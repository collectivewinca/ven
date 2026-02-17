# miny-ven Handoff for Cline CLI

## Repo
- GitHub: `https://github.com/collectivewinca/miny-ven`
- Local path: `/Users/aletviegas/Documents/codex/miny-ven`
- Branch: `main`

## Current Deployment State
- Public working alias: `https://ven.minyvinyl.com` (HTTP 200)
- Raw Vercel deployment URL: `https://miny-7i29v7l25-collective-win.vercel.app` (HTTP 401, auth protected)

## What Was Done
- Pushed scraper/data freshness fixes and debugging improvements.
- Added Firestore preflight step to workflow.
- Added RSS sorting by `pubDate` before processing.
- Added freshness guard in workflow (fails if latest `fetched_at` > 24h old).
- Added project notes:
  - `PROJECT_NOTE_2026-02-13.md`
  - README “Latest Updates (2026-02-13)” section

## Recent Key Commits
- `8fd6eb1` Sort RSS items by pubDate before processing
- `688fddd` Add Firestore preflight check to scraper workflow
- `c27e7fa` chore: trigger vercel deploy with authorized author
- `3191cbe` Fix stale ingestion and local Firestore fallback

## Known Problem (Still Open)
- Scraper workflows run, but Firestore data remains stale.
- Latest known Firestore timestamps:
  - `fetched_at`: `2026-02-11T15:56:12.166468`
  - `published_at`: `2026-02-11T15:31:27+00:00`
- Latest workflow runs (Feb 13, 2026) failed on freshness gate after scraper step.

## Verified Findings
- Firestore access in GitHub Actions is valid (preflight step succeeds).
- Issue is inside scraper ingestion behavior (writes not producing fresh docs), not auth to Firestore.

## Vercel / Permissions Context
- Team email alerts show failures like:
  - “Failed CLI deployment from `aletviegas@users.noreply.github.com`”
  - Reason: user not recognized as member/collaborator in Vercel team context.
- Public alias currently works despite raw deploy URL auth protection.

## Highest-Priority Next Steps
1. Pull workflow logs for failing runs and capture per-source counters:
   - feed items fetched
   - duplicate skips
   - save attempts and response codes
2. Add explicit structured summary output from scraper (JSON per source) and upload as workflow artifact.
3. Confirm whether each RSS source is returning recent items in GitHub Actions runtime.
4. Verify write path to Firestore for non-duplicate docs (doc ID/hash and PATCH responses).
5. Re-run workflow and confirm latest `fetched_at` crosses current UTC date.

## Useful Commands
```bash
# Trigger workflow
gh api repos/collectivewinca/miny-ven/actions/workflows/scraper.yml/dispatches -X POST -f ref=main

# List latest runs
gh api repos/collectivewinca/miny-ven/actions/workflows/scraper.yml/runs --jq '.workflow_runs[] | [.id,.status,.conclusion,.created_at,.html_url] | @tsv' | head

# Check Firestore freshness
curl -sS "https://firestore.googleapis.com/v1/projects/miny-ven/databases/(default)/documents/articles?pageSize=200" \
  | jq -r '.documents[]?.fields.fetched_at.stringValue' | sort -r | head
```

## Handoff Goal
Get scraper to write fresh articles again (post-2026-02-11) and pass freshness verification in CI.
