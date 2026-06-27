#!/usr/bin/env python3
"""
x_supplement.py — Supplement thin cities in music-cities feed with X/Twitter results.

Runs on Mac (bird CLI is Mac-only). Reads the generated HTML, identifies cities
with <3 articles, searches X for music news, and appends to the HTML.

Usage:
    python3 x_supplement.py --html /path/to/music-cities.html [--dry-run]
"""
from __future__ import annotations
import json, os, re, subprocess, sys, time, urllib.request
from html import escape
from pathlib import Path

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
LLM_MODEL = "gemma4:31b"
MIN_ARTICLES = 3
MAX_X_PER_CITY = 2

# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def parse_city_counts(html: str) -> dict[str, int]:
    """Extract city names and article counts from the feed HTML."""
    counts = {}
    for match in re.finditer(r'<h3>(.+?)\s*<span class="count">·\s*(\d+)</span></h3>', html):
        city = match.group(1).strip()
        count = int(match.group(2))
        counts[city] = count
    return counts

def find_thin_cities(counts: dict[str, int]) -> list[str]:
    """Return cities with fewer than MIN_ARTICLES articles."""
    return [city for city, count in counts.items() if count < MIN_ARTICLES]

# ---------------------------------------------------------------------------
# Bird CLI
# ---------------------------------------------------------------------------

def bird_search(query: str, count: int = 5) -> list[dict]:
    """Search X via bird CLI and return parsed tweets."""
    try:
        result = subprocess.run(
            ["bird", "search", query, "--json", "--count", str(count)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            sys.stderr.write(f"  [bird] Error: {result.stderr[:200]}\n")
            return []
        data = json.loads(result.stdout)
        if isinstance(data, list):
            return data
        return data.get("tweets", data.get("results", []))
    except Exception as e:
        sys.stderr.write(f"  [bird] Exception: {e}\n")
        return []

# ---------------------------------------------------------------------------
# LLM filter
# ---------------------------------------------------------------------------

def llm_filter_music(tweets: list[dict], city: str) -> list[dict]:
    """Use Ollama Cloud to filter tweets for music relevance."""
    if not OLLAMA_API_KEY or not tweets:
        return tweets[:MAX_X_PER_CITY]

    lines = []
    for i, t in enumerate(tweets[:10]):
        text = t.get("text", t.get("full_text", ""))[:200]
        lines.append(f"[{i}] {text}")

    prompt = (
        f"Filter these tweets about {city} for MUSIC relevance only. "
        f"Return ONLY a JSON array of index numbers for tweets about music, "
        f"artists, albums, concerts, festivals, or music industry. Max {MAX_X_PER_CITY}.\n\n"
        f"Tweets:\n{chr(10).join(lines)}"
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
            return [tweets[i] for i in indices if isinstance(i, int) and 0 <= i < len(tweets)][:MAX_X_PER_CITY]
    except Exception as e:
        sys.stderr.write(f"  [LLM] Error: {e}\n")
    return tweets[:MAX_X_PER_CITY]

# ---------------------------------------------------------------------------
# HTML injection
# ---------------------------------------------------------------------------

def inject_x_articles(html: str, city: str, tweets: list[dict]) -> str:
    """Inject X-sourced articles into a city's article block."""
    if not tweets:
        return html

    articles_html = ""
    for t in tweets:
        text = t.get("text", t.get("full_text", ""))
        text = re.sub(r'https?://\S+', '', text).strip()
        text = escape(text[:200])
        tweet_url = t.get("url", t.get("permalink", ""))
        if not tweet_url:
            tid = t.get("id", t.get("tweet_id", ""))
            author = t.get("author", t.get("user", {}))
            if isinstance(author, dict):
                handle = author.get("username", author.get("screen_name", ""))
            else:
                handle = str(author)
            if tid and handle:
                tweet_url = f"https://x.com/{handle}/status/{tid}"
        if not tweet_url or not text:
            continue
        articles_html += (
            f'<div class="article"><a href="{escape(tweet_url)}" target="_blank" rel="noopener">{text}</a>'
            f'<div class="meta">X Discovery</div></div>'
        )

    if not articles_html:
        return html

    # Find the city block: <div class="city"><h3>CityName ...</h3>...articles...</div>
    # The city block ends at </div> before the next <div class="city"> or </section>
    city_escaped = re.escape(city)
    # Find the city h3 and its content up to the closing </div>
    pattern = re.compile(
        r'(<div class="city"><h3>' + city_escaped + r'\s*<span class="count">·\s*\d+</span></h3>)(.*?)(</div>\s*(?=<div class="city">|</section>))',
        re.DOTALL
    )
    match = pattern.search(html)
    if match:
        # Insert articles before the closing </div>
        insert_point = match.start(3)
        html = html[:insert_point] + articles_html + html[insert_point:]
        # Update the count
        old_count_match = re.search(r'·\s*(\d+)</span>', match.group(1))
        if old_count_match:
            old_count = int(old_count_match.group(1))
            new_count = old_count + len(tweets)
            html = html[:match.start()] + html[match.start():insert_point].replace(
                f"· {old_count}</span>", f"· {new_count}</span>", 1
            ) + html[insert_point:]

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
        print("Usage: x_supplement.py --html /path/to/music-cities.html [--dry-run]")
        sys.exit(1)

    html = Path(html_path).read_text()
    counts = parse_city_counts(html)
    thin = find_thin_cities(counts)
    print(f"[x-supplement] Cities: {len(counts)} total, {len(thin)} thin (<{MIN_ARTICLES} articles)")

    if not thin:
        print("[x-supplement] No thin cities. Done.")
        return

    for city in thin:
        print(f"  [{city}] Searching X...")
        tweets = bird_search(f"{city} music news", count=5)
        if not tweets:
            print(f"    -> No tweets found")
            continue
        filtered = llm_filter_music(tweets, city)
        print(f"    -> {len(filtered)} music-related tweets")
        if not dry_run:
            html = inject_x_articles(html, city, filtered)
        time.sleep(2)  # Rate limit bird

    if not dry_run:
        Path(html_path).write_text(html)
        print(f"[x-supplement] Updated {html_path}")
    else:
        print("[x-supplement] DRY RUN — no changes written.")

if __name__ == "__main__":
    main()