# miny-ven Project Note (2026-02-13)

## Current Status

- Production deploy completed on Vercel via CLI.
- Recent production URL: `https://miny-7i29v7l25-collective-win.vercel.app`
- Alias attached during deploy: `https://ven.minyvinyl.com`
- Core UI/data fallback fix is live (local Firebase env no longer hard-blocks article fetch).

## Latest Code Updates

1. `3191cbe` - `Fix stale ingestion and local Firestore fallback`
1. `c27e7fa` - `chore: trigger vercel deploy with authorized author`
1. `688fddd` - `Add Firestore preflight check to scraper workflow`
1. `8fd6eb1` - `Sort RSS items by pubDate before processing`

## Workflow Timeline (GitHub Actions)

- `22001971775` (workflow_dispatch, 2026-02-13T20:36:48Z): `completed/failure`
- `22001836943` (workflow_dispatch, 2026-02-13T20:32:09Z): `completed/failure`
- `22001785893` (schedule, 2026-02-13T20:30:23Z): `completed/failure`
- `22001504620` (workflow_dispatch, 2026-02-13T20:20:29Z): `completed/failure`
- `22000247653` (schedule, 2026-02-13T19:38:05Z): `completed/success`

Run links are in GitHub Actions:
`https://github.com/collectivewinca/miny-ven/actions/workflows/scraper.yml`

## Debugger Findings

- Firestore preflight access step passes in workflow (API key + connectivity are valid in Actions).
- `Run RSS Scraper` completes, but freshness verification fails.
- Latest Firestore `fetched_at` remains:
  - `2026-02-11T15:56:12.166468`
  - `2026-02-11T15:56:08.846410`
  - `2026-02-11T15:56:04.757200`

Conclusion: pipeline executes, but no fresh records are being inserted after 2026-02-11.

## Open Issue

Even after duplicate logic and feed ordering fixes, ingestion remains stale. Next debug step should inspect scraper runtime output for each feed/API path (item counts, duplicate skips, save responses) from workflow logs and/or add explicit per-source counters to job summary.

