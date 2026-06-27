#!/usr/bin/env python3
"""
ve_curator.py — VE Curator: automated + manual article curation.

Automated mode (default or --run):
    Reads new city-tagged articles from last 24h, uses LLM to pick the
    1-2 most newsworthy per city (max 5 total/day), marks them curated.

CLI mode:
    python3 ve_curator.py --article <id> --curator "Alet"
    python3 ve_curator.py --article <id> --uncurate
    python3 ve_curator.py --list
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
LOOKBACK_HOURS = 24
LLM_MODEL = "gemma4:31b"
LLM_MAX_TOKENS = 800
MAX_CURATED_PER_DAY = 5
MAX_PER_CITY = 2

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

def pb_query(token, filter_str, fields=None, per_page=500):
    params = [f"perPage={per_page}"]
    if filter_str:
        params.append(f"filter={urllib.parse.quote(filter_str)}")
    if fields:
        params.append(f"fields={fields}")
    base = f"{PB_URL}/api/collections/articles/records?{'&'.join(params)}"
    items = []
    page = 1
    while True:
        url = f"{base}&page={page}&sort=-published_at"
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
    if not OLLAMA_API_KEY:
        return []

    lines = []
    for i, art in enumerate(articles):
        lines.append(f"[{i}] {art.get('title','')} — {art.get('source','')} — {art.get('summary','')[:200]}")

    prompt = (
        f"You are a music editor for a global music residency program in {city_name}.\n"
        f"From these music articles, pick the {MAX_PER_CITY} most newsworthy/important ones "
        f"for a music industry audience (A&R, promoters, venue bookers).\n\n"
        f"Return ONLY a JSON array of index numbers. Example: [0, 3]\n\n"
        f"Articles:\n{chr(10).join(lines)}"
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
            indices = json.loads(match.group(0))
            return [articles[i] for i in indices if isinstance(i, int) and 0 <= i < len(articles)]
    except Exception as e:
        sys.stderr.write(f"  [LLM] Curation error for {city_name}: {e}\n")
    return []

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_run(dry_run=False):
    token = pb_auth()
    print(f"[curator] Starting automated curation at {datetime.now(timezone.utc).isoformat()}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    already = pb_query(token, f'curated = true && curated_at >= "{today} 00:00:00"', "id")
    slots_left = MAX_CURATED_PER_DAY - len(already)
    print(f"[curator] Already curated today: {len(already)} / {MAX_CURATED_PER_DAY} — {slots_left} slots left")

    if slots_left <= 0:
        print("[curator] Daily cap reached. Done.")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    flt = f'location != "" && published_at > "{cutoff}" && curated != true'
    fields = "id,title,summary,source,source_url,primary_genre,location,published_at"
    articles = pb_query(token, flt, fields)
    print(f"[curator] Found {len(articles)} uncurated city-tagged articles")

    by_city = defaultdict(list)
    for art in articles:
        loc = art.get("location", "")
        if loc:
            by_city[loc].append(art)

    curated_count = 0
    for city, city_arts in sorted(by_city.items()):
        if curated_count >= slots_left:
            break
        if not city or len(city_arts) < 1:
            continue

        picks = llm_pick_articles(city_arts[:20], city)
        picks = picks[:MAX_PER_CITY]

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
        print("[curator] DRY RUN — no writes.")

def cmd_article_curate(article_id, curator_name):
    token = pb_auth()
    pb_mark_curated(token, article_id, curator_name)
    print(f"[curator] Article {article_id} curated by {curator_name}")

def cmd_uncurate(article_id):
    token = pb_auth()
    pb_uncurate(token, article_id)
    print(f"[curator] Article {article_id} uncurated")

def cmd_list():
    token = pb_auth()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    flt = f'curated = true && curated_at >= "{today} 00:00:00"'
    items = pb_query(token, flt, "id,title,source,location,curator,curated_at")
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