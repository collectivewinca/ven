#!/usr/bin/env python3
"""
enrich_directory.py — Enrich entity records with RapidConnect artist data.

Reads entities that have a city tag but no RC enrichment, searches
RapidConnect (via SearXNG) for the artist, stores profile URL back in
PocketBase. Bidirectional: also links the RC URL to the article.

Usage:
    python3 enrich_directory.py [--dry-run] [--limit N] [--stats]
"""
from __future__ import annotations
import json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENV_FILE = Path("/home/exedev/miny-ven/scraper/.env")
MAX_PER_RUN = 5
SEARXNG_URL = "https://ve-code.exe.xyz/searxng/search"

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
SEARXNG_TOKEN = os.getenv("CRW_EDGE_TOKEN", "")

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

def pb_query_entities(token, filter_str, fields=None):
    params = [f"perPage=500"]
    if filter_str:
        params.append(f"filter={urllib.parse.quote(filter_str)}")
    if fields:
        params.append(f"fields={fields}")
    url = f"{PB_URL}/api/collections/entities/records?{'&'.join(params)}"
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
# SearXNG search for RapidConnect profiles
# ---------------------------------------------------------------------------

def search_rc_profile(artist_name):
    """Search SearXNG for a RapidConnect artist profile + extract bio/genres from content."""
    if not SEARXNG_TOKEN:
        return None

    query = f"site:rapidconnect.minyvinyl.com/artists {artist_name}"
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "engines": "brave",
        "pageno": 1,
    })
    url = f"{SEARXNG_URL}?{params}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {SEARXNG_TOKEN}",
        "Accept": "application/json",
    })
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        results = resp.get("results", [])
        for r in results:
            link = r.get("url", "")
            if "rapidconnect.minyvinyl.com/artists/" in link:
                content = r.get("content", "")
                data = {
                    "profile_url": link,
                    "title": r.get("title", ""),
                    "bio": content[:2000] if content else "",
                }
                # Extract genres from content (pattern: "genres of X, Y, and Z" or "known for ... in the genres of X, Y")
                import re as _re
                genre_match = _re.search(r'genres? of ([^.]+)', content, _re.I)
                if genre_match:
                    genres_raw = genre_match.group(1).strip().rstrip('.')
                    data["genres"] = [g.strip() for g in _re.split(r'[,/]', genres_raw) if g.strip() and len(g.strip()) > 2 and g.strip() not in ("and", "the", "of")]
                else:
                    data["genres"] = []
                # Extract socials from content (URLs in the content field)
                socials = {}
                if "spotify.com" in content:
                    m = _re.search(r'(https?://open\.spotify\.com/[^\s"]+)', content)
                    if m: socials["spotify"] = m.group(1)
                if "instagram.com" in content:
                    m = _re.search(r'(https?://(?:www\.)?instagram\.com/[^\s"]+)', content)
                    if m: socials["instagram"] = m.group(1)
                if "bandcamp.com" in content:
                    m = _re.search(r'(https?://[^\s"]+\.bandcamp\.com[^\s"]*)', content)
                    if m: socials["bandcamp"] = m.group(1)
                if "soundcloud.com" in content:
                    m = _re.search(r'(https?://soundcloud\.com/[^\s"]+)', content)
                    if m: socials["soundcloud"] = m.group(1)
                data["socials"] = socials
                return data
    except Exception as e:
        sys.stderr.write(f"  [SearXNG] Error: {e}\n")
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

    # Stats
    pending = pb_query_entities(token, 'city != "" && (rc_enriched = false || rc_enriched = null)',
                                "id,name,city,article_ids")
    done = pb_query_entities(token, 'rc_enriched = true', "id,name")
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

        rc_data = search_rc_profile(name)
        if not rc_data:
            print(f"    -> Not found on RapidConnect")
            if not dry_run:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                pb_patch_entity(token, eid, {
                    "rc_enriched": True,
                    "rc_enriched_at": now,
                })
            enriched += 1
            continue

        profile_url = rc_data["profile_url"]
        bio = rc_data.get("bio", "")
        genres = rc_data.get("genres", [])
        socials = rc_data.get("socials", {})
        print(f"    -> Found: {profile_url}")
        if bio:
            print(f"    -> Bio: {bio[:100]}...")
        if genres:
            print(f"    -> Genres: {genres}")

        if not dry_run:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            patch = {
                "rc_profile_url": profile_url,
                "rc_bio": bio[:2000],
                "rc_genres": genres,
                "rc_socials": socials,
                "rc_enriched": True,
                "rc_enriched_at": now,
            }
            pb_patch_entity(token, eid, patch)

            # Link RC URL to articles
            article_ids = entity.get("article_ids", [])
            if isinstance(article_ids, str):
                try:
                    article_ids = json.loads(article_ids) if article_ids else []
                except:
                    article_ids = []
            for art_id in article_ids[:5]:
                try:
                    pb_patch_article(token, art_id, {"entity_rc_url": profile_url})
                except Exception as e:
                    sys.stderr.write(f"    [PB] Error linking article {art_id}: {e}\n")

        enriched += 1
        time.sleep(1)

    print(f"[enrich] Done. Enriched {enriched} entities.")
    if dry_run:
        print("[enrich] DRY RUN — no writes.")

if __name__ == "__main__":
    main()