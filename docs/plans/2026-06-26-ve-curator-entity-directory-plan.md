# VE Curator + Entity Directory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a three-script pipeline that extracts artist entities from feed articles, curates the best ones daily via LLM, and enriches the artist directory with RapidConnect — all coordinated through PocketBase and rendered into the Music Cities Daily feed.

**Architecture:** Three independent Python scripts on y0-minynet VM, running as a sequential cron pipeline after the existing `generate_music_cities.py`. Each script reads from and writes to PocketBase collections. The generator is updated to render curated badges and "Discover Artist" links. A Curated Picks section is added to the y0 landing page.

**Tech Stack:** Python 3.12, PocketBase REST API, Ollama Cloud (gemma4:31b), RapidConnect API, static HTML, Vercel deploy

**Design doc:** `docs/plans/2026-06-26-ve-curator-entity-directory-design.md`

**Key files:**
- `scraper/generate_music_cities.py` — existing generator (661 lines), to be modified
- `scraper/ollama_client.py` — existing Ollama Cloud wrapper (use `chat()` function)
- `scraper/.env` — credentials (PB_ADMIN_EMAIL, PB_ADMIN_PASSWORD, PB_URL, OLLAMA_API_KEY, RC_API_KEY)
- `/home/exedev/tag-articles-location/residency-aliases.yaml` — city config

**Existing PocketBase schema (already present):**
- `articles`: has `curated` (bool), `curator` (text) — already added in a prior session
- `entities`: has `name`, `type`, `artist`, `article_ids` (json), `mention_count` (number), `genres` (json), `sources` (json)

**PocketBase fields to ADD:**
- `articles`: `curated_at` (date), `entity_ids` (json), `entity_rc_url` (text)
- `entities`: `city` (text), `last_seen` (date), `rc_profile_url` (text), `rc_bio` (text), `rc_socials` (json), `rc_genres` (json), `rc_enriched` (bool), `rc_enriched_at` (date)

---

## Task 1: Add PocketBase Schema Fields

**Files:**
- Create: `scraper/add_pb_fields.py`
- Repo: `collectivewinca/ven`

**Step 1: Write the schema migration script**

```python
#!/usr/bin/env python3
"""add_pb_fields.py — Add new fields to articles + entities collections in PocketBase."""
import json, os, urllib.request
from dotenv import load_dotenv
load_dotenv(Path("/home/exedev/miny-ven/scraper/.env"))

PB_URL = os.getenv("PB_URL", "http://miny-database.exe.xyz:8090")
PB_EMAIL = os.getenv("PB_ADMIN_EMAIL", "admin@miny-ven.local")
PB_PASSWORD = os.getenv("PB_ADMIN_PASSWORD", "")

def auth():
    data = json.dumps({"identity": PB_EMAIL, "password": PB_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["token"]

def patch_collection(token, collection_name, new_fields):
    # Get current schema
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/{collection_name}",
        headers={"Authorization": f"Bearer {token}"},
    )
    coll = json.loads(urllib.request.urlopen(req, timeout=10).read())
    # Merge fields
    existing_names = {f["name"] for f in coll["fields"]}
    for nf in new_fields:
        if nf["name"] not in existing_names:
            coll["fields"].append(nf)
    # PATCH
    req2 = urllib.request.Request(
        f"{PB_URL}/api/collections/{collection_name}",
        data=json.dumps(coll).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    resp = json.loads(urllib.request.urlopen(req2, timeout=10).read())
    print(f"  {collection_name}: added fields")

def main():
    token = auth()
    print(f"Authenticated to {PB_URL}")

    articles_fields = [
        {"name": "curated_at", "type": "date", "required": False},
        {"name": "entity_ids", "type": "json", "required": False},
        {"name": "entity_rc_url", "type": "text", "required": False},
    ]
    entities_fields = [
        {"name": "city", "type": "text", "required": False},
        {"name": "last_seen", "type": "date", "required": False},
        {"name": "rc_profile_url", "type": "text", "required": False},
        {"name": "rc_bio", "type": "text", "required": False},
        {"name": "rc_socials", "type": "json", "required": False},
        {"name": "rc_genres", "type": "json", "required": False},
        {"name": "rc_enriched", "type": "bool", "required": False},
        {"name": "rc_enriched_at", "type": "date", "required": False},
    ]

    patch_collection(token, "articles", articles_fields)
    patch_collection(token, "entities", entities_fields)
    print("Done.")

if __name__ == "__main__":
    main()
```

**Step 2: Deploy and run on VM**

```bash
scp scraper/add_pb_fields.py y0-minynet.exe.xyz:/home/exedev/miny-ven/scraper/
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 add_pb_fields.py"
```

Expected output: `articles: added fields` / `entities: added fields` / `Done.`

**Step 3: Verify fields exist**

```bash
ssh y0-minynet.exe.xyz "curl -s http://miny-database.exe.xyz:8090/api/collections/articles -H 'Authorization: Bearer <token>' | python3 -c 'import sys,json; [print(f[\"name\"]) for f in json.load(sys.stdin)[\"fields\"]]'"
```

Expected: `curated_at`, `entity_ids`, `entity_rc_url` visible in the articles schema.

**Step 4: Commit**

```bash
cd /tmp/ven-commit && git add scraper/add_pb_fields.py
git commit -m "feat(scraper): add PocketBase schema migration for entity + curation fields"
git push
```

---

## Task 2: Build `extract_feed_entities.py`

**Files:**
- Create: `scraper/extract_feed_entities.py`
- Repo: `collectivewinca/ven`

**Step 1: Write the entity extraction script**

```python
#!/usr/bin/env python3
"""
extract_feed_entities.py — Extract artist entities from feed-relevant articles.

Runs after generate_music_cities.py. Reads articles that passed the keyword
filter (the same ~54 articles the generator considers), uses Ollama Cloud
to extract artist names, and upserts them to PocketBase entities collection
with city + article links.

Usage:
    python3 extract_feed_entities.py [--dry-run] [--limit N]
"""
from __future__ import annotations
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# Load env
ENV_FILE = Path("/home/exedev/miny-ven/scraper/.env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

PB_URL = os.getenv("PB_URL", "http://miny-database.exe.xyz:8090")
PB_EMAIL = os.getenv("PB_ADMIN_EMAIL", "admin@miny-ven.local")
PB_PASSWORD = os.getenv("PB_ADMIN_PASSWORD", "")
LLM_MODEL = "gemma4:31b"
LLM_MAX_TOKENS = 1000
LOOKBACK_HOURS = 36

# ---------------------------------------------------------------------------
# PocketBase client
# ---------------------------------------------------------------------------

def pb_auth() -> str:
    data = json.dumps({"identity": PB_EMAIL, "password": PB_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["token"]

def pb_query(token, collection, filter_str, fields=None, per_page=500):
    params = [f"perPage={per_page}"]
    if filter_str:
        params.append(f"filter={urllib.parse.quote(filter_str)}")
    if fields:
        params.append(f"fields={fields}")
    url = f"{PB_URL}/api/collections/{collection}/records?{'&'.join(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    items = []
    page = 1
    while True:
        paginated_url = f"{url}&page={page}"
        req = urllib.request.Request(paginated_url, headers={"Authorization": f"Bearer {token}"})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        items.extend(data.get("items", []))
        if page >= data.get("totalPages", 1):
            break
        page += 1
    return items

def pb_upsert_entity(token, name, city, article_id):
    """Upsert an entity by name — create if not exists, update if it does."""
    # Search for existing entity by name
    flt = urllib.parse.quote(f'name = "{name}"')
    url = f"{PB_URL}/api/collections/entities/records?filter={flt}&perPage=1"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    items = data.get("items", [])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    if items:
        # Update existing
        entity = items[0]
        eid = entity["id"]
        article_ids = entity.get("article_ids", [])
        if isinstance(article_ids, str):
            article_ids = json.loads(article_ids) if article_ids else []
        if article_id not in article_ids:
            article_ids.append(article_id)
        patch_data = {
            "article_ids": article_ids,
            "mention_count": (entity.get("mention_count", 0) or 0) + 1,
            "last_seen": now,
        }
        if city and not entity.get("city"):
            patch_data["city"] = city
        req = urllib.request.Request(
            f"{PB_URL}/api/collections/entities/records/{eid}",
            data=json.dumps(patch_data).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="PATCH",
        )
        urllib.request.urlopen(req, timeout=10).read()
        return eid
    else:
        # Create new
        create_data = {
            "name": name,
            "type": "artist",
            "city": city or "",
            "article_ids": [article_id],
            "mention_count": 1,
            "last_seen": now,
            "first_seen_at": now,
            "firebase_id": f"local-{int(time.time())}-{hash(name) % 10000}",
        }
        req = urllib.request.Request(
            f"{PB_URL}/api/collections/entities/records",
            data=json.dumps(create_data).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return resp["id"]

def pb_update_article_entities(token, article_id, entity_ids):
    """Link entity IDs back to the article."""
    patch_data = {"entity_ids": entity_ids}
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/articles/records/{article_id}",
        data=json.dumps(patch_data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10).read()

# ---------------------------------------------------------------------------
# LLM entity extraction
# ---------------------------------------------------------------------------

def llm_extract_entities(title, summary, city):
    """Use Ollama Cloud to extract artist names from an article."""
    api_key = os.getenv("OLLAMA_API_KEY", "")
    if not api_key:
        return []

    prompt = f"""Extract all artist/band names mentioned in this music article.
Return ONLY a JSON array of strings. No explanation, no markdown.

Article:
Title: {title}
City: {city}
Summary: {summary}

Return format: ["Artist Name 1", "Artist Name 2"]"""

    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        "https://ollama.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        content = resp["choices"][0]["message"]["content"].strip()
        # Parse JSON array from response
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            artists = json.loads(match.group(0))
            return [a.strip() for a in artists if a.strip() and len(a.strip()) > 1]
    except Exception as e:
        sys.stderr.write(f"  [LLM] Error extracting entities: {e}\n")
    return []

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dry_run = "--dry-run" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    print(f"[extract-entities] Starting at {datetime.now(timezone.utc).isoformat()}")

    token = pb_auth()
    print(f"[extract-entities] Authenticated to PocketBase")

    # Query articles with location in lookback window (same as generator)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    flt = f'location != "" && published_at > "{cutoff}"'
    fields = "id,title,summary,source,source_url,primary_genre,location,artist_names,published_at"
    articles = pb_query(token, "articles", flt, fields)
    print(f"[extract-entities] Found {len(articles)} articles with location in last {LOOKBACK_HOURS}h")

    if limit:
        articles = articles[:limit]
        print(f"[extract-entities] Limited to {limit} articles")

    # Extract entities from each article
    total_entities = 0
    for i, art in enumerate(articles):
        title = art.get("title", "")
        summary = art.get("summary", "")
        city = art.get("location", "")
        art_id = art["id"]

        # Skip if already has entity_ids
        existing = art.get("entity_ids")
        if existing and isinstance(existing, list) and len(existing) > 0:
            continue

        # Use LLM to extract artist names
        artists = llm_extract_entities(title, summary, city)

        if not artists:
            # Fallback: use artist_names field if present
            raw_names = art.get("artist_names")
            if raw_names:
                if isinstance(raw_names, str):
                    raw_names = json.loads(raw_names)
                artists = [str(n) for n in raw_names if n and len(str(n)) > 1][:5]

        if not artists:
            continue

        print(f"  [{i+1}/{len(articles)}] {city}: {artists}")

        if dry_run:
            total_entities += len(artists)
            continue

        # Upsert each artist to entities collection
        entity_ids = []
        for name in artists[:10]:  # Cap at 10 entities per article
            try:
                eid = pb_upsert_entity(token, name, city, art_id)
                entity_ids.append(eid)
                total_entities += 1
            except Exception as e:
                sys.stderr.write(f"  [PB] Error upserting entity '{name}': {e}\n")

        # Link entity IDs back to article
        if entity_ids:
            try:
                pb_update_article_entities(token, art_id, entity_ids)
            except Exception as e:
                sys.stderr.write(f"  [PB] Error linking entities to article: {e}\n")

        time.sleep(0.3)  # Rate limit LLM calls

    print(f"[extract-entities] Done. Extracted {total_entities} entity mentions.")
    if dry_run:
        print("[extract-entities] DRY RUN — no writes to PocketBase.")

if __name__ == "__main__":
    from datetime import timedelta
    main()
```

**Step 2: Deploy to VM and test with dry-run**

```bash
scp scraper/extract_feed_entities.py y0-minynet.exe.xyz:/home/exedev/miny-ven/scraper/
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 extract_feed_entities.py --dry-run --limit 5"
```

Expected: prints `Found N articles` and shows extracted artist names without writing to PocketBase.

**Step 3: Run for real on a small batch**

```bash
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 extract_feed_entities.py --limit 10"
```

Expected: `Done. Extracted N entity mentions.` with no errors.

**Step 4: Verify entities in PocketBase**

```bash
ssh y0-minynet.exe.xyz "curl -s 'http://miny-database.exe.xyz:8090/api/collections/entities/records?filter=city!=\"\"&perPage=5' -H 'Authorization: Bearer <token>' | python3 -c 'import sys,json; [print(e[\"name\"], e.get(\"city\",\"\"), e.get(\"mention_count\",0)) for e in json.load(sys.stdin)[\"items\"]]'" 
```

Expected: shows entity records with city tags and mention counts.

**Step 5: Commit**

```bash
cd /tmp/ven-commit && git add scraper/extract_feed_entities.py
git commit -m "feat(scraper): entity extraction from feed-relevant articles"
git push
```

---

## Task 3: Build `ve_curator.py`

**Files:**
- Create: `scraper/ve_curator.py`
- Repo: `collectivewinca/ven`

**Step 1: Write the curation script**

```python
#!/usr/bin/env python3
"""
ve_curator.py — VE Curator: automated + manual article curation.

Automated mode (default):
    Reads new city-tagged articles from last 24h, uses LLM to pick the
    1-2 most newsworthy per city (max 5 total/day), marks them curated.

CLI mode:
    python3 ve_curator.py --article <id> --curator "Alet"
    python3 ve_curator.py --article <id> --uncurate
    python3 ve_curator.py --list
    python3 ve_curator.py --run            # force automated run
"""
from __future__ import annotations
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

ENV_FILE = Path("/home/exedev/miny-ven/scraper/.env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

PB_URL = os.getenv("PB_URL", "http://miny-database.exe.xyz:8090")
PB_EMAIL = os.getenv("PB_ADMIN_EMAIL", "admin@miny-ven.local")
PB_PASSWORD = os.getenv("PB_ADMIN_PASSWORD", "")
LLM_MODEL = "gemma4:31b"
LLM_MAX_TOKENS = 800
LOOKBACK_HOURS = 24
MAX_CURATED_PER_DAY = 5
MAX_PER_CITY = 2

# ---------------------------------------------------------------------------
# PocketBase client
# ---------------------------------------------------------------------------

def pb_auth() -> str:
    data = json.dumps({"identity": PB_EMAIL, "password": PB_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["token"]

def pb_query(token, collection, filter_str, fields=None, per_page=500):
    params = [f"perPage={per_page}"]
    if filter_str:
        params.append(f"filter={urllib.parse.quote(filter_str)}")
    if fields:
        params.append(f"fields={fields}")
    base_url = f"{PB_URL}/api/collections/{collection}/records?{'&'.join(params)}"
    items = []
    page = 1
    while True:
        url = f"{base_url}&page={page}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        items.extend(data.get("items", []))
        if page >= data.get("totalPages", 1):
            break
        page += 1
    return items

def pb_mark_curated(token, article_id, curator_name):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    patch = {"curated": True, "curator": curator_name, "curated_at": now}
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/articles/records/{article_id}",
        data=json.dumps(patch).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10).read()

def pb_uncurate(token, article_id):
    patch = {"curated": False, "curator": "", "curated_at": None}
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/articles/records/{article_id}",
        data=json.dumps(patch).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10).read()

# ---------------------------------------------------------------------------
# LLM curation
# ---------------------------------------------------------------------------

def llm_pick_articles(articles, city_name):
    """Ask LLM to pick the most newsworthy articles for a city."""
    api_key = os.getenv("OLLAMA_API_KEY", "")
    if not api_key:
        return []

    # Format articles for the prompt
    lines = []
    for i, art in enumerate(articles):
        lines.append(f"[{i}] {art.get('title','')} — {art.get('source','')} — {art.get('summary','')[:200]}")
    
    prompt = f"""You are a music editor for a global music residency program in {city_name}.
From these music articles, pick the {MAX_PER_CITY} most newsworthy/important ones
for a music industry audience (not just fans — think A&R, promoters, venue bookers).

Return ONLY a JSON array of index numbers. Example: [0, 3]

Articles:
{chr(10).join(lines)}"""

    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        "https://ollama.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        content = resp["choices"][0]["message"]["content"].strip()
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            indices = json.loads(match.group(0))
            return [articles[i] for i in indices if 0 <= i < len(articles)]
    except Exception as e:
        sys.stderr.write(f"  [LLM] Curation error for {city_name}: {e}\n")
    return []

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_run(dry_run=False):
    """Automated curation run."""
    token = pb_auth()
    print(f"[curator] Starting automated curation at {datetime.now(timezone.utc).isoformat()}")

    # Check how many already curated today
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    flt_today = f'curated = true && curated_at >= "{today} 00:00:00"'
    already_curated = pb_query(token, "articles", flt_today, "id")
    slots_left = MAX_CURATED_PER_DAY - len(already_curated)
    print(f"[curator] Already curated today: {len(already_curated)} / {MAX_CURATED_PER_DAY} — {slots_left} slots left")

    if slots_left <= 0:
        print("[curator] Daily curation cap reached. Done.")
        return

    # Query city-tagged articles from last 24h, not already curated
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    flt = f'location != "" && published_at > "{cutoff}" && curated != true'
    fields = "id,title,summary,source,source_url,primary_genre,location,published_at"
    articles = pb_query(token, "articles", flt, fields)
    print(f"[curator] Found {len(articles)} uncurated city-tagged articles")

    # Group by city
    by_city = defaultdict(list)
    for art in articles:
        by_city[art.get("location", "")].append(art)

    curated_count = 0
    for city, city_arts in sorted(by_city.items()):
        if curated_count >= slots_left:
            break
        if not city or len(city_arts) < 1:
            continue

        picks = llm_pick_articles(city_arts[:20], city)  # Limit to top 20 per city for LLM
        picks = picks[:MAX_PER_CITY]  # Cap at 2 per city

        for pick in picks:
            if curated_count >= slots_left:
                break
            art_id = pick["id"]
            title = pick.get("title", "")[:80]
            print(f"  [curate] {city}: {title}")

            if not dry_run:
                pb_mark_curated(token, art_id, "VE Curator")
            curated_count += 1
            time.sleep(0.3)

    print(f"[curator] Done. Curated {curated_count} articles (cap: {MAX_CURATED_PER_DAY}).")
    if dry_run:
        print("[curator] DRY RUN — no writes to PocketBase.")

def cmd_article_curate(article_id, curator_name):
    """Manually curate a single article."""
    token = pb_auth()
    pb_mark_curated(token, article_id, curator_name)
    print(f"[curator] Article {article_id} curated by {curator_name}")

def cmd_uncurate(article_id):
    """Remove curation from an article."""
    token = pb_auth()
    pb_uncurate(token, article_id)
    print(f"[curator] Article {article_id} uncurated")

def cmd_list():
    """List today's curated articles."""
    token = pb_auth()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    flt = f'curated = true && curated_at >= "{today} 00:00:00"'
    items = pb_query(token, "articles", flt, "id,title,source,location,curator,curated_at")
    print(f"Curated articles for {today} ({len(items)}):")
    for item in items:
        print(f"  {item['id'][:12]}  {item.get('curator','?'):12s}  {item.get('location',''):15s}  {item.get('title','')[:60]}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if "--list" in sys.argv:
        cmd_list()
    elif "--article" in sys.argv:
        article_id = sys.argv[sys.argv.index("--article") + 1]
        if "--uncurate" in sys.argv:
            cmd_uncurate(article_id)
        else:
            curator = "Manual"
            if "--curator" in sys.argv:
                curator = sys.argv[sys.argv.index("--curator") + 1]
            cmd_article_curate(article_id, curator)
    elif "--run" in sys.argv or len(sys.argv) == 1:
        dry = "--dry-run" in sys.argv
        cmd_run(dry)
    else:
        print("Usage: ve_curator.py [--run] [--dry-run] | --article <id> [--curator NAME] [--uncurate] | --list")

if __name__ == "__main__":
    main()
```

**Step 2: Deploy and test dry-run**

```bash
scp scraper/ve_curator.py y0-minynet.exe.xyz:/home/exedev/miny-ven/scraper/
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 ve_curator.py --dry-run"
```

Expected: prints which articles it would curate per city without writing.

**Step 3: Run for real**

```bash
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 ve_curator.py --run"
```

Expected: `Done. Curated N articles (cap: 5).`

**Step 4: Verify with --list**

```bash
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 ve_curator.py --list"
```

Expected: shows curated articles with curator "VE Curator".

**Step 5: Test manual override**

```bash
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 ve_curator.py --article <some-id> --curator 'Alet'"
```

Expected: `Article <id> curated by Alet`

**Step 6: Commit**

```bash
cd /tmp/ven-commit && git add scraper/ve_curator.py
git commit -m "feat(scraper): VE Curator — automated + manual article curation"
git push
```

---

## Task 4: Update `generate_music_cities.py` — Curated Badges + Discover Links

**Files:**
- Modify: `scraper/generate_music_cities.py` (on VM + in ven repo)
- Specifically the `query_articles` method and `render_html` function

**Step 1: Update query_articles to fetch curated + entity fields**

In `query_articles`, change the `fields` parameter to include curated fields:

```python
# OLD:
fields = "id,title,summary,source,source_url,primary_genre,location,artist_names,published_at"

# NEW:
fields = "id,title,summary,source,source_url,primary_genre,location,artist_names,published_at,curated,curator,entity_rc_url"
```

**Step 2: Update render_html to show curated badge**

In `render_html`, inside the article loop, add curated badge:

```python
# OLD:
articles_html.append(
    f'<div class="article"><a href="{url}" target="_blank" rel="noopener">{title}</a>'
    f'<div class="meta">{source}{genre_html}</div></div>'
)

# NEW:
curated_html = ""
if art.get("curated"):
    curator = escape(art.get("curator", ""))
    curated_html = f'<span class="curated-badge">★ {curator}</span>'
articles_html.append(
    f'<div class="article">{curated_html}<a href="{url}" target="_blank" rel="noopener">{title}</a>'
    f'<div class="meta">{source}{genre_html}</div></div>'
)
```

**Step 3: Add CSS for curated badge**

In the `<style>` block, add:

```css
.curated-badge {{ display:inline-block; padding:1px 8px; background:linear-gradient(to right,#f97316,#ea580c); color:#fff; border-radius:99px; font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; margin-right:6px; font-family:var(--sans); }}
```

**Step 4: Add a Curated Picks section at the top**

Before the phase sections, add a curated picks block:

```python
# In render_html, before the phase loop:
curated_articles = []
for phase_key in phase_order:
    for city in city_config["cities_by_phase"].get(phase_key, []):
        for art in grouped.get(city["name"], []):
            if art.get("curated"):
                curated_articles.append(art)

curated_html = ""
if curated_articles:
    picks_items = []
    for art in curated_articles[:5]:
        title = escape(art.get("title", "")[:200])
        url = escape(art.get("source_url", ""))
        source = escape(art.get("source", ""))
        curator = escape(art.get("curator", "VE Curator"))
        picks_items.append(
            f'<div class="pick"><a href="{url}" target="_blank" rel="noopener">{title}</a>'
            f'<div class="pick-meta">★ {curator} · {source}</div></div>'
        )
    curated_html = (
        '<section class="picks-block">'
        '<p class="picks-label">Curated Picks</p>'
        f'{"".join(picks_items)}</section>'
    )
```

Add CSS:
```css
.picks-block {{ margin:0 0 40px; padding:24px; background:var(--hint); border-radius:12px; }}
.picks-label {{ font-family:var(--sans); font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:var(--accent); font-weight:600; margin:0 0 16px; }}
.pick {{ padding:8px 0; border-bottom:1px solid var(--rule); }}
.pick:last-child {{ border-bottom:none; }}
.pick a {{ color:var(--ink); text-decoration:none; font-weight:600; }}
.pick a:hover {{ text-decoration:underline; }}
.pick-meta {{ font-family:var(--sans); font-size:11px; color:var(--muted); margin-top:2px; }}
```

**Step 5: Deploy and test**

```bash
scp scraper/generate_music_cities.py y0-minynet.exe.xyz:/home/exedev/miny-ven/scraper/
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 generate_music_cities.py --no-searxng"
```

Expected: feed shows curated badges on articles and a Curated Picks section at top.

**Step 6: Commit**

```bash
cd /tmp/ven-commit && git add scraper/generate_music_cities.py
git commit -m "feat(scraper): curated badges + Curated Picks section in music-cities feed"
git push
```

---

## Task 5: Build `enrich_directory.py`

**Files:**
- Create: `scraper/enrich_directory.py`
- Repo: `collectivewinca/ven`

**Step 1: Write the enrichment script**

```python
#!/usr/bin/env python3
"""
enrich_directory.py — Enrich entity records with RapidConnect artist data.

Reads entities that have a city tag but no RC enrichment, searches
RapidConnect for the artist, and stores bio/socials/genres back in PocketBase.

Usage:
    python3 enrich_directory.py [--dry-run] [--limit N] [--stats]
"""
from __future__ import annotations
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENV_FILE = Path("/home/exedev/miny-ven/scraper/.env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

PB_URL = os.getenv("PB_URL", "http://miny-database.exe.xyz:8090")
PB_EMAIL = os.getenv("PB_ADMIN_EMAIL", "admin@miny-ven.local")
PB_PASSWORD = os.getenv("PB_ADMIN_PASSWORD", "")
RC_API_KEY = os.getenv("RC_API_KEY", os.getenv("RAPIDCONNECT_API_KEY", ""))
RC_BASE_URL = "https://rapidconnect.minyvinyl.com"
MAX_PER_RUN = 5

# ---------------------------------------------------------------------------
# PocketBase
# ---------------------------------------------------------------------------

def pb_auth() -> str:
    data = json.dumps({"identity": PB_EMAIL, "password": PB_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/_superusers/auth-with-password",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["token"]

def pb_query(token, collection, filter_str, fields=None):
    params = [f"perPage=500"]
    if filter_str:
        params.append(f"filter={urllib.parse.quote(filter_str)}")
    if fields:
        params.append(f"fields={fields}")
    url = f"{PB_URL}/api/collections/{collection}/records?{'&'.join(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return data.get("items", [])

def pb_patch_entity(token, entity_id, patch_data):
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/entities/records/{entity_id}",
        data=json.dumps(patch_data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10).read()

def pb_patch_article(token, article_id, patch_data):
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/articles/records/{article_id}",
        data=json.dumps(patch_data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10).read()

# ---------------------------------------------------------------------------
# RapidConnect
# ---------------------------------------------------------------------------

def rc_search_artist(artist_name):
    """Search RapidConnect for an artist and return profile data."""
    if not RC_API_KEY:
        return None

    # Search by name
    search_url = f"{RC_BASE_URL}/api/search?q={urllib.parse.quote(artist_name)}"
    req = urllib.request.Request(search_url, headers={
        "Authorization": f"Bearer {RC_API_KEY}",
        "Accept": "application/json",
    })
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        results = data.get("results", data.get("artists", []))
        if not results:
            return None
        # Take best match
        artist = results[0]
        return {
            "profile_url": artist.get("url", artist.get("profile_url", "")),
            "bio": artist.get("bio", ""),
            "socials": {
                "spotify": artist.get("spotify_url", ""),
                "instagram": artist.get("instagram_url", ""),
                "bandcamp": artist.get("bandcamp_url", ""),
                "soundcloud": artist.get("soundcloud_url", ""),
            },
            "genres": artist.get("genres", []),
        }
    except Exception as e:
        sys.stderr.write(f"  [RC] Error searching {artist_name}: {e}\n")
        return None

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dry_run = "--dry-run" in sys.argv
    stats_only = "--stats" in sys.argv
    limit = MAX_PER_RUN
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    token = pb_auth()
    print(f"[enrich] Starting at {datetime.now(timezone.utc).isoformat()}")

    # Get stats
    flt_pending = 'city != "" && (rc_enriched = false || rc_enriched = null)'
    pending = pb_query(token, "entities", flt_pending, "id,name,city,article_ids")
    flt_done = 'rc_enriched = true'
    done = pb_query(token, "entities", flt_done, "id,name")
    print(f"[enrich] Stats: {len(done)} enriched, {len(pending)} pending")

    if stats_only:
        return

    if not pending:
        print("[enrich] Nothing to enrich. Done.")
        return

    enriched = 0
    for entity in pending[:limit]:
        name = entity.get("name", "")
        city = entity.get("city", "")
        eid = entity["id"]
        print(f"  [{enriched+1}/{min(limit, len(pending))}] Enriching: {name} ({city})")

        rc_data = rc_search_artist(name)
        if not rc_data:
            print(f"    → Not found on RapidConnect")
            if not dry_run:
                pb_patch_entity(token, eid, {
                    "rc_enriched": True,
                    "rc_enriched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                })
            enriched += 1
            continue

        print(f"    → Found: {rc_data['profile_url']}")

        if not dry_run:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            pb_patch_entity(token, eid, {
                "rc_profile_url": rc_data["profile_url"],
                "rc_bio": rc_data["bio"][:2000],
                "rc_socials": rc_data["socials"],
                "rc_genres": rc_data["genres"],
                "rc_enriched": True,
                "rc_enriched_at": now,
            })

            # Update linked articles with RC URL for "Discover Artist" link
            article_ids = entity.get("article_ids", [])
            if isinstance(article_ids, str):
                article_ids = json.loads(article_ids) if article_ids else []
            for art_id in article_ids[:5]:
                try:
                    pb_patch_article(token, art_id, {"entity_rc_url": rc_data["profile_url"]})
                except Exception as e:
                    sys.stderr.write(f"    [PB] Error linking article {art_id}: {e}\n")

        enriched += 1
        time.sleep(1)  # Rate limit RC API

    print(f"[enrich] Done. Enriched {enriched} entities.")
    if dry_run:
        print("[enrich] DRY RUN — no writes to PocketBase.")

if __name__ == "__main__":
    main()
```

**Step 2: Deploy and check stats**

```bash
scp scraper/enrich_directory.py y0-minynet.exe.xyz:/home/exedev/miny-ven/scraper/
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 enrich_directory.py --stats"
```

Expected: shows how many entities are enriched vs pending.

**Step 3: Run dry-run on a few**

```bash
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 enrich_directory.py --dry-run --limit 3"
```

Expected: shows which artists it would search for on RapidConnect.

**Step 4: Run for real**

```bash
ssh y0-minynet.exe.xyz "cd /home/exedev/miny-ven/scraper && python3 enrich_directory.py --limit 5"
```

Expected: `Done. Enriched 5 entities.`

**Step 5: Commit**

```bash
cd /tmp/ven-commit && git add scraper/enrich_directory.py
git commit -m "feat(scraper): RapidConnect directory enrichment for entities"
git push
```

---

## Task 6: Wire Cron Pipeline + End-to-End Test

**Files:**
- Create: `/home/exedev/bin/y0-daily-pipeline.sh` (VM only)

**Step 1: Write the pipeline wrapper script**

```bash
#!/usr/bin/env bash
# y0-daily-pipeline.sh — Full y0 daily pipeline (runs on VM at 13:00 UTC)
set -uo pipefail
cd /home/exedev/miny-ven/scraper

LOGDIR="/home/exedev/miny-ven/logs"
mkdir -p "$LOGDIR"
DATE=$(date -u +%Y-%m-%d)

echo "[pipeline] Starting $DATE at $(date -u +%H:%M:%S UTC)"

# Step 1: Generate feed (keyword + LLM filter)
echo "[pipeline] Step 1: Generate music-cities feed..."
python3 generate_music_cities.py 2>&1 | tee "$LOGDIR/01-generate-$DATE.log"

# Step 2: Extract entities from feed-relevant articles
echo "[pipeline] Step 2: Extract entities..."
python3 extract_feed_entities.py 2>&1 | tee "$LOGDIR/02-entities-$DATE.log"

# Step 3: Curate top articles
echo "[pipeline] Step 3: Curate articles..."
python3 ve_curator.py --run 2>&1 | tee "$LOGDIR/03-curate-$DATE.log"

# Step 4: Enrich directory from RapidConnect
echo "[pipeline] Step 4: Enrich directory..."
python3 enrich_directory.py 2>&1 | tee "$LOGDIR/04-enrich-$DATE.log"

# Step 5: Re-render feed with curated + enriched data
echo "[pipeline] Step 5: Final render..."
python3 generate_music_cities.py 2>&1 | tee "$LOGDIR/05-final-$DATE.log"

echo "[pipeline] Complete at $(date -u +%H:%M:%S UTC)"
```

**Step 2: Install on VM**

```bash
scp /tmp/y0-daily-pipeline.sh y0-minynet.exe.xyz:/home/exedev/bin/
ssh y0-minynet.exe.xyz "chmod +x /home/exedev/bin/y0-daily-pipeline.sh"
```

**Step 3: Update crontab**

```bash
ssh y0-minynet.exe.xyz "crontab -l" > /tmp/current-crontab.txt
# Replace the existing generate-music-cities cron with the full pipeline
# OLD: 0 13 * * * /home/exedev/bin/generate-music-cities.sh
# NEW: 0 13 * * * /home/exedev/bin/y0-daily-pipeline.sh
```

**Step 4: Run end-to-end test**

```bash
ssh y0-minynet.exe.xyz "/home/exedev/bin/y0-daily-pipeline.sh"
```

Expected: all 5 steps complete, final HTML written to `/home/exedev/miny-ven/music-cities.html`.

**Step 5: Pull and deploy**

```bash
scp y0-minynet.exe.xyz:/home/exedev/miny-ven/music-cities.html /tmp/miny-y0-landing-restore/music-cities/index.html
cd /tmp/miny-y0-landing-restore && vercel deploy --prod --yes
```

Expected: Vercel deploy succeeds, `y0.minyvinyl.com/music-cities/` shows curated badges + picks section.

**Step 6: Verify**

```bash
curl -s https://y0.minyvinyl.com/music-cities/ | grep -o "Curated Picks\|curated-badge\|★" | head -5
```

Expected: shows curated content on the live page.

---

## Task 7: Add Curated Picks Section to y0 Landing Page

**Files:**
- Modify: `index.html` in `collectivewinca/miny-y0-landing` repo
- Create: `js/curated-picks.js` (fetches curated articles from PocketBase)

**Step 1: Write curated-picks.js**

A small script that fetches today's curated articles from PocketBase and renders them in a section on the y0 landing page:

```javascript
// curated-picks.js — Fetch today's curated articles and render in landing page
(async function() {
  const PB_URL = 'https://miny-database.exe.xyz:8090'; // or proxy
  const today = new Date().toISOString().split('T')[0];
  const filter = encodeURIComponent(`curated = true && curated_at >= "${today} 00:00:00"`);
  const fields = 'id,title,summary,source,location,curator,source_url';
  
  try {
    const res = await fetch(`${PB_URL}/api/collections/articles/records?filter=${filter}&perPage=5&fields=${fields}&sort=-curated_at`);
    const data = await res.json();
    const container = document.getElementById('curated-picks');
    if (!container || !data.items || data.items.length === 0) return;
    
    container.innerHTML = data.items.map(a => `
      <div class="curated-card">
        <span class="curated-badge">★ ${a.curator || 'VE Curator'}</span>
        <a href="${a.source_url}" target="_blank" rel="noopener">${a.title}</a>
        <div class="curated-meta">${a.location || ''} · ${a.source}</div>
      </div>
    `).join('');
    container.style.display = 'block';
  } catch (e) {
    console.log('Curated picks unavailable:', e);
  }
})();
```

**Step 2: Add curated picks section to index.html**

Insert before the "How It Works" section in index.html:

```html
<section id="curated-picks" class="curated-section" style="display:none;">
  <h2>Today's Curated Picks</h2>
  <p class="curated-subtitle">Hand-picked music news from our VE Curator</p>
</section>
<script src="/js/curated-picks.js"></script>
```

**Step 3: Add CSS**

In the existing `<style>` block or a new `<link>`:

```css
.curated-section { max-width: 760px; margin: 48px auto; padding: 0 24px; }
.curated-section h2 { font-family: var(--sans); font-size: 24px; font-weight: 700; }
.curated-subtitle { color: #6b6557; font-style: italic; margin-bottom: 24px; }
.curated-card { padding: 16px 0; border-bottom: 1px solid #e3e3dd; }
.curated-badge { display: inline-block; padding: 2px 8px; background: linear-gradient(to right, #f97316, #ea580c); color: #fff; border-radius: 99px; font-size: 10px; font-weight: 600; text-transform: uppercase; margin-right: 8px; }
.curated-card a { color: #181715; text-decoration: none; font-weight: 600; font-size: 16px; }
.curated-card a:hover { text-decoration: underline; }
.curated-meta { font-size: 12px; color: #6b6557; margin-top: 4px; font-family: var(--sans); }
```

**Step 4: Deploy and verify**

```bash
cd /tmp/miny-y0-landing-restore && vercel deploy --prod --yes
```

Verify: `curl -s https://y0.minyvinyl.com/ | grep "curated-picks"` — section should be present (hidden until JS loads data).

**Step 5: Commit**

```bash
cd /tmp/miny-y0-landing-restore && git add index.html js/curated-picks.js
git commit -m "feat: add Curated Picks section to y0 landing page"
git push origin main
```

---

## Summary

| Task | Script/Action | Effort | Depends On |
|------|---------------|--------|------------|
| 1 | Add PB schema fields | small | — |
| 2 | `extract_feed_entities.py` | medium | 1 |
| 3 | `ve_curator.py` | medium | 1 |
| 4 | Update `generate_music_cities.py` | small | 1, 3 |
| 5 | `enrich_directory.py` | medium | 1, 2 |
| 6 | Wire cron + e2e test | small | 2, 3, 4, 5 |
| 7 | Curated Picks on landing page | small | 3 |

Tasks 2 and 3 can be built in parallel (both depend only on Task 1). Task 4 depends on 1+3. Task 5 depends on 1+2. Task 6 depends on all. Task 7 depends on 3.