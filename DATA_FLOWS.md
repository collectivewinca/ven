# MINY y0 Data Flows

## Architecture

```
                    VM: y0-minynet.exe.xyz
                    ┌─────────────────────────────────────────────────┐
                    │                                                 │
  RSS Sources ──── │  rss_scraper.py (hourly :05)                    │
  (60+ feeds)      │    → PocketBase articles (34k+)                 │
                    │                                                 │
                    │  tag-articles-location.py (every 15min)         │
                    │    → articles.location = "City Name"            │
                    │    → uses residency-aliases.yaml (16 cities)    │
                    │                                                 │
                    │  entity_tracker.py (every 6h)                   │
                    │    → PocketBase entities (11k+)                 │
                    │    → extracts artists/albums via Gemini         │
                    │                                                 │
                    │  y0-daily-pipeline.sh (daily 13:00 UTC)         │
                    │    1. generate_music_cities.py                  │
                    │       → keyword filter + LLM (gemma4:31b)       │
                    │       → ~32 articles across 12 cities           │
                    │       → SearXNG supplement for thin cities      │
                    │       → writes music-cities.html                │
                    │                                                 │
                    │    2. extract_feed_entities.py                  │
                    │       → LLM extracts artist names               │
                    │       → upserts to entities with city + links   │
                    │                                                 │
                    │    3. ve_curator.py --run                       │
                    │       → LLM picks top 5 articles/day            │
                    │       → marks curated=true, curator="VE Curator"│
                    │                                                 │
                    │    4. enrich_directory.py                       │
                    │       → SearXNG finds RC profile URLs           │
                    │       → stores rc_profile_url in entities       │
                    │                                                 │
                    │    5. generate_music_cities.py (re-run)         │
                    │       → final HTML with curated badges + RC     │
                    │                                                 │
                    └────────────────────┬────────────────────────────┘
                                         │
                                    SCP (ssh)
                                         │
                    ┌────────────────────▼────────────────────────────┐
                    │  Mac: deploy-music-cities.sh (launchd 13:00 ET) │
                    │    → pulls music-cities.html from VM             │
                    │    → x_supplement.py (bird CLI, thin cities)     │
                    │    → l30d_supplement.py (last30days, 0-article)  │
                    │    → copies to miny-y0-landing repo              │
                    │    → vercel deploy --prod                        │
                    └────────────────────┬────────────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────────────┐
                    │  Vercel: y0.minyvinyl.com                       │
                    │    → index.html (landing page + Curated Picks)  │
                    │    → music-cities/index.html (daily feed)       │
                    │    → cities/*.html (17 city detail pages)       │
                    │    → map/ (residency map)                       │
                    └─────────────────────────────────────────────────┘
```

## PocketBase Collections (miny-database.exe.xyz)

| Collection | Records | Role |
|-----------|---------|------|
| `articles` | 34k+ | RSS-scraped music articles with location tags |
| `entities` | 11k+ | Artist/band entities extracted from articles |
| `_superusers` | 8 | Admin accounts |
| `users` | 21 | App users |
| `miny_applications` | 5 | y0 residency applications |
| `location_prospects` | 2 | Diplomatic prospects |
| `sm_musicians` | 1.3k | Separate musician directory (Strat by M) |

### Key `articles` fields
- `title`, `summary`, `source`, `source_url`, `primary_genre`
- `location` — city name (set by tag-articles-location.py)
- `artist_names` — JSON array of artist names
- `curated` (bool), `curator` (text), `curated_at` (date) — VE Curator
- `entity_ids` (json) — linked entity IDs
- `entity_rc_url` (text) — RapidConnect profile URL
- `epk_url`, `epk_status` — legacy EPK assignment

### Key `entities` fields
- `name`, `type` ("artist"), `artist`
- `article_ids` (json) — linked article IDs
- `mention_count`, `buzz_7d`, `buzz_30d`, `buzz_score`
- `city` — residency city
- `last_seen` (date)
- `rc_profile_url`, `rc_bio`, `rc_socials`, `rc_genres` — RapidConnect enrichment
- `rc_enriched` (bool), `rc_enriched_at` (date)

## Scripts

### VM scripts (/home/exedev/miny-ven/scraper/)

| Script | Schedule | Purpose |
|--------|----------|---------|
| `rss_scraper.py` | hourly :05 | Scrape 60+ RSS feeds → PocketBase articles |
| `tag-articles-location.py` | every 15min | Tag articles with city based on residency-aliases.yaml |
| `entity_tracker.py` | every 6h | Extract entities via Gemini → PocketBase entities |
| `generate_music_cities.py` | daily 13:00 UTC | Generate filtered feed HTML |
| `extract_feed_entities.py` | daily 13:02 UTC | Extract artists from feed articles via Ollama Cloud |
| `ve_curator.py` | daily 13:05 UTC | LLM curation (automated) + manual CLI |
| `enrich_directory.py` | daily 13:10 UTC | RapidConnect profile lookup via SearXNG |
| `add_pb_fields.py` | one-time | Schema migration script |

### Mac scripts

| Script | Schedule | Purpose |
|--------|----------|---------|
| `~/bin/deploy-music-cities.sh` | launchd 13:00 ET | Pull HTML from VM, supplement, deploy to Vercel |
| `x_supplement.py` | (in deploy script) | Search X via bird CLI for thin cities |
| `l30d_supplement.py` | (in deploy script) | Search last30days for 0-article cities |

### Cron (VM)

```
5  *  * * *  rss_scraper.py                          # hourly RSS
*/15 * * * *  tag-articles-location.py               # every 15 min
30 */6 * * *  entity_tracker.py --hours 72           # every 6h
0  13 * * *  y0-daily-pipeline.sh                    # daily pipeline
```

### Launchd (Mac)

```
com.velab.music-cities-daily.plist
  → 13:00 ET: deploy-music-cities.sh
```

## External Services

| Service | URL | Auth | Purpose |
|---------|-----|------|---------|
| Ollama Cloud | ollama.com/v1 | OLLAMA_API_KEY | LLM classification (gemma4:31b) |
| SearXNG | ve-code.exe.xyz/searxng | CRW_EDGE_TOKEN | Meta-search for thin city supplement + RC lookup |
| fastCRW | ve-code.exe.xyz/crw/v1 | CRW_EDGE_TOKEN | Web scraping (RC deep enrichment) |
| RapidConnect | rapidconnect.minyvinyl.com | none (public SPA) | Artist EPK profiles |
| Vercel | vercel.com | CLI token | Hosting for y0.minyvinyl.com |
| PocketBase | miny-database.exe.xyz | ARTICLES_PB_ADMIN_* | Articles + entities database |

## Config Files

| File | Location | Purpose |
|------|----------|---------|
| `residency-aliases.yaml` | `/home/exedev/tag-articles-location/` | 16 cities, 4 phases, aliases |
| `.env` | `/home/exedev/miny-ven/scraper/` | All credentials |
| `vercel.json` | miny-y0-landing repo | Vercel config |

## Repositories

| Repo | Purpose |
|------|---------|
| `collectivewinca/ven` | Scraper scripts, generator, curator, enricher |
| `collectivewinca/miny-y0-landing` | Static site (landing page, cities, map, feed) |

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Feed not updating | `ssh y0-minynet.exe.xyz "ls -la /home/exedev/miny-ven/music-cities.html"` — check mtime |
| LLM classification slow | Ollama Cloud may be rate-limited — check `logs/01-generate-*.log` |
| SearXNG returns empty | Brave engine may be suspended — try `engines=google,bing` |
| Curated badges missing | Run `ve_curator.py --list` to verify curated articles exist |
| Landing page wiped | Deploy script must use full repo dir, not just music-cities/ |
| PocketBase auth fails | Run `pb-superuser-unlock.sh` on VM (cron at :04) |