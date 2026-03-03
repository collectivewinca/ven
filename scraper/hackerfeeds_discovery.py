#!/usr/bin/env python3
"""
Hacker Feeds-based supplementary discovery for miny-ven.

Uses the `hf` CLI to pull Hacker News top stories and normalize them into
the item shape expected by RSSScraper.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from urllib.parse import urlparse
from typing import Dict, List, Tuple


HF_BIN = shutil.which("hf")

MUSIC_KEYWORDS = {
    "music",
    "song",
    "songs",
    "album",
    "albums",
    "artist",
    "artists",
    "band",
    "bands",
    "tour",
    "tours",
    "concert",
    "festival",
    "dj",
    "hip hop",
    "hip-hop",
    "rap",
    "pop",
    "rock",
    "electronic",
    "edm",
    "billboard",
    "grammy",
    "spotify",
}

TECH_KEYWORDS = {
    "music tech",
    "audio software",
    "music ai",
    "music streaming",
    "daw",
    "midi",
    "synth",
    "audio plugin",
    "vst",
    "music production",
    "music app",
    "sound design",
    "music api",
}

HIGH_SIGNAL_DOMAINS = {
    "billboard.com",
    "pitchfork.com",
    "rollingstone.com",
    "musictech.com",
    "musicbusinessworldwide.com",
    "residentadvisor.net",
    "songexploder.net",
    "ra.co",
    "github.com",
    "arstechnica.com",
    "theverge.com",
    "techcrunch.com",
    "wired.com",
}

REDDIT_TOPICS = [
    "music",
    "musicproduction",
    "wearethemusicmakers",
    "edmproduction",
    "audioengineering",
    "MusicTechnology",
]

MIN_SCORE = 6


def is_available() -> bool:
    return HF_BIN is not None


def _parse_json_payload(raw: str) -> List[Dict]:
    payload = json.loads(raw or "[]")
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "stories", "posts"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
        return [payload]
    return []


def _run_hf(args: List[str], timeout: int = 25) -> List[Dict]:
    if not HF_BIN:
        return []

    # Preferred path for newer hacker-feeds CLI variants.
    try:
        result = subprocess.run(
            [HF_BIN, "--json", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return _parse_json_payload(result.stdout)
    except Exception:
        pass

    # Fallback path for older hf versions that only print text tables.
    try:
        result = subprocess.run(
            [HF_BIN, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            print(f"  ⚠ hf error ({' '.join(args)}): {err[:160]}")
            return []

        titles = re.findall(r"^Title:\s*(.+)$", result.stdout or "", flags=re.MULTILINE)
        urls = re.findall(
            r"^URL:\s*(https?://\S+)$", result.stdout or "", flags=re.MULTILINE
        )
        return [{"title": t.strip(), "url": u.strip()} for t, u in zip(titles, urls)]
    except Exception as exc:
        print(f"  ⚠ hf parse error ({' '.join(args)}): {str(exc)[:160]}")
        return []


def _pick_url(item: Dict) -> str:
    for key in ("url", "link", "external_url", "target", "href"):
        value = str(item.get(key, "") or "").strip()
        if value.startswith("http"):
            return value
    return ""


def _pick_title(item: Dict) -> str:
    for key in ("title", "headline", "name"):
        value = str(item.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _pick_text(item: Dict) -> str:
    for key in ("summary", "snippet", "description", "text", "content"):
        value = str(item.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _score_item(title: str, text: str, link: str, source_label: str) -> Tuple[int, str]:
    haystack = f"{title} {text} {link}".lower()
    score = 0
    reasons: List[str] = []

    music_hits = sum(1 for keyword in MUSIC_KEYWORDS if keyword in haystack)
    if not music_hits:
        # Enforce at least one explicit music signal so we don't surface purely technical posts.
        return 0, "no-music-signal"
    if music_hits:
        score += min(6, music_hits)
        reasons.append(f"music:{music_hits}")

    tech_hits = sum(1 for keyword in TECH_KEYWORDS if keyword in haystack)
    if tech_hits:
        score += min(4, tech_hits)
        reasons.append(f"tech:{tech_hits}")

    host = urlparse(link).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if any(
        host == domain or host.endswith(f".{domain}") for domain in HIGH_SIGNAL_DOMAINS
    ):
        score += 4
        reasons.append("trusted-domain")

    if source_label.startswith("reddit:"):
        score += 2
        reasons.append("reddit-topic")
    elif source_label == "hackernews":
        score += 1

    return score, ",".join(reasons)


def _normalize(items: List[Dict], source_label: str) -> List[Dict]:
    out: List[Dict] = []
    seen = set()

    for raw in items:
        if not isinstance(raw, dict):
            continue
        title = _pick_title(raw)
        link = _pick_url(raw)
        if not title or not link or link in seen:
            continue
        seen.add(link)

        text = _pick_text(raw)
        score, why = _score_item(title, text, link, source_label)
        if score < MIN_SCORE:
            continue

        out.append(
            {
                "title": title,
                "link": link,
                "description": text[:500],
                "content": text,
                "pub_date": "",
                "image": None,
                "source_hint": source_label,
                "discovery_score": score,
                "discovery_reason": why,
            }
        )

    return out


def discover() -> List[Dict]:
    if not is_available():
        print("  ⚠ hf CLI not installed, skipping hackerfeeds discovery")
        return []

    # HN top stories can surface fresh external links not present in RSS feeds.
    hn_items = _normalize(_run_hf(["news", "-t", "20"]), "hackernews")

    # Try music/music-tech Reddit communities. Some HF builds may get 403; skip gracefully.
    reddit_items: List[Dict] = []
    for topic in REDDIT_TOPICS:
        rows = _run_hf(["reddit", "-t", topic, "-s", "hot"])
        if not rows:
            continue
        reddit_items.extend(_normalize(rows, f"reddit:{topic}"))

    candidates = hn_items + reddit_items

    deduped: List[Dict] = []
    seen_urls = set()
    for item in sorted(
        candidates, key=lambda x: x.get("discovery_score", 0), reverse=True
    ):
        if item["link"] in seen_urls:
            continue
        seen_urls.add(item["link"])
        deduped.append(item)
    return deduped


if __name__ == "__main__":
    print("🔬 hacker-feeds discovery dry run")
    if not is_available():
        print("❌ hf CLI not found. Install hacker-feeds-cli first.")
        raise SystemExit(1)
    rows = discover()
    print(f"Found {len(rows)} items")
    for idx, row in enumerate(rows[:8], start=1):
        print(f"{idx}. {row['title'][:80]}")
        print(f"   {row['link']}")
