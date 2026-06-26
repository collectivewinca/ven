#!/usr/bin/env python3
"""
generate_music_cities.py — Music Cities Daily generator

Reads articles from PocketBase (miny-database.exe.xyz), filters for music
relevance, deduplicates by URL, caps per-source per-city, targets 5-10
stories per city, renders static HTML matching the existing editorial
design, and deploys to Vercel.

Cron: daily at 9 AM ET (13:00 UTC) on y0-minynet.exe.xyz
"""

from __future__ import annotations
import json
import os
import re
import sys
import hashlib
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from html import escape
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_FILE = Path("/home/exedev/miny-ven/scraper/.env")
YAML_PATH = Path("/home/exedev/tag-articles-location/residency-aliases.yaml")
OUTPUT_HTML = Path("/home/exedev/miny-ven/music-cities.html")
MAX_PER_CITY = 10
MIN_PER_CITY = 3
MAX_PER_SOURCE_PER_CITY = 3
LOOKBACK_HOURS = 24

# Non-music keywords — if any appear in title/summary, the article is dropped
NON_MUSIC_BLOCKLIST = [
    "earthquake", "tsunami", "medical emergency", "blood donation",
    "baseball", "basketball", "football", "soccer", "hockey",
    "gators demolish", "super regionals", "hurricane",
    "drug trafficking", "money laundering", "arrest",
    "election", "political rally", "campaign",
    "restaurant review", "food guide", "travel guide",
    "medical emergency in japan", "survival guide",
]

# Music relevance keywords — at least one must appear somewhere
MUSIC_KEYWORDS = [
    "music", "album", "single", "ep", "track", "song", "artist",
    "band", "tour", "concert", "festival", "live show", "gig",
    "dj", "producer", "rapper", "singer", "guitarist", "drummer",
    "label", "signing", "release", "debut", "vinyl", "streaming",
    "spotify", "soundcloud", "bandcamp", "apple music", "tidal",
    "grammy", "billboard", "chart", "playlist", "mixtape",
    "venue", "stage", "performance", "setlist", "opener",
    "collaboration", "featuring", "feat", "remix", "cover",
    "genre", "rock", "pop", "hip-hop", "hiphop", "rap", "jazz",
    "electronic", "edm", "house", "techno", "indie", "folk",
    "country", "gospel", "r&b", "rnb", "soul", "funk", "reggae",
    "metal", "punk", "classical", "opera", "blues", "ambient",
    "k-pop", "j-pop", "latin", "reggaeton", "bachata", "salsa",
    "dj set", "live set", "b2b", "headliner", "support act",
    "announce", "reveal", "drop", "return", "hiatus", "reunion",
    "acm", "cma", "roskilde", "ade", "coachella", "lollapalooza",
]

# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------

def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

# ---------------------------------------------------------------------------
# PocketBase client
# ---------------------------------------------------------------------------

class PocketBase:
    def __init__(self, base_url: str, email: str, password: str):
        self.base = base_url.rstrip("/")
        self.token = self._auth(email, password)

    def _auth(self, email: str, password: str) -> str:
        url = f"{self.base}/api/collections/_superusers/auth-with-password"
        body = json.dumps({"identity": email, "password": password}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["token"]

    def query_articles(self, lookback_hours: int) -> list[dict]:
        """Fetch articles with location set, published within lookback."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours + 12)).strftime("%Y-%m-%d %H:%M:%S")
        flt = urllib.parse.quote(f'location != "" && published_at > "{cutoff}"')
        fields = "id,title,summary,source,source_url,primary_genre,location,artist_names,published_at"

        all_items = []
        page = 1
        while True:
            url = (f"{self.base}/api/collections/articles/records"
                   f"?perPage=500&page={page}&filter={flt}&sort=-published_at&fields={fields}")
            req = urllib.request.Request(url, headers={"Authorization": self.token})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            all_items.extend(data.get("items", []))
            if page >= data.get("totalPages", 1):
                break
            page += 1
        return all_items

# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def build_haystack(article: dict) -> str:
    """Lowercased text of title + summary for keyword matching."""
    parts = [
        article.get("title") or "",
        article.get("summary") or "",
    ]
    return " ".join(parts).lower()

def has_non_music_content(haystack: str) -> bool:
    for kw in NON_MUSIC_BLOCKLIST:
        if kw in haystack:
            return True
    return False

def has_music_content(haystack: str) -> bool:
    for kw in MUSIC_KEYWORDS:
        if kw in haystack:
            return True
    return False

def canonical_url(url: str) -> str:
    """Strip tracking params, normalize for dedup."""
    parsed = urllib.parse.urlsplit(url)
    # Keep only essential params, strip utm_*, fbclid, etc
    qs = urllib.parse.parse_qs(parsed.query)
    clean = {k: v for k, v in qs.items() if not k.startswith("utm_") and k not in ("fbclid", "ref", "source")}
    query = urllib.parse.urlencode(clean, doseq=True)
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))

def filter_articles(articles: list[dict]) -> list[dict]:
    """Apply relevance + dedup + per-source-cap filters."""
    seen_urls = set()
    source_city_counts = defaultdict(int)
    result = []

    for art in articles:
        title = art.get("title") or ""
        summary = art.get("summary") or ""
        source = art.get("source") or ""
        source_url = art.get("source_url") or ""
        location = art.get("location") or ""

        if not location or not source_url:
            continue

        haystack = build_haystack(art)

        # 1. Drop non-music
        if has_non_music_content(haystack):
            continue

        # 2. Require music relevance
        if not has_music_content(haystack):
            continue

        # 3. Dedup by canonical URL
        canon = canonical_url(source_url)
        if canon in seen_urls:
            continue
        seen_urls.add(canon)

        # 4. Per-source per-city cap
        key = (source, location)
        if source_city_counts[key] >= MAX_PER_SOURCE_PER_CITY:
            continue
        source_city_counts[key] += 1

        result.append(art)

    return result

# ---------------------------------------------------------------------------
# City grouping + phase ordering
# ---------------------------------------------------------------------------

def load_city_config(yaml_path: Path) -> dict:
    """Load residency-aliases.yaml and build phase → cities mapping."""
    try:
        import yaml
    except ImportError:
        sys.stderr.write("Missing pyyaml\n")
        sys.exit(2)

    data = yaml.safe_load(yaml_path.read_text())

    phases = {}
    for phase_key, phase_info in data.get("phases", {}).items():
        if not phase_info.get("active", True):
            continue
        phase_num = phase_key.replace("phase_", "")
        phases[phase_key] = {
            "num": phase_num,
            "name": phase_info.get("name", ""),
            "description": phase_info.get("description", "").strip(),
        }

    cities_by_phase = defaultdict(list)
    city_names = set()
    for city in data.get("cities", []):
        name = city["name"]
        phase = city["phase"]
        city_names.add(name)
        cities_by_phase[phase].append({
            "name": name,
            "slug": city["slug"],
            "aliases": city.get("aliases", []),
        })

    return {
        "phases": phases,
        "cities_by_phase": dict(cities_by_phase),
        "city_names": city_names,
    }

def group_by_city(articles: list[dict], city_config: dict) -> dict:
    """Group articles by city, capped at MAX_PER_CITY."""
    by_city = defaultdict(list)
    for art in articles:
        loc = art.get("location", "")
        if loc in city_config["city_names"]:
            by_city[loc].append(art)

    # Cap per city
    capped = {}
    for city, arts in by_city.items():
        capped[city] = arts[:MAX_PER_CITY]
    return capped

# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_html(city_config: dict, grouped: dict, date_str: str, total_count: int) -> str:
    """Render the music cities daily page as static HTML."""

    phase_order = ["phase_1", "phase_2", "phase_3", "phase_4"]
    phase_labels = {
        "phase_1": "1", "phase_2": "2", "phase_3": "3", "phase_4": "4",
    }

    sections_html = []
    for phase_key in phase_order:
        if phase_key not in city_config["phases"]:
            continue
        phase = city_config["phases"][phase_key]
        cities = city_config["cities_by_phase"].get(phase_key, [])

        city_blocks = []
        for city in cities:
            name = city["name"]
            arts = grouped.get(name, [])
            if not arts:
                continue

            articles_html = []
            for art in arts:
                title = escape(art.get("title", "")[:200])
                url = escape(art.get("source_url", ""))
                source = escape(art.get("source", ""))
                genre = escape(art.get("primary_genre", ""))
                genre_html = f'<span class="genre">{genre}</span>' if genre else ""
                articles_html.append(
                    f'<div class="article"><a href="{url}" target="_blank" rel="noopener">{title}</a>'
                    f'<div class="meta">{source}{genre_html}</div></div>'
                )

            city_blocks.append(
                f'<div class="city"><h3>{escape(name)} <span class="count">\u00b7 {len(arts)}</span></h3>'
                f'{"".join(articles_html)}</div>'
            )

        if not city_blocks:
            continue

        sections_html.append(
            f'<section class="phase-block">'
            f'<p class="phase-label">phase {phase_labels.get(phase_key, "")}</p>'
            f'<h2 class="phase-title">{escape(phase["name"])}</h2>'
            f'<p class="phase-desc">{escape(phase["description"])}</p>'
            f'{"".join(city_blocks)}</section>'
        )

    body_sections = "".join(sections_html)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Music Cities Daily \u2014 {date_str}</title>
<meta name="description" content="Music news across the MINY y0 Residency cities \u2014 daily digest.">
<style>
:root {{
  --ink:#181715; --paper:#fafaf7; --muted:#6b6557; --rule:#e3e3dd;
  --accent:#b54124; --hint:#f3eee4; --serif:'Iowan Old Style','Charter',Georgia,serif;
  --sans:'Inter','Helvetica Neue',Arial,sans-serif;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font-family:var(--serif); font-size:17px; line-height:1.55; }}
.wrap {{ max-width:760px; margin:0 auto; padding:48px 24px 80px; }}
.eyebrow {{ font-family:var(--sans); font-size:11px; letter-spacing:0.22em; text-transform:uppercase; color:var(--accent); font-weight:600; margin:0 0 12px; }}
h1 {{ font-weight:700; font-size:38px; line-height:1.1; margin:0 0 8px; letter-spacing:-0.01em; }}
.dek {{ font-style:italic; color:var(--muted); font-size:18px; margin:0 0 32px; }}
.phase-block {{ margin:48px 0 0; padding-top:24px; border-top:1px solid var(--rule); }}
.phase-block:first-of-type {{ border-top:none; padding-top:0; }}
.phase-label {{ font-family:var(--sans); font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:var(--muted); margin:0 0 4px; font-weight:600; }}
.phase-title {{ font-weight:700; font-size:24px; margin:0 0 4px; }}
.phase-desc {{ font-style:italic; color:var(--muted); font-size:14px; margin:0 0 24px; }}
.city {{ margin:24px 0; }}
.city h3 {{ font-family:var(--sans); font-weight:700; font-size:13px; text-transform:uppercase; letter-spacing:0.12em; margin:0 0 10px; color:var(--ink); }}
.city h3 .count {{ color:var(--muted); font-weight:400; }}
.article {{ padding:8px 0; border-bottom:1px solid var(--rule); }}
.article:last-child {{ border-bottom:none; }}
.article a {{ color:var(--ink); text-decoration:none; }}
.article a:hover {{ text-decoration:underline; text-decoration-color:var(--accent); text-decoration-thickness:2px; }}
.meta {{ font-family:var(--sans); font-size:11.5px; color:var(--muted); letter-spacing:0.04em; }}
.genre {{ display:inline-block; padding:1px 7px; background:var(--hint); border-radius:99px; color:var(--accent); font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; margin-left:6px; }}
footer {{ margin-top:64px; padding-top:20px; border-top:2px solid var(--ink); font-family:var(--sans); font-size:12px; color:var(--muted); }}
footer a {{ color:var(--accent); text-decoration:none; }}
.empty {{ font-style:italic; color:var(--muted); font-size:14px; }}
</style>
</head>
<body>
<div class="wrap">
<p class="eyebrow">MINY \u00b7 y0 Residency</p>
<h1>Music Cities Daily</h1>
<p class="dek">{date_str} \u00b7 {total_count} stories across the residency cities</p>
{body_sections}
<footer>
Updated daily 9 AM ET \u00b7 <a href="https://freeintelligence.ai/">Free Intelligence</a>
</footer>
</div>
</body>
</html>"""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"[music-cities] Starting generation at {datetime.now(timezone.utc).isoformat()}")

    # Load env
    env = load_env(ENV_FILE)
    pb_url = env.get("POCKETBASE_URL", "https://miny-database.exe.xyz")
    pb_email = env.get("POCKETBASE_ADMIN_EMAIL", "")
    pb_pw = env.get("POCKETBASE_ADMIN_PASSWORD", "")

    if not pb_email or not pb_pw:
        print("[music-cities] ERROR: Missing PocketBase credentials")
        sys.exit(1)

    # Load city config
    city_config = load_city_config(YAML_PATH)
    print(f"[music-cities] Loaded {len(city_config['city_names'])} cities across {len(city_config['phases'])} phases")

    # Query PocketBase
    print(f"[music-cities] Querying articles from last {LOOKBACK_HOURS}h...")
    pb = PocketBase(pb_url, pb_email, pb_pw)
    articles = pb.query_articles(LOOKBACK_HOURS)
    print(f"[music-cities] Found {len(articles)} articles with location in lookback window")

    # Filter
    filtered = filter_articles(articles)
    print(f"[music-cities] After filtering: {len(filtered)} articles")

    # Group by city
    grouped = group_by_city(filtered, city_config)
    total_displayed = sum(len(arts) for arts in grouped.values())
    cities_with_content = len(grouped)
    print(f"[music-cities] {total_displayed} articles across {cities_with_content} cities")

    # Date label
    now_et = datetime.now(timezone.utc) - timedelta(hours=4)  # EDT = UTC-4
    date_str = now_et.strftime("%B %-d, %Y")

    # Render
    html = render_html(city_config, grouped, date_str, total_displayed)
    OUTPUT_HTML.write_text(html)
    print(f"[music-cities] Wrote {len(html)} bytes to {OUTPUT_HTML}")

    # Summary
    for city, arts in sorted(grouped.items()):
        sources = set(a.get("source", "") for a in arts)
        print(f"  {city}: {len(arts)} articles from {len(sources)} sources")

if __name__ == "__main__":
    main()