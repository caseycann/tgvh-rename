# Airtable Schema — `Footage` Table

This is built in the production base (`appwlYDQ4ihdowH9E`) as the `Footage`
table, and links out to the existing `Physical Locations` and `Scenes`
tables. Field names below are the actual field names — the logger and DIT
tool are built against these exactly.

| Field Name          | Type                                    | Notes                                                                 |
|----------------------|------------------------------------------|------------------------------------------------------------------------|
| `Name`               | Single line text                       | Primary field. Composed by the logger app as `Location_Scene_Shot_Take` at write time — not auto-computed by Airtable. |
| `Date`               | Date                                    | Shoot day. Used to scope which rows `pull` fetches.                   |
| `Physical Locations` | Link to another record (`Physical Locations`) | What the logger writes to. Pick the location actually shot at.   |
| `Location`           | Lookup (`Nickname` from `Physical Locations`) | Read-only, Airtable-computed. This is what's used for the filename — the `Nickname` field on `Physical Locations` is a no-space slug (e.g. `Grange`), unlike `Name` which is a full prose name. |
| `Scene`              | Link to another record (`Scenes`)      | Pick the scene from the existing list rather than typing it in.       |
| `Shot`               | Single select                          | Predefined choices (`1`–`30` currently). The logger sends `typecast: true` so a new shot number still gets written even if it's not yet a defined choice. |
| `Take`               | Number (integer)                       |                                                                          |
| `Flagged Take`       | Checkbox                               | Optional. Flags a good take for the editor.                           |
| `Status`             | Single select (`Good`/`No good`/`Exceptional`) | Optional triage info.                                          |
| `Notes`              | Long text                              | Free text from the slate or AD.                                       |
| `Logged At`          | Created time                           | Automatic. This is the chronological key used to match rows to files. |
| `Logged By`          | Single line text                       | Optional — who tapped it in.                                          |
| `Media`              | Single select (`Just Video`/`Just Audio`/`Sync Sound`) | Set by the logger's 3-button toggle (Video/Audio/Sync Sound), defaults to `Just Video`. |
| `Sync Sound`         | Checkbox                               | Not written by the logger (that's `Media` now). The DIT tool's web UI checks this automatically when a batch rename produces both a footage file and an audio file sharing the same basename — see [dit-tool/README.md](dit-tool/README.md#linking-renamed-files-back-to-airtable). |
| `Source`             | Single select (`Live logged`/`Ingested`) | Set by the DIT tool's web UI after a rename: `Live logged` if the AD already logged this take and the row existed, `Ingested` if the row was created after the fact from a renamed file with no prior log entry. |

## Naming source fields

The logger composes `Name` (and the DIT tool's `pull` mode composes the
renamed filename) from:

- **Location** → the `Nickname` field on the linked `Physical Locations`
  record (e.g. `Grange`), not the full `Name` field — fetched via the
  `Physical Locations` dropdown in the logger, which shows Nickname (or Name
  as a fallback if a location has no Nickname set yet).
- **Scene** → the `Scenes` table's `Scene Number` field, with a leading
  `"SCENE "` prefix stripped (real data looks like `"SCENE 23"`, `"SCENE
  55b"` — the tooling strips the prefix and keeps `23`, `55b`).
- **Shot** → the single-select value as typed/selected (e.g. `4`).
- **Take** → the take number.

All four are zero-padded to 2 digits when numeric for the final filename
(`Grange_23_04_01.mxf`), matching the original naming convention — Scene
codes with letters (like `55b`) are left as-is.

## Why `Logged At` matters

The DIT tool's `pull` mode has no other way to know which take corresponds to
which file — cameras don't write scene/shot/take into filenames. It sorts
Airtable rows by `Logged At` and sorts files in `Footage/`/`Audio/` by file
creation time, then pairs them up in order. Keeping logging prompt (AD logs the
take right after it happens, not in a batch later) keeps that ordering
reliable.

## API access

You'll need an Airtable Personal Access Token (https://airtable.com/create/tokens)
with, at minimum:

- `data.records:read` and `data.records:write` on the base — for the logger
  (writes to `Footage`, reads from `Physical Locations`/`Scenes` to populate
  dropdowns) and for the DIT tool's `pull` mode (reads `Footage`).

Also note your **Base ID** (starts with `app...`) — needed by both the
logger and the DIT tool.
