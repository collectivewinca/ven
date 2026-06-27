#!/usr/bin/env python3
"""
generate_music_cities.py — Music Cities Daily generator (v2)

Pipeline:
  1. Query PocketBase for articles with location in last 24h
  2. Keyword pre-filter (blocklist + allowlist)
  3. LLM classification (glm-5.2 via Ollama Cloud) — is it music? is it about the city?
  4. LLM event-location extraction — override source-based location if LLM disagrees
  5. Deduplicate by canonical URL
  6. Cap per-source per-city at 3
  7. Supplement thin cities (<3 articles) via SearXNG discovery + LLM filtering
  8. Group by city, cap at 10 per city
  9. Render static HTML
  10. Write to output file

Flags:
  --no-llm     Skip LLM classification (keyword-only filter, for debugging)
  --no-searxng Skip SearXNG thin-city supplementation

Cron: daily at 9 AM ET (13:00 UTC) on y0-minynet.exe.xyz
"""

from __future__ import annotations
import json
import os
import re
import sys
import time
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
LLM_MODEL = "gemma4:31b"
LLM_MAX_TOKENS = 2000
LLM_TIMEOUT = 60

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
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours + 12)).strftime("%Y-%m-%d %H:%M:%S")
        flt = urllib.parse.quote(f'location != "" && published_at > "{cutoff}"')
        fields = "id,title,summary,source,source_url,primary_genre,location,artist_names,published_at,curated,curator,entity_rc_url"

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
# LLM client (Ollama Cloud, OpenAI-compatible)
# ---------------------------------------------------------------------------

class LLMClient:
    """Thin wrapper around Ollama Cloud's OpenAI-compatible endpoint."""

    def __init__(self, api_key: str, model: str = LLM_MODEL):
        self.url = "https://ollama.com/v1/chat/completions"
        self.api_key = api_key
        self.model = model
        self.call_count = 0

    def chat(self, prompt: str, max_tokens: int = LLM_MAX_TOKENS) -> str:
        """Send a single-turn prompt, return the assistant text content."""
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }).encode()

        req = urllib.request.Request(self.url, data=body, headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
                data = json.loads(r.read())
            self.call_count += 1
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else ""
        except Exception as e:
            print(f"  [LLM] Error: {e}")
            return ""

    def classify_music_relevance(self, title: str, summary: str, city: str) -> bool:
        """Return True if the LLM says this is a music story about the city."""
        prompt = (
            f"Is this article primarily about music or a music event that is happening "
            f"in or relevant to {city}? Reply only YES or NO.\n"
            f"Title: {title}\nSummary: {summary[:300]}"
        )
        resp = self.chat(prompt)
        return resp.upper().startswith("YES")

    def extract_event_location(self, title: str, summary: str, city_names: list[str]) -> str:
        """Ask the LLM which residency city the event is happening in."""
        cities_str = ", ".join(city_names)
        prompt = (
            f"Which of these cities is this music event primarily happening in? "
            f"Reply with ONLY the city name from this list, or NONE if none apply.\n"
            f"Cities: {cities_str}\n"
            f"Title: {title}\nSummary: {summary[:300]}"
        )
        resp = self.chat(prompt)
        # Match response against city names (case-insensitive)
        resp_clean = resp.strip().strip(".").strip()
        for name in city_names:
            if name.lower() == resp_clean.lower():
                return name
        return ""

# ---------------------------------------------------------------------------
# SearXNG discovery (thin-press city supplementation)
# ---------------------------------------------------------------------------

class SearXNGClient:
    """Query the self-hosted SearXNG meta-search for city-specific music news."""

    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.token = token

    def search_music(self, city_name: str, year: int) -> list[dict]:
        """Search for recent music news about a city."""
        query = f"{city_name} music artist album tour concert festival {year}"
        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "categories": "news",
            "time_range": "week",
            "safesearch": 0,
        })
        url = f"{self.base}/search?{params}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "miny-ven/1.0",
        })

        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            return data.get("results", [])[:10]
        except Exception as e:
            print(f"  [SearXNG] Error searching {city_name}: {e}")
            return []

# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def build_haystack(article: dict) -> str:
    parts = [article.get("title") or "", article.get("summary") or ""]
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
    parsed = urllib.parse.urlsplit(url)
    qs = urllib.parse.parse_qs(parsed.query)
    clean = {k: v for k, v in qs.items()
             if not k.startswith("utm_") and k not in ("fbclid", "ref", "source")}
    query = urllib.parse.urlencode(clean, doseq=True)
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))

def keyword_filter(articles: list[dict]) -> list[dict]:
    """Stage 1: keyword pre-filter (blocklist + allowlist + dedup + per-source cap)."""
    seen_urls = set()
    source_city_counts = defaultdict(int)
    result = []

    for art in articles:
        title = art.get("title") or ""
        source = art.get("source") or ""
        source_url = art.get("source_url") or ""
        location = art.get("location") or ""

        if not location or not source_url:
            continue

        haystack = build_haystack(art)

        if has_non_music_content(haystack):
            continue
        if not has_music_content(haystack):
            continue

        canon = canonical_url(source_url)
        if canon in seen_urls:
            continue
        seen_urls.add(canon)

        key = (source, location)
        if source_city_counts[key] >= MAX_PER_SOURCE_PER_CITY:
            continue
        source_city_counts[key] += 1

        result.append(art)

    return result

def llm_filter(articles: list[dict], llm: LLMClient) -> list[dict]:
    """Stage 2: LLM classification — is it music? is it about the city?"""
    result = []
    for i, art in enumerate(articles):
        title = art.get("title") or ""
        summary = art.get("summary") or ""
        location = art.get("location") or ""

        is_music = llm.classify_music_relevance(title, summary, location)
        if is_music:
            result.append(art)
        else:
            print(f"  [LLM] Dropped: [{location}] {title[:60]}")

    return result

def llm_relocate(articles: list[dict], llm: LLMClient, city_names: list[str]) -> list[dict]:
    """Stage 3: LLM event-location extraction — override source-based location."""
    result = []
    city_names_sorted = sorted(city_names, key=len, reverse=True)

    for art in articles:
        title = art.get("title") or ""
        summary = art.get("summary") or ""
        current_loc = art.get("location") or ""

        llm_loc = llm.extract_event_location(title, summary, city_names_sorted)
        if llm_loc and llm_loc != current_loc:
            print(f"  [LLM] Relocated: {current_loc} -> {llm_loc} | {title[:50]}")
            art = dict(art)
            art["location"] = llm_loc
        result.append(art)

    return result

def filter_articles(articles: list[dict], llm: LLMClient | None = None,
                    do_relocate: bool = False, all_city_names: list[str] | None = None) -> list[dict]:
    """Full filter pipeline: keyword → LLM → (optional relocate) → dedup → per-source cap."""
    # Stage 1: keyword pre-filter
    kw_filtered = keyword_filter(articles)
    print(f"[music-cities] After keyword filter: {len(kw_filtered)} articles")

    # Stage 2: LLM classification (optional)
    if llm:
        print(f"[music-cities] Running LLM classification on {len(kw_filtered)} articles...")
        llm_filtered = llm_filter(kw_filtered, llm)
        print(f"[music-cities] After LLM filter: {len(llm_filtered)} articles (LLM calls: {llm.call_count})")

        # Stage 3: LLM event-location extraction (optional, off by default — doubles LLM calls)
        if do_relocate and all_city_names:
            print(f"[music-cities] Running LLM location extraction on {len(llm_filtered)} articles...")
            relocated = llm_relocate(llm_filtered, llm, all_city_names)
        else:
            relocated = llm_filtered
    else:
        relocated = kw_filtered

    # Re-apply per-source cap after relocation (location may have changed)
    seen_urls = set()
    source_city_counts = defaultdict(int)
    result = []
    for art in relocated:
        canon = canonical_url(art.get("source_url", ""))
        if canon in seen_urls:
            continue
        seen_urls.add(canon)
        source = art.get("source", "")
        location = art.get("location", "")
        key = (source, location)
        if source_city_counts[key] >= MAX_PER_SOURCE_PER_CITY:
            continue
        source_city_counts[key] += 1
        result.append(art)

    return result

# ---------------------------------------------------------------------------
# Thin-press city supplementation
# ---------------------------------------------------------------------------

def supplement_thin_cities(grouped: dict, city_config: dict, searxng: SearXNGClient,
                           llm: LLMClient, year: int) -> dict:
    """For cities with < MIN_PER_CITY articles, search SearXNG and LLM-filter results."""
    for phase_key, cities in city_config["cities_by_phase"].items():
        for city in cities:
            name = city["name"]
            current_count = len(grouped.get(name, []))
            if current_count >= MIN_PER_CITY:
                continue

            needed = MIN_PER_CITY - current_count
            print(f"[music-cities] Supplementing {name} ({current_count} articles, need {needed} more)...")

            results = searxng.search_music(name, year)
            if not results:
                continue

            added = 0
            seen_urls = {canonical_url(a.get("source_url", "")) for arts in grouped.values() for a in arts}

            for r in results[:5]:  # Only check top 5 results to limit LLM calls
                if added >= needed:
                    break

                title = r.get("title", "")
                url = r.get("url", "")
                if not title or not url:
                    continue

                canon = canonical_url(url)
                if canon in seen_urls:
                    continue

                # LLM classify: is it music + about this city?
                if llm.classify_music_relevance(title, "", name):
                    seen_urls.add(canon)
                    grouped.setdefault(name, []).append({
                        "title": title,
                        "source": "SearXNG Discovery",
                        "source_url": url,
                        "primary_genre": "",
                        "location": name,
                        "artist_names": [],
                        "published_at": "",
                    })
                    added += 1
                    print(f"  [SearXNG] Added: {title[:60]}")

            print(f"[music-cities] {name}: supplemented {added} articles")

    return grouped

# ---------------------------------------------------------------------------
# City grouping + phase ordering
# ---------------------------------------------------------------------------

def load_city_config(yaml_path: Path) -> dict:
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
        phases[phase_key] = {
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
    by_city = defaultdict(list)
    for art in articles:
        loc = art.get("location", "")
        if loc in city_config["city_names"]:
            by_city[loc].append(art)

    capped = {}
    for city, arts in by_city.items():
        capped[city] = arts[:MAX_PER_CITY]
    return capped

# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_html(city_config: dict, grouped: dict, date_str: str, total_count: int) -> str:
    phase_order = ["phase_1", "phase_2", "phase_3", "phase_4"]

    sections_html = []

    # Curated Picks section
    curated_picks = []
    for phase_key in phase_order:
        if phase_key not in city_config["phases"]:
            continue
        for city in city_config["cities_by_phase"].get(phase_key, []):
            for art in grouped.get(city["name"], []):
                if art.get("curated"):
                    curated_picks.append(art)
    curated_section = ""
    if curated_picks:
        picks_items = []
        for art in curated_picks[:5]:
            title = escape(art.get("title", "")[:200])
            url = escape(art.get("source_url", ""))
            source = escape(art.get("source", ""))
            curator = escape(art.get("curator", "VE Curator"))
            picks_items.append(
                f'<div class="pick"><a href="{url}" target="_blank" rel="noopener">{title}</a>'
                f'<div class="pick-meta">★ {curator} · {source}</div></div>'
            )
        curated_section = (
            '<section class="picks-block">'
            '<p class="picks-label">Curated Picks</p>'
            f'{"".join(picks_items)}</section>'
        )

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
                curated_html = ""
                if art.get("curated"):
                    curator = escape(art.get("curator", "VE Curator"))
                    curated_html = f'<span class="curated-badge">★ {curator}</span>'
                articles_html.append(
                    f'<div class="article">{curated_html}<a href="{url}" target="_blank" rel="noopener">{title}</a>'
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
            f'<p class="phase-label">phase {phase_key.replace("phase_","")}</p>'
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
.curated-badge {{ display:inline-block; padding:1px 8px; background:linear-gradient(to right,#f97316,#ea580c); color:#fff; border-radius:99px; font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; margin-right:6px; font-family:var(--sans); }}
.picks-block {{ margin:0 0 40px; padding:24px; background:var(--hint); border-radius:12px; }}
.picks-label {{ font-family:var(--sans); font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:var(--accent); font-weight:600; margin:0 0 16px; }}
.pick {{ padding:8px 0; border-bottom:1px solid var(--rule); }}
.pick:last-child {{ border-bottom:none; }}
.pick a {{ color:var(--ink); text-decoration:none; font-weight:600; }}
.pick a:hover {{ text-decoration:underline; }}
.pick-meta {{ font-family:var(--sans); font-size:11px; color:var(--muted); margin-top:2px; }}
</style>
</head>
<body>
<div class="wrap">
<p class="eyebrow">MINY \u00b7 y0 Residency</p>
<h1>Music Cities Daily</h1>
<p class="dek">{date_str} \u00b7 {total_count} stories across the residency cities</p>
{curated_section}
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
    import argparse
    parser = argparse.ArgumentParser(description="Music Cities Daily generator")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM classification")
    parser.add_argument("--no-searxng", action="store_true", help="Skip SearXNG thin-city supplementation")
    parser.add_argument("--relocate", action="store_true", help="Enable LLM event-location extraction (slow, off by default)")
    args = parser.parse_args()

    print(f"[music-cities] Starting generation at {datetime.now(timezone.utc).isoformat()}")

    env = load_env(ENV_FILE)
    pb_url = env.get("POCKETBASE_URL", "https://miny-database.exe.xyz")
    pb_email = env.get("POCKETBASE_ADMIN_EMAIL", "")
    pb_pw = env.get("POCKETBASE_ADMIN_PASSWORD", "")
    ollama_key = env.get("OLLAMA_API_KEY", "")
    searxng_url = env.get("CRW_SEARXNG_URL", "")
    searxng_token = env.get("CRW_EDGE_TOKEN", "")

    if not pb_email or not pb_pw:
        print("[music-cities] ERROR: Missing PocketBase credentials")
        sys.exit(1)

    city_config = load_city_config(YAML_PATH)
    print(f"[music-cities] Loaded {len(city_config['city_names'])} cities across {len(city_config['phases'])} phases")

    # Query PocketBase
    print(f"[music-cities] Querying articles from last {LOOKBACK_HOURS}h...")
    pb = PocketBase(pb_url, pb_email, pb_pw)
    articles = pb.query_articles(LOOKBACK_HOURS)
    print(f"[music-cities] Found {len(articles)} articles with location in lookback window")

    # Initialize LLM client (or None if --no-llm)
    llm = None
    if not args.no_llm and ollama_key:
        llm = LLMClient(ollama_key)
        print(f"[music-cities] LLM classification enabled (model: {LLM_MODEL})")
    else:
        print("[music-cities] LLM classification disabled")

    # Filter
    all_city_names = sorted(city_config["city_names"], key=len, reverse=True)
    filtered = filter_articles(articles, llm, do_relocate=args.relocate, all_city_names=all_city_names)
    print(f"[music-cities] After all filters: {len(filtered)} articles")

    # Group by city
    grouped = group_by_city(filtered, city_config)

    # Supplement thin cities via SearXNG
    if not args.no_searxng and searxng_url and searxng_token and llm:
        searxng = SearXNGClient(searxng_url, searxng_token)
        year = datetime.now(timezone.utc).year
        print(f"[music-cities] Supplementing thin cities via SearXNG...")
        grouped = supplement_thin_cities(grouped, city_config, searxng, llm, year)

    total_displayed = sum(len(arts) for arts in grouped.values())
    cities_with_content = len(grouped)
    print(f"[music-cities] Final: {total_displayed} articles across {cities_with_content} cities")

    if llm:
        print(f"[music-cities] Total LLM calls: {llm.call_count}")

    # Date label
    now_et = datetime.now(timezone.utc) - timedelta(hours=4)
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