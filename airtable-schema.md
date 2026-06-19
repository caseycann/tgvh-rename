# Airtable Schema — `Footage` Table

This is already built in the production base (`appwlYDQ4ihdowH9E`) as the
`Footage` table. Field names below are the actual field names in that table —
the logger and DIT tool are built against these exactly.

| Field Name     | Type                                   | Notes                                                                 |
|----------------|-----------------------------------------|------------------------------------------------------------------------|
| `Name`         | Single line text                       | Primary field. Not used by the tooling; Airtable requires a primary field. |
| `Date`         | Date                                    | Shoot day. Used to scope which rows `pull` fetches.                   |
| `Location`     | Single line text                       | e.g. `Grange`                                                         |
| `Scene`        | Single line text                       | Text, not number — scene numbers can be `23A`, `64`, etc.             |
| `Shot`         | Single line text                       | Same reasoning as Scene.                                               |
| `Take`         | Number (integer)                       |                                                                          |
| `Flagged Take` | Checkbox                               | Optional. Flags a good take for the editor.                           |
| `Status`       | Single select (`Good`/`No good`/`Exceptional`) | Optional triage info.                                          |
| `Notes`        | Long text                              | Free text from the slate or AD.                                       |
| `Logged At`    | Created time                           | Automatic. This is the chronological key used to match rows to files. |
| `Logged By`    | Single line text                       | Optional — who tapped it in.                                          |

## Why `Logged At` matters

The DIT tool's `pull` mode has no other way to know which take corresponds to
which file — cameras don't write scene/shot/take into filenames. It sorts
Airtable rows by `Logged At` and sorts files in `Footage/`/`Audio/` by file
creation time, then pairs them up in order. Keeping logging prompt (AD logs the
take right after it happens, not in a batch later) keeps that ordering
reliable.

## API access

You'll need two Airtable Personal Access Tokens (https://airtable.com/create/tokens):

- **Write token** (`data.records:write` on the base) — used by the logger's
  serverless API route, set as `AIRTABLE_API_KEY` in Vercel.
- **Read token** (`data.records:read` on the base) — used by the DIT tool's
  `pull` mode, can be the same token if you don't want to manage two.

Also note your **Base ID** (starts with `app...`, found in the API docs for
your base) — needed by both the logger and the DIT tool.
