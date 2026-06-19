# TGVH Footage Renaming System

Renames footage/audio from `YYYYMMDD/Footage/` and `YYYYMMDD/Audio/` into
`Location_Scene_Shot_Take.ext`, sourced from live take logging instead of
guessing from file order or shoot-day timing (shoot days aren't sequential by
scene/shot).

Three pieces:

- **[`airtable-schema.md`](airtable-schema.md)** — the `Footage` table this
  system reads/writes, already built in the production base.
- **[`logger/`](logger/README.md)** — mobile-first web app the AD/director
  uses on set to log each take straight off the slate, in real time, to
  Airtable. Deploys to Vercel.
- **[`dit-tool/`](dit-tool/README.md)** — local Python script the DIT runs.
  `pull` fetches the day's Airtable log and renames to match; `batch` is a
  CSV fallback for days with no live logging; `live` is a manual one-take-
  at-a-time mode independent of Airtable. No media ever leaves the machine.

## Quick start

1. AD/director opens the deployed logger URL on their phone, logs takes as
   they happen.
2. At wrap, DIT runs:
   ```bash
   AIRTABLE_API_KEY=... AIRTABLE_BASE_ID=appwlYDQ4ihdowH9E python3 dit-tool/rename_footage.py pull --root /path/to/20260619
   ```
3. If no logging happened that day, DIT runs `batch` mode instead (see
   [dit-tool/README.md](dit-tool/README.md)).
