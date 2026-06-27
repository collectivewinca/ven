#!/usr/bin/env python3
"""
l30d_supplement.py — Supplement 0-article cities with last30days social research.

Runs on Mac (last30days CLI is Mac-only). Reads the generated HTML, identifies
cities with 0 articles, runs last30days for music news, and appends to HTML.

Usage:
    python3 l30d_supplement.py --html /path/to/music-cities.html [--dry-run]
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time, urllib.request
from html import escape
from pathlib import Path

L30D_SCRIPT = Path.home() / ".claude/skills/last30days/skills/last30days/scripts/last30days.py"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
LLM_MODEL = "gemma4:31b"
MAX_PER_CITY = 2

# ---------------------------------------------------------------------------
# HTML parsing (same as x_supplement)
# ---------------------------------------------------------------------------

def parse_city_counts(html: str) -> dict[str, int]:
    counts = {}
    for match in re.finditer(r'<h3>(.+?)\s*<span class="count">·\s*(\d+)</span></h3>', html):
        city = match.group(1).strip()
        count = int(match.group(2))
        counts[city] = count
    return counts

def find_empty_cities(counts: dict[str, int]) -> list[str]:
    return [city for city, count in counts.items() if count == 0]

# ---------------------------------------------------------------------------
# last30days CLI
# ---------------------------------------------------------------------------

def run_last30days(query: str) -> list[dict]:
    """Run last30days CLI and return parsed posts."""
    try:
        result = subprocess.run(
            ["python3", str(L30D_SCRIPT), query, "--json"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            sys.stderr.write(f"  [l30d] Error: {result.stderr[:200]}\n")
            return []
        # l30d outputs JSON to stdout
        try:
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return data
            return data.get("posts", data.get("results", []))
        except json.JSONDecodeError:
            # Maybe it outputs text — parse for URLs and titles
            posts = []
            for line in result.stdout.splitlines():
                if line.startswith("{"):
                    try:
                        posts.append(json.loads(line))
                    except:
                        pass
            return posts
    except Exception as e:
        sys.stderr.write(f"  [l30d] Exception: {e}\n")
        return []

# ---------------------------------------------------------------------------
# LLM filter (same pattern as x_supplement)
# ---------------------------------------------------------------------------

def llm_filter_music(posts: list[dict], city: str) -> list[dict]:
    if not OLLAMA_API_KEY or not posts:
        return posts[:MAX_PER_CITY]

    lines = []
    for i, p in enumerate(posts[:10]):
        title = p.get("title", p.get("text", ""))[:200]
        source = p.get("source", p.get("platform", ""))
        lines.append(f"[{i}] {title} ({source})")

    prompt = (
        f"Filter these social posts about {city} for MUSIC relevance only. "
        f"Return ONLY a JSON array of index numbers for posts about music, "
        f"artists, albums, concerts, festivals. Max {MAX_PER_CITY}.\n\n"
        f"Posts:\n{chr(10).join(lines)}"
    )
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
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
            return [posts[i] for i in indices if isinstance(i, int) and 0 <= i < len(posts)][:MAX_PER_CITY]
    except Exception as e:
        sys.stderr.write(f"  [LLM] Error: {e}\n")
    return posts[:MAX_PER_CITY]

# ---------------------------------------------------------------------------
# HTML injection (same as x_supplement but for empty cities)
# ---------------------------------------------------------------------------

def inject_l30d_articles(html: str, city: str, posts: list[dict]) -> str:
    if not posts:
        return html

    articles_html = ""
    for p in posts:
        title = escape(p.get("title", p.get("text", ""))[:200])
        url = p.get("url", p.get("link", ""))
        source = p.get("source", p.get("platform", "Social"))
        if not url or not title:
            continue
        articles_html += (
            f'<div class="article"><a href="{escape(url)}" target="_blank" rel="noopener">{title}</a>'
            f'<div class="meta">Social Discovery · {escape(str(source))}</div></div>'
        )

    if not articles_html:
        return html

    # For empty cities, we need to find the city block (it exists with count 0)
    # and inject articles inside it
    city_pattern = re.compile(
        r'(<div class="city"><h3>' + re.escape(city) + r'\s*<span class="count">·\s*0</span></h3>)(\s*</div>)',
        re.DOTALL
    )
    match = city_pattern.search(html)
    if match:
        html = html[:match.start(2)] + articles_html + html[match.start(2):]
        # Update count from 0 to len(posts)
        html = html[:match.start()] + html[match.start():match.start(2)].replace(
            "· 0</span>", f"· {len(posts)}</span>"
        ) + html[match.start(2):]

    return html

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    html_path = None
    dry_run = False
    for i, arg in enumerate(sys.argv):
        if arg == "--html" and i + 1 < len(sys.argv):
            html_path = sys.argv[i + 1]
        elif arg == "--dry-run":
            dry_run = True

    if not html_path:
        print("Usage: l30d_supplement.py --html /path/to/music-cities.html [--dry-run]")
        sys.exit(1)

    html = Path(html_path).read_text()
    counts = parse_city_counts(html)
    empty = find_empty_cities(counts)
    print(f"[l30d] Cities: {len(counts)} total, {len(empty)} with 0 articles")

    if not empty:
        print("[l30d] No empty cities. Done.")
        return

    for city in empty:
        print(f"  [{city}] Running last30days...")
        posts = run_last30days(f"{city} music scene news")
        if not posts:
            print(f"    -> No posts found")
            continue
        filtered = llm_filter_music(posts, city)
        print(f"    -> {len(filtered)} music-related posts")
        if not dry_run:
            html = inject_l30d_articles(html, city, filtered)
        time.sleep(3)

    if not dry_run:
        Path(html_path).write_text(html)
        print(f"[l30d] Updated {html_path}")
    else:
        print("[l30d] DRY RUN — no changes written.")

if __name__ == "__main__":
    main()