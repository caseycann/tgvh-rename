# DIT Rename Tool

Renames footage/audio files into `Location_Scene_Shot_Take.ext` inside a
`YYYYMMDD/Footage` and `YYYYMMDD/Audio` folder pair. Nothing is ever
uploaded — all file operations are local; `pull` mode and the web UI's
Airtable calls only send/receive small JSON records over the network,
never media.

Two ways to use it:

- **Web UI** (`webapp/`) — a local browser interface, for anyone (DIT or
  AD) who'd rather not use the command line. Same underlying logic as the
  CLI.
- **CLI** (`rename_footage.py`) — `live` / `batch` / `pull` modes, zero
  Python dependencies beyond the standard library.

Both share `core.py`, so the rename/pairing logic is identical either way.

All modes/flows:
- Zero-pad scene/shot/take to 2 digits if they're numeric (e.g. `4` → `04`).
- Preview every proposed rename and require an explicit confirm before
  touching any file.
- Never overwrite an existing file — collisions are skipped with a warning.
- Append every successful rename to `rename_log.csv` in the date folder, so
  there's always a local paper trail independent of Airtable.

## Setup

The CLI's `live`/`batch`/`pull` modes need nothing beyond Python 3.8+. The
web UI and slate transcription need a couple of installs:

```bash
cd dit-tool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg   # if not already installed — required for slate transcription
```

**Before going on location**, run the web UI once with internet access so
the Whisper speech model downloads and caches locally (~150MB, one-time):

```bash
source .venv/bin/activate
python3 -c "import slate_transcribe; slate_transcribe.get_model()"
```

After that, slate transcription works fully offline.

## Web UI

```bash
source .venv/bin/activate
AIRTABLE_API_KEY=pat... AIRTABLE_BASE_ID=app... python3 webapp/app.py
```

On this machine, this is also wired up as a plain shell command — just run:

```bash
rename
```

That's a wrapper script at `/opt/homebrew/bin/rename` which `cd`s into this
folder, activates `.venv`, loads `dit-tool/.env` (Airtable credentials —
gitignored, not in the repo) for you, and starts the server. It's
machine-specific (hardcodes this checkout's path), so it won't follow the
repo if cloned elsewhere — re-create it there if needed:

```bash
cat > /opt/homebrew/bin/rename <<'EOF'
#!/bin/bash
set -e
DIT_TOOL_DIR="/absolute/path/to/tgvh-rename/dit-tool"
if [ -f "$DIT_TOOL_DIR/.env" ]; then
  set -a; source "$DIT_TOOL_DIR/.env"; set +a
fi
source "$DIT_TOOL_DIR/.venv/bin/activate"
cd "$DIT_TOOL_DIR"
exec python3 webapp/app.py "$@"
EOF
chmod +x /opt/homebrew/bin/rename
```

Open http://localhost:5050 in a browser **on the same machine** — this is
a local-only server, nothing is exposed to the network. Type in the date
folder path, click "Load folder", then **Batch / Slate scrub** — currently
the only mode shown in the UI, since slate transcription turned out to
cover the real workflow well enough that Live and Pull from Airtable
aren't needed day-to-day:

- **Batch / Slate scrub** — loads every file in `Footage`/`Audio` into an
  editable table. Each row has a "Suggest from slate" button (see below).
  Pick Location/Scene from the dropdowns (sourced from Airtable) so the
  Airtable-link step below has a record to link to.

`Live` and `Pull from Airtable` (the same logic as CLI `pull`) are still
fully implemented underneath — routes, JS functions, everything — just not
exposed as tabs. To bring a tab back, uncomment its `<button>` in the
`.mode-tabs` div in `webapp/templates/index.html` (see the HTML comment
there for exactly which lines).

`AIRTABLE_API_KEY`/`AIRTABLE_BASE_ID` are optional if you only need to
rename files with no Airtable involvement at all — the Location/Scene
dropdowns and the Airtable-link step (below) just won't run.

## Linking renamed files back to Airtable

After a batch confirm, for each renamed take the web UI checks the
`Footage` table for a row whose `Name` already matches the new filename:

- **Already exists** (the AD logged it live) — only the `Source` field is
  updated, to `Live logged`. Nothing else on that row is touched.
- **Doesn't exist yet** (never logged, only ingested after the fact) — a
  new row is created with whatever's available (`Name`, `Date`, the
  selected `Physical Locations`/`Scene` links, `Shot`, `Take`) and
  `Source` set to `Ingested`.

This runs once per unique take (footage + its matching audio share one
row, same as live logging), right after the actual file rename succeeds.
If Airtable isn't configured, this step is silently skipped — files still
get renamed locally either way.

## Slate transcription ("Suggest from slate")

For days with no live Airtable logging, instead of a DIT manually
watching every clip back to read the slate by eye, the web UI can scrub
the first ~20 seconds of a file's audio and auto-detect spoken slate
info ("Scene 23, shot 4, take 2") using a local speech-to-text model
(faster-whisper, `base.en`, runs on CPU — no audio or video ever leaves
the machine).

**File integrity guarantee:** this only ever *reads* the original file.
The extraction step (`ffmpeg -i <original> ... <temp.wav>`) opens the
original strictly as input — ffmpeg never writes to its input — and the
only output is a small temp WAV file in the system temp directory, which
is deleted immediately after transcription regardless of success or
failure. The rename step itself (`Path.rename`) is a directory-entry
operation; it never opens file content at all. Nothing about this process
can corrupt or alter the original media, before or after archiving.

This is a **suggestion only** — spoken-slate transcription is inherently
imperfect (mumbled numbers, no slate that take, ambient noise). Always
review the "Heard: ..." transcript shown under each suggestion and the
filled-in Scene/Shot/Take values before confirming a rename. It only
fills in fields when it finds the literal words "scene"/"shot"/"take"
followed by a number — it won't guess from bare numbers alone.

## CLI

### `live` — right after a take, no Airtable needed

```bash
python3 rename_footage.py live --root /path/to/20260619
```

Finds the most-recently-modified file in `Footage/` and `Audio/`, prompts
for Location/Scene/Shot/Take off the slate, previews, confirms, renames
both files together. Fast path for a DIT keeping up in real time.

`--root` defaults to `./<today's date as YYYYMMDD>` if omitted.

### `batch` — CSV-driven, for days with no live logging

```bash
python3 rename_footage.py batch --root /path/to/20260619
```

First run with no `batch_rename.csv` present creates a template listing
every file currently in `Footage/`/`Audio/`. Fill in `location`, `scene`,
`shot`, `take` for each row (e.g. while watching footage back to read
slates, or using the web UI's slate-scrub feature first and exporting),
then re-run the same command to preview and execute the renames.

### `pull` — fetch the day's log from Airtable

```bash
AIRTABLE_API_KEY=pat... AIRTABLE_BASE_ID=app... python3 rename_footage.py pull --root /path/to/20260619
```

Requires env vars:

| Var | Description |
|---|---|
| `AIRTABLE_API_KEY` | Personal Access Token with `data.records:read` on the base. |
| `AIRTABLE_BASE_ID` | The base ID, e.g. `appwlYDQ4ihdowH9E`. |
| `AIRTABLE_TABLE_NAME` | Optional, defaults to `Footage`. |

Fetches every row logged for the folder's date (parsed from the `YYYYMMDD`
folder name), sorted by `Logged At`. Separately sorts files in `Footage/`
and `Audio/` by file creation time, and pairs each folder's files with the
Airtable rows **in chronological order** — the same heuristic `live` mode
uses, just driven by the AD's log instead of "most recent file."

If the file count in a folder doesn't match the number of logged rows, it
warns loudly before the preview — review carefully in that case, since the
pairing may be off. When in doubt, `batch` is the safer fallback.

## Supported extensions

`.mxf .mov .mp4 .r3d .braw .ari .wav .bwf` — edit `SUPPORTED_EXTENSIONS` at
the top of `core.py` to add more.

## Recommended workflow

1. AD/director logs takes live via the [logger app](../logger) throughout
   the day (see [Airtable schema](../airtable-schema.md) for the `Footage`
   table this reads from).
2. At wrap, run `pull` (CLI or web UI) for the day's folder. Review the
   preview carefully — if the counts line up, confirm.
3. If logging didn't happen (dead zone, AD too busy, etc.), use `batch` —
   either the web UI's slate-scrub assist, or manually watching footage
   back and filling in the CSV.
4. `live` is there as a fast manual path any time, independent of the
   other two — useful if the DIT wants to rename as they go regardless of
   what's in Airtable.
