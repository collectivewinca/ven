# VE Curator + Entity Directory Design

**Date:** 2026-06-26
**Status:** Approved (Approach B — Pipeline of Independent Scripts)

## Problem

The Music Cities Daily feed at y0.minyvinyl.com/music-cities/ surfaces articles but:
1. No entity extraction — artist names in articles aren't linked to a directory
2. No curation layer — all articles are treated equally, no "picks" highlighting
3. No bidirectional relationship — the feed doesn't enrich the directory and vice versa

## Solution

Three independent Python scripts running on y0-minynet VM, coordinated via PocketBase:

### 1. `extract_feed_entities.py` — Entity Extraction

**Purpose:** Extract artist entities from feed-relevant articles and link them to residency cities.

**Input:** Articles that passed the music-cities keyword filter (~54/day from `generate_music_cities.py`)
**Process:**
- Read the keyword-filtered article IDs from the generator's intermediate state
- For each article, use Ollama Cloud (gemma4:31b) to extract: artist names, album/track names, release type, genre
- Upsert each artist to PocketBase `entities` collection with:
  - `name`: artist name
  - `city`: residency city (from article's location tag)
  - `article_ids`: array of article IDs mentioning this artist
  - `last_seen`: timestamp
  - `mention_count`: incremented on each mention
- Link articles back: update `articles` collection with `entity_ids` array

**Schedule:** Runs after `generate_music_cities.py` in the same cron (13:00 UTC)
**Cost:** ~54 LLM calls/day (same articles already filtered by the generator)
**Output:** Entities collection gains city-tagged artist records linked to articles

### 2. `ve_curator.py` — VE Curator (Agent Plugin + CLI)

**Purpose:** Mark articles as "curated" with a curator name, like Founder's Pick on ven.

**Two modes:**

**Automated mode (cron):**
- Reads new articles from last 24h that have a city location tag
- LLM prompt: "Given these N music articles about [city], pick the 1-2 most newsworthy/important for a music residency audience. Return article IDs."
- Marks selected articles with `curated: true`, `curator: "VE Curator"`, `curated_at: timestamp`
- Caps at 5 total curated articles per day across all cities
- Avoids re-curating articles already curated

**CLI mode (manual override):**
```
python3 ve_curator.py --article <article-id> --curator "Alet"
python3 ve_curator.py --article <article-id> --uncurate
python3 ve_curator.py --list  # show today's curated
```

**Schedule:** Runs after entity extraction (13:05 UTC)
**Cost:** ~16 LLM calls/day (one per city with articles)
**PocketBase fields added to `articles`:** `curated` (bool), `curator` (string), `curated_at` (date)

### 3. `enrich_directory.py` — RapidConnect Enrichment

**Purpose:** Enrich entity records with artist info from RapidConnect, and build bidirectional links.

**Process:**
- Read entities that have a `city` tag but no `rc_enriched` flag
- For each entity, search RapidConnect by artist name
- Store in `entities` collection:
  - `rc_profile_url`: RapidConnect EPK URL
  - `rc_bio`: artist bio
  - `rc_socials`: { spotify, instagram, bandcamp, soundcloud }
  - `rc_genres`: genre tags from RC
  - `rc_enriched`: true
  - `rc_enriched_at`: timestamp
- Rate-limited: 5 artists per run (avoid RC API limits)
- Bidirectional: when an entity gets enriched, update linked articles with `entity_rc_url` for the "Discover Artist" link

**Schedule:** Runs daily at 13:10 UTC (after curation)
**Cost:** 5 RC API calls/day
**Output:** Artist directory entries with full profiles, articles with "Discover Artist" links

### 4. `generate_music_cities.py` Updates

The existing generator gets updated to:
- Read `curated` + `curator` fields from PocketBase
- Render a "★ Curated by [name]" badge on curated articles (same orange badge pattern as ven's Founder's Pick)
- Read `entity_rc_url` from linked entities and add "Discover Artist" links
- Add a "Curated Picks" section at the top of the feed page (above the city sections)

### 5. New: Curated Picks Section on y0 Landing Page

A new section on `y0.minyvinyl.com/` (index.html) showing today's curated articles:
- Generated as part of the music-cities deploy
- Shows 3-5 curated articles with title, city, curator badge, and link to full article
- Styled to match the existing y0 landing page aesthetic

## Data Flow

```
RSS Scraper (hourly)
    → PocketBase articles (34k+)
        → tag-articles-location.py (hourly)
            → City-tagged articles (6.1k)
                → generate_music_cities.py (daily 13:00 UTC)
                    → Keyword filter (~54 articles)
                        → LLM classification (~32 survive)
                            → music-cities.html (deployed to Vercel)
                        
                    → extract_feed_entities.py (daily 13:02 UTC)
                        → Ollama Cloud entity extraction (~54 calls)
                        → PocketBase entities (upsert with city + article links)
                        
                    → ve_curator.py (daily 13:05 UTC)
                        → LLM curation (~16 calls, picks top 1-2 per city)
                        → PocketBase articles (curated=true, curator="VE")
                        
                    → enrich_directory.py (daily 13:10 UTC)
                        → RapidConnect lookup (5 artists/day)
                        → PocketBase entities (rc_profile_url, bio, socials)
                        → PocketBase articles (entity_rc_url for Discover links)
                        
                    → generate_music_cities.py (re-run with curated + enriched data)
                        → Final HTML with curated badges + Discover Artist links
                        → Deploy to Vercel
```

## PocketBase Schema Changes

### `articles` collection — new fields:
| Field | Type | Description |
|-------|------|-------------|
| `curated` | bool | Whether this article is curated |
| `curator` | text | Who curated it ("VE Curator", "Alet", etc.) |
| `curated_at` | date | When it was curated |
| `entity_ids` | json | Array of entity IDs mentioned in this article |
| `entity_rc_url` | text | RapidConnect URL for the primary artist (for Discover link) |

### `entities` collection — new fields:
| Field | Type | Description |
|-------|------|-------------|
| `city` | text | Residency city this entity was mentioned in |
| `article_ids` | json | Array of article IDs mentioning this entity |
| `mention_count` | number | How many articles mention this artist |
| `last_seen` | date | Most recent article date |
| `rc_profile_url` | text | RapidConnect EPK URL |
| `rc_bio` | text | Artist bio from RapidConnect |
| `rc_socials` | json | { spotify, instagram, bandcamp, soundcloud } |
| `rc_genres` | json | Genre tags from RapidConnect |
| `rc_enriched` | bool | Whether RC enrichment has been done |
| `rc_enriched_at` | date | When RC enrichment was done |

## File Locations

| File | Location | Repo |
|------|----------|------|
| `extract_feed_entities.py` | `/home/exedev/miny-ven/scraper/` | collectivewinca/ven |
| `ve_curator.py` | `/home/exedev/miny-ven/scraper/` | collectivewinca/ven |
| `enrich_directory.py` | `/home/exedev/miny-ven/scraper/` | collectivewinca/ven |
| `generate_music_cities.py` | `/home/exedev/miny-ven/scraper/` (updated) | collectivewinca/ven |
| `music-cities/index.html` | deploy output | collectivewinca/miny-y0-landing |
| Cron wrapper | `/home/exedev/bin/y0-daily-pipeline.sh` | VM only |

## Cron Schedule (VM, UTC)

```
# Existing
0 * * * * /home/exedev/miny-ven/scraper/rss_scraper.py    # hourly RSS
0 * * * * /home/exedev/tag-articles-location/tag.py        # hourly tagger

# New daily pipeline
0 13 * * * /home/exedev/bin/y0-daily-pipeline.sh           # full pipeline
```

**y0-daily-pipeline.sh:**
```bash
#!/bin/bash
cd /home/exedev/miny-ven/scraper
python3 generate_music_cities.py          # 13:00 — generate feed
python3 extract_feed_entities.py          # 13:02 — extract entities
python3 ve_curator.py                     # 13:05 — curate
python3 enrich_directory.py               # 13:10 — enrich from RC
python3 generate_music_cities.py --final  # 13:15 — re-render with curated + enriched
```

The Mac launchd job (13:00 ET) pulls the final HTML and deploys to Vercel.

## Error Handling

- Each script writes to its own log file in `/home/exedev/miny-ven/logs/`
- If any script fails, the pipeline continues (non-blocking) — the feed still deploys without curation/enrichment
- Ollama Cloud failures: retry 3x with 2s backoff, then skip that article
- RapidConnect failures: skip that artist, try next run
- PocketBase write failures: log and continue

## Testing

- Each script has a `--dry-run` mode that shows what it would do without writing to PocketBase
- `ve_curator.py --list` shows current curated articles for verification
- `enrich_directory.py --stats` shows how many entities are enriched vs pending

## Rollout Order

1. **Phase 1:** Add PocketBase schema fields (articles + entities)
2. **Phase 2:** Build `extract_feed_entities.py` — test entity extraction
3. **Phase 3:** Build `ve_curator.py` — test curation (automated + CLI)
4. **Phase 4:** Update `generate_music_cities.py` — render curated badges
5. **Phase 5:** Build `enrich_directory.py` — test RC enrichment
6. **Phase 6:** Wire up cron pipeline + test end-to-end
7. **Phase 7:** Add Curated Picks section to y0 landing page