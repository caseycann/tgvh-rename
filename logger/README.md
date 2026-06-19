# Take Logger

Mobile-first web app for the AD/director to log takes from the slate, in real
time, straight to Airtable. The DIT pulls this log at wrap to drive renaming
(see `../dit-tool`).

## Local dev

```bash
cd logger
npm install
cp .env.local.example .env.local   # then fill in your Airtable credentials
npm run dev
```

Open http://localhost:3000 — on a phone on the same wifi, use your machine's
LAN IP instead of `localhost` (e.g. `http://192.168.1.23:3000`).

## Env vars

| Var | Description |
|---|---|
| `AIRTABLE_API_KEY` | Personal Access Token with `data.records:write` (and `:read` for recent-takes) on the base. **Server-side only** — never exposed to the browser. |
| `AIRTABLE_BASE_ID` | The base ID, starts with `app...`. |
| `AIRTABLE_TABLE_NAME` | Table to write to. Defaults to `Footage`. |

## Deploy to Vercel

```bash
npm install -g vercel   # if not already installed
cd logger
vercel
```

Then set the three env vars above in the Vercel project settings (Project →
Settings → Environment Variables) for the Production environment, and
redeploy. Share the resulting `https://<project>.vercel.app` URL with whoever
is logging takes that day — works on any phone/tablet/laptop browser.

## How it works

- `app/page.tsx` — the form. Remembers the last Location/Scene/Shot typed in
  the browser session and auto-suggests the next Take number when
  Location+Scene+Shot match the most recently logged entry.
- `app/api/log-take/route.ts` — server route, writes one row to Airtable.
  This is the only place the Airtable token is used.
- `app/api/recent-takes/route.ts` — server route, returns the last 15 logged
  rows so the form can show a live feed and compute take auto-suggestions.

No state is kept outside Airtable — if the page is closed/reopened, the
"recent" list and auto-suggest just refetch from Airtable.

## Known limitation (v1)

Assumes reliable internet (cell signal or a hotspot) on location. If
connectivity drops, takes won't log until it's back — there's no offline
queue/sync in this version. If a dead zone turns out to be a real problem,
the DIT's `batch` CSV fallback (see `../dit-tool`) covers that day instead.
