# DIT Rename Tool

`rename_footage.py` — pure Python standard library, no installs needed
(Python 3.8+). Renames footage/audio files into
`Location_Scene_Shot_Take.ext` inside a `YYYYMMDD/Footage` and
`YYYYMMDD/Audio` folder pair. Nothing is ever uploaded — all file
operations are local; `pull` mode only sends/receives small Airtable
records over the network, never media.

All three modes:
- Zero-pad scene/shot/take to 2 digits if they're numeric (e.g. `4` → `04`).
- Print a full preview and require typing `y` before touching any file.
- Never overwrite an existing file — collisions are skipped with a warning.
- Append every successful rename to `rename_log.csv` in the date folder, so
  there's always a local paper trail independent of Airtable.

## Modes

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
slates), then re-run the same command to preview and execute the renames.

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
the top of `rename_footage.py` to add more.

## Recommended workflow

1. AD/director logs takes live via the [logger app](../logger) throughout
   the day (see [Airtable schema](../airtable-schema.md) for the `Footage`
   table this reads from).
2. At wrap, DIT runs `pull` for the day's folder. Review the preview
   carefully — if the counts line up, confirm.
3. If logging didn't happen (dead zone, AD too busy, etc.), fall back to
   `batch`: watch footage back, fill in the CSV, rename.
4. `live` is there as a fast manual path any time, independent of the other
   two — useful if the DIT wants to rename as they go regardless of what's
   in Airtable.
