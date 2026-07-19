# miny-ven

60-word music news PWA for creators — Gospel, Hip-Hop, Pop, Rock, Electronic

## Live

- **App**: https://ven.minyvinyl.com
- **Aliases**: https://minyven-news.vercel.app / https://miny-ven.vercel.app

## Ops Docs

- **Scraper Operations**: `README_SCRAPER_OPS.md`
- **VM Runbook**: `RUNBOOK.md`
- **CLI Reference**: `scraper/README_MINY_CLI.md`

## Features

### Music News (ven.minyvinyl.com)
- **60-Word Summaries** — DeepSeek AI condenses every article to exactly 60 words
- **5 Balanced Genres** — Gospel, Hip-Hop, Pop, Rock, Electronic
- **Dual Discovery** — 5 RSS feeds + Exa AI search across genre queries
- **CTA Headlines** — Perplexity SDK rewrites titles into click-worthy headlines
- **Smart Dedup** — Jaccard similarity (80% threshold) + URL canonicalization
- **Refusal Guard** — regex filter catches AI meta-commentary before it reaches the DB
- **Bookmarks** — click any title to save locally (localStorage)
- **Text Link (Quo API)** — send article links via SMS
- **Swipe Navigation** — mobile-optimized gesture browsing
- **Pull to Refresh** — swipe down for fresh content
- **PWA Ready** — installable on mobile devices

### EPK / RapidConnect Integration
- **Live EPK Lookup** — article titles + summaries scanned against `sm_musicians` PocketBase collection on `miny-database.exe.xyz`; matches link to artist EPKs at `rapidconnect.minyvinyl.com`
- **Published-Only Gate** — indexes only records with `content_status='published'` (paired with Subway-Musician EPK quality contract, see PR #9)
- **Embedded Fallback** — ships a static `artistEpkIndex.json` snapshot; falls back gracefully if the PB filter 400s (pre-field-add window)
- **Cache** — localStorage key `miny-ven-artist-epk-index-v2` (bumped from v1 to drop stale unfiltered indexes after the published-only gate shipped)
- **Source**: `src/hooks/useArtistEpk.ts`

### Music Trends Monitor (music-trends/)
- **30+ Subreddits** — Music communities across MINY y0's 13 cities
- **Regional Coverage** — 5 regions: Latin America, Nordic/Europe, Africa/Middle East, Asia, Global/Indie
- **Dynamic Dashboards** — Auto-generated trends pages and analytics
- **48-Hour Automation** — Cron job updates every 2 days
- **Real-time Insights** — Trending topics, engagement metrics, keyword analysis
- **MINY y0 Integration** — CTAs linking to y0.minyvinyl.com for artist applications
- **here.now Publishing** — Permanent hosting of trends dashboards
- **Data-driven Decisions** — Analytics for artist recruitment and content strategy

## Architecture

### Music News Scraper
```
                     hourly cron (:05)
                              |
                    +---------v----------+
                    | y0-minynet VM      |
                    | miny CLI + cron    |
                    +---------+----------+
                              |
                    +---------v----------+
                    | rss_scraper.py     |
                    |                    |
                    |  1. RSS feeds (5)  |
                    |  2. Exa discovery  |
                    |  3. Perplexity CTA |
                    |  4. DeepSeek 60w   |
                    +---------+----------+
                              |
                    +---------v----------+
                    | Firestore REST API |
```

### Music Trends Monitor
```
                     every 48 hours
                              |
                    +---------v----------+
                    | update_trends.sh   |
                    |                    |
                    |  1. Fetch 30+      |
                    |     subreddits     |
                    |  2. Generate       |
                    |     trends HTML    |
                    |  3. Create         |
                    |     analytics      |
                    |  4. Publish to     |
                    |     here.now       |
                    +---------+----------+
                              |
                    +---------v----------+
                    | Live Dashboards    |
                    |                    |
                    | • Trends Monitor   |
                    | • Analytics        |
                    | • MINY y0 CTAs     |
                    +--------------------+
```
                    | (constrained write)|
                    +---------+----------+
                              |
                    +---------v----------+
                    | React + Vite PWA   |
                    | (Vercel hosting)   |
                    +--------------------+
```

### Frontend
- **Framework**: React 19 + TypeScript + Vite
- **Styling**: Tailwind CSS with glass-morphism design
- **Data**: REST API calls to Firebase Firestore
- **Hosting**: Vercel (manual deploy via `vercel --prod`)

### Scraper Pipeline
- **Language**: Python 3.12 (VM runtime)
- **RSS Sources**: Jesusfreakhideout, Pitchfork News, Pitchfork Reviews, Rolling Stone, Billboard
- **Exa Discovery**: 5 genre queries x 5 results — finds articles beyond RSS feeds
- **Perplexity SDK** (`sonar` model): generates CTA headlines, article research (Exa fallback)
- **DeepSeek API** (`deepseek-chat`): 60-word summaries
- **Firestore REST API**: unauthenticated constrained writes (16 fields, strict validation)
- **Automation**: VM cron (`miny run` hourly at `:05`) + optional manual GitHub Actions dispatch

### AI Fallback Chain
| Step | Primary | Fallback |
| --- | --- | --- |
| News discovery | Exa search | Perplexity `sonar` |
| Article research | Exa content extraction | Perplexity `sonar` |
| CTA headlines | Perplexity `sonar` | Regex title transform |
| 60-word summaries | DeepSeek `deepseek-chat` | First 60 words of content |

If any AI response triggers the refusal guard (meta-commentary like "I notice...", "As an AI..."), the pipeline falls back to the next level automatically.

## Quick Start

### Prerequisites
- Node.js 18+
- Python 3.11+
- Firebase project

### 1. Clone

```bash
git clone https://github.com/collectivewinca/miny-ven.git
cd miny-ven
```

### 2. Frontend

```bash
npm install
cp .env.example .env
# Add Firebase credentials to .env
npm run dev
```

### 3. Scraper

```bash
cd scraper
pip install -r requirements.txt
cp .env.example .env
# Add API keys to .env
python3 rss_scraper.py
```

### 4. VM Operations CLI

```bash
cd scraper
./miny --help

# Common ops
./miny status
./miny deploy --all
./miny logs --follow
./miny metrics --period=24h
```

## Project Structure

```
miny-ven/
├── .github/workflows/
│   └── scraper.yml            # Manual fallback run in GitHub Actions
├── RUNBOOK.md                 # VM operations runbook
├── scraper/
│   ├── rss_scraper.py         # Main scraper (RSS + Exa + AI pipeline)
│   ├── miny_cli.py            # VM scraper management CLI
│   ├── miny                   # Executable wrapper for miny_cli.py
│   ├── README_MINY_CLI.md     # CLI command reference
│   ├── requirements.txt       # Python deps (perplexityai, exa_py, etc.)
│   ├── cleanup_duplicates.py  # Remove duplicate articles from Firestore
│   ├── seed_firebase_rest.py  # Initial data seeding
│   └── .env.example           # Required API keys template
├── src/
│   ├── App.tsx                # Main React app with bookmarks + swipe
│   └── firebase.ts            # Firebase config
├── api/
│   └── quo-sms.js             # Vercel serverless SMS endpoint
├── firestore.rules            # Strict 16-field schema validation
├── firebase.json              # Firebase project config
├── vercel.json                # Vercel deployment config
└── README.md
```

## Environment Variables

### Frontend (`.env`)
```bash
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=miny-ven.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=miny-ven
VITE_FIREBASE_STORAGE_BUCKET=miny-ven.firebasestorage.app
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
VITE_FIREBASE_MEASUREMENT_ID=
VITE_PUBLIC_APP_URL=https://ven.minyvinyl.com
```

### Scraper (`scraper/.env`)
```bash
FIREBASE_API_KEY=           # Firestore REST API key
FIREBASE_PROJECT_ID=miny-ven
PERPLEXITY_API_KEY=         # CTA headlines + research fallback (model: sonar)
DEEPSEEK_API_KEY=           # 60-word summaries (model: deepseek-chat)
EXA_API_KEY=                # Article research + news discovery
BRAVE_API_KEY=              # Librarium provider
GEMINI_API_KEY=             # AI image generation fallback (gemini-2.5-flash-image)
FIREBASE_SERVICE_ACCOUNT_B64= # Firebase Storage service account JSON (base64)
```

### GitHub Actions Secrets
```
FIREBASE_API_KEY
DEEPSEEK_API_KEY
PERPLEXITY_API_KEY
EXA_API_KEY
BRAVE_API_KEY
GEMINI_API_KEY
FIREBASE_SERVICE_ACCOUNT_B64
```

### Vercel (for Quo SMS API)
```bash
QUO_API_URL=
QUO_API_KEY=
QUO_API_KEY_HEADER=Authorization
QUO_AUTH_SCHEME=raw
QUO_FROM=
```

## Scraper Operations (VM-first)

Primary runtime is VM cron:

```cron
5 * * * * /usr/bin/flock -n /home/exedev/miny-ven/scraper/.rss_scraper.lock /bin/bash -lc 'MINY_LOCAL_MODE=1 /home/exedev/bin/miny run'
```

Primary commands:

```bash
MINY_LOCAL_MODE=1 /home/exedev/bin/miny status
MINY_LOCAL_MODE=1 /home/exedev/bin/miny run
MINY_LOCAL_MODE=1 /home/exedev/bin/miny logs --follow
MINY_LOCAL_MODE=1 /home/exedev/bin/miny rollback
```

## GitHub Actions Workflow (Manual Fallback)

The `scraper.yml` workflow is manual (`workflow_dispatch`) and includes:

1. **Preflight** — verifies Firestore is reachable before scraping
2. **RSS Scraper** — fetches 5 feeds + Exa discovery + AI processing
3. **Freshness Guard** — fails the run if newest `fetched_at` is older than 24h
4. **Status Report** — logs total article count

```bash
# Manual trigger
gh workflow run "Hourly RSS Scraper"

# Watch a run
gh run list --workflow=scraper.yml --limit 5
gh run watch <run-id>

# View logs
gh run view <run-id> --log
```

## Firestore Rules

Unauthenticated scraper writes are constrained to:
- Exactly 16 required fields (no `id` field in payload)
- Strict type validation (string, int, list)
- Title 1-200 chars, summary 1-1000 chars, content max 4000 chars
- `source_url` must start with `https://`
- Counter fields (`share_count`, `email_count`, `bookmark_count`) must be 0 on create

Authenticated users have full read/write/delete access.

## Changelog

### 2026-07-19
- **Fixed (build)**: removed dead `getField` helper in `useArtistEpk.ts` that blocked `tsc -b` (TS6133 unused value) — Vercel production deploy was failing on this since the PR #1 merge
- **Migrated**: `useArtistEpk` reads live PocketBase `sm_musicians` at `miny-database.exe.xyz` (published-only) instead of the stale `subway-musician-564bd` Firestore April snapshot — paired with Subway-Musician PR #9 (EPK quality contract: sanitized LLM output, name guard, fail-closed generation, repair sweep)
- **Added**: localStorage cache key bumped to `v2` so stale unfiltered indexes drop on first load after the published-only gate
- **Deploy**: Vercel production at https://ven.minyvinyl.com (redeploy after build fix)

### 2026-03-05
- **Added**: Music Trends Monitoring System (`music-trends/`)
  - Automated Reddit trends tracking for MINY y0 cities
  - 30+ music subreddits across 5 regions
  - Dynamic trends pages and analytics dashboards
  - 48-hour automation via cron job
  - here.now publishing integration

### 2026-02-25
- **Added**: VM-first scraper operations CLI (`scraper/miny_cli.py`) with `run/logs/status/deploy/rollback/metrics/cron`
- **Updated**: Scheduler source of truth moved to VM cron (`:05`) with lockfile guard (`flock`)
- **Updated**: GitHub Actions scraper workflow to manual fallback only (`workflow_dispatch`)
- **Added**: VM runbook (`RUNBOOK.md`) and scraper ops overview (`README_SCRAPER_OPS.md`)

### 2026-02-13
- **Fixed**: Firestore 403 — removed `id` field from payload (rules enforce exactly 16 fields)
- **Added**: Exa SDK integration for article research and news discovery (5 genre queries)
- **Added**: Perplexity-based discovery fallback when Exa is unavailable
- **Added**: Refusal guard — regex filter catches 15+ AI meta-commentary patterns
- **Migrated**: Perplexity from raw HTTP to official SDK, model `sonar`
- **Added**: `_clean_perplexity_text()` — strips markdown bold and citation brackets
- **Added**: OpenAI image generation fallback for articles missing feed/OG/artist images
- **Updated**: GitHub Actions workflow — added `EXA_API_KEY`, removed `OPENROUTER_API_KEY`
- **Deployed**: Vercel production at https://ven.minyvinyl.com

### 2026-02-11
- Initial scraper with RSS feeds + DeepSeek summaries
- Firestore security rules with constrained writes
- GitHub Actions hourly cron
- PWA frontend with bookmarks, swipe, Quo SMS

## License

Private repository — All rights reserved
