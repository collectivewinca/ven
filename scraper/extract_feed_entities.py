#!/usr/bin/env python3
"""
extract_feed_entities.py — Extract artist entities from feed-relevant articles.

Runs after generate_music_cities.py. Reads articles that have a city location
tag, uses Ollama Cloud to extract artist names, upserts to PocketBase entities
collection with city + article links.

Usage:
    python3 extract_feed_entities.py [--dry-run] [--limit N]
"""
from __future__ import annotations
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_FILE = Path("/home/exedev/miny-ven/scraper/.env")
LOOKBACK_HOURS = 36
LLM_MODEL = "gemma4:31b"
LLM_MAX_TOKENS = 1000
MAX_ENTITIES_PER_ARTICLE = 10

# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

PB_URL = os.getenv("ARTICLES_PB_URL", "https://miny-database.exe.xyz")
PB_EMAIL = os.getenv("ARTICLES_PB_ADMIN_EMAIL", "admin@miny-ven.local")
PB_PASSWORD = os.getenv("ARTICLES_PB_ADMIN_PASSWORD", "")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

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

def pb_query_articles(token, lookback_hours: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d %H:%M:%S")
    flt = urllib.parse.quote(f'location != "" && published_at > "{cutoff}"')
    fields = "id,title,summary,source,source_url,primary_genre,location,artist_names,published_at,entity_ids"
    items = []
    page = 1
    while True:
        url = (f"{PB_URL}/api/collections/articles/records"
               f"?perPage=500&page={page}&filter={flt}&sort=-published_at&fields={fields}")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        items.extend(data.get("items", []))
        if page >= data.get("totalPages", 1):
            break
        page += 1
    return items

def pb_search_entity(token, name: str) -> dict | None:
    flt = urllib.parse.quote(f'name = "{name}"')
    url = f"{PB_URL}/api/collections/entities/records?filter={flt}&perPage=1"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    items = data.get("items", [])
    return items[0] if items else None

def pb_create_entity(token, name: str, city: str, article_id: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "name": name,
        "type": "artist",
        "city": city or "",
        "article_ids": [article_id],
        "mention_count": 1,
        "last_seen": now,
        "first_seen_at": now,
        "firebase_id": f"local-{int(time.time())}-{abs(hash(name)) % 10000}",
    }
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/entities/records",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return resp["id"]

def pb_update_entity(token, entity_id: str, article_id: str, city: str | None = None):
    entity = pb_search_entity_by_id(token, entity_id)
    if not entity:
        return
    article_ids = entity.get("article_ids", [])
    if isinstance(article_ids, str):
        article_ids = json.loads(article_ids) if article_ids else []
    if article_id not in article_ids:
        article_ids.append(article_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    patch = {
        "article_ids": article_ids,
        "mention_count": (entity.get("mention_count", 0) or 0) + 1,
        "last_seen": now,
    }
    if city and not entity.get("city"):
        patch["city"] = city
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/entities/records/{entity_id}",
        data=json.dumps(patch).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10).read()

def pb_search_entity_by_id(token, entity_id: str) -> dict | None:
    url = f"{PB_URL}/api/collections/entities/records/{entity_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except:
        return None

def pb_link_entities_to_article(token, article_id: str, entity_ids: list[str]):
    patch = {"entity_ids": entity_ids}
    req = urllib.request.Request(
        f"{PB_URL}/api/collections/articles/records/{article_id}",
        data=json.dumps(patch).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10).read()

# ---------------------------------------------------------------------------
# LLM entity extraction
# ---------------------------------------------------------------------------

def llm_extract_artists(title: str, summary: str, city: str) -> list[str]:
    if not OLLAMA_API_KEY:
        return []
    prompt = (
        f"Extract all artist/band names mentioned in this music article.\n"
        f"Return ONLY a JSON array of strings. No explanation, no markdown.\n\n"
        f"Article:\nTitle: {title}\nCity: {city}\nSummary: {summary}\n\n"
        f'Return format: ["Artist Name 1", "Artist Name 2"]'
    )
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        "https://ollama.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {OLLAMA_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
        content = resp["choices"][0]["message"]["content"].strip()
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            artists = json.loads(match.group(0))
            return [a.strip() for a in artists if a.strip() and len(a.strip()) > 1]
    except Exception as e:
        sys.stderr.write(f"  [LLM] Error: {e}\n")
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
    print(f"[extract-entities] Authenticated to {PB_URL}")

    articles = pb_query_articles(token, LOOKBACK_HOURS)
    print(f"[extract-entities] Found {len(articles)} articles with location in last {LOOKBACK_HOURS}h")

    if limit:
        articles = articles[:limit]
        print(f"[extract-entities] Limited to {limit} articles")

    total_entities = 0
    for i, art in enumerate(articles):
        title = art.get("title", "")
        summary = art.get("summary", "")
        city = art.get("location", "")
        art_id = art["id"]

        existing_eids = art.get("entity_ids")
        if existing_eids and isinstance(existing_eids, list) and len(existing_eids) > 0:
            continue
        if existing_eids and isinstance(existing_eids, str) and existing_eids.strip() not in ("", "[]"):
            continue

        artists = llm_extract_artists(title, summary, city)

        if not artists:
            raw = art.get("artist_names")
            if raw:
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except:
                        raw = [raw]
                artists = [str(n) for n in raw if n and len(str(n)) > 1][:5]

        if not artists:
            continue

        print(f"  [{i+1}/{len(articles)}] {city}: {artists[:5]}")

        if dry_run:
            total_entities += len(artists)
            continue

        entity_ids = []
        for name in artists[:MAX_ENTITIES_PER_ARTICLE]:
            try:
                existing = pb_search_entity(token, name)
                if existing:
                    pb_update_entity(token, existing["id"], art_id, city)
                    entity_ids.append(existing["id"])
                else:
                    eid = pb_create_entity(token, name, city, art_id)
                    entity_ids.append(eid)
                total_entities += 1
            except Exception as e:
                sys.stderr.write(f"  [PB] Error upserting '{name}': {e}\n")

        if entity_ids:
            try:
                pb_link_entities_to_article(token, art_id, entity_ids)
            except Exception as e:
                sys.stderr.write(f"  [PB] Error linking to article: {e}\n")

        time.sleep(0.3)

    print(f"[extract-entities] Done. Extracted {total_entities} entity mentions.")
    if dry_run:
        print("[extract-entities] DRY RUN — no writes to PocketBase.")

if __name__ == "__main__":
    main()