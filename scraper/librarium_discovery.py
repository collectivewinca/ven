#!/usr/bin/env python3
"""
Librarium-based article discovery for miny-ven.
Calls the librarium CLI to fan out genre-specific queries across multiple
search/AI providers (Perplexity, Exa, Brave) and parses structured output.

Used as a supplementary discovery source after Exa in the pipeline.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


LIBRARIUM_BIN = shutil.which("librarium")

GENRE_QUERIES = [
    "latest hip hop rap music news today",
    "new pop music releases albums today",
    "rock alternative music news today",
    "electronic EDM music news today",
    "gospel christian music news today",
]

# Providers to use — maps to librarium's "quick" group
DEFAULT_GROUP = "quick"


def is_available() -> bool:
    """Check if librarium CLI is installed and reachable."""
    return LIBRARIUM_BIN is not None


def _run_query(query: str, output_dir: str, group: str = DEFAULT_GROUP) -> Optional[Path]:
    """Run a single librarium query and return the output directory path."""
    cmd = [
        LIBRARIUM_BIN,
        "run",
        query,
        "--group", group,
        "--mode", "sync",
        "--output", output_dir,
        "--timeout", "30",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ},
        )
        if result.returncode != 0:
            print(f"  ⚠ librarium error: {result.stderr[:200]}")
            return None

        # librarium creates a timestamped subdirectory inside output_dir
        out_path = Path(output_dir)
        subdirs = sorted(out_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for d in subdirs:
            if d.is_dir() and (d / "sources.json").exists():
                return d

        return None

    except subprocess.TimeoutExpired:
        print(f"  ⚠ librarium timed out for query: {query[:40]}...")
        return None
    except Exception as e:
        print(f"  ⚠ librarium subprocess error: {e}")
        return None


def _parse_sources(run_dir: Path) -> List[Dict]:
    """Parse sources.json from a librarium run directory into article items."""
    sources_file = run_dir / "sources.json"
    if not sources_file.exists():
        return []

    try:
        data = json.loads(sources_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ Failed to parse {sources_file}: {e}")
        return []

    items = []
    # sources.json is an array of {url, title, snippet, provider, ...}
    sources = data if isinstance(data, list) else data.get("sources", [])

    for src in sources:
        title = (src.get("title") or "").strip()
        url = (src.get("url") or "").strip()
        snippet = (src.get("snippet") or src.get("description") or "").strip()

        if not title or not url or not url.startswith("http"):
            continue

        items.append({
            "title": title,
            "link": url,
            "description": snippet[:500],
            "content": snippet,
            "pub_date": "",
            "image": None,
        })

    return items


def _parse_summary(run_dir: Path) -> str:
    """Parse summary.md for additional context."""
    summary_file = run_dir / "summary.md"
    if summary_file.exists():
        try:
            return summary_file.read_text()[:5000]
        except OSError:
            pass
    return ""


def discover(genres: Optional[List[str]] = None, group: str = DEFAULT_GROUP) -> List[Dict]:
    """Run librarium discovery across genre queries.

    Args:
        genres: Custom query list. Defaults to GENRE_QUERIES.
        group: Librarium provider group. Defaults to "quick".

    Returns:
        List of article dicts with keys: title, link, description, content,
        pub_date, image — matching the format expected by RSSScraper.
    """
    if not is_available():
        print("  ⚠ librarium CLI not found, skipping librarium discovery")
        return []

    queries = genres or GENRE_QUERIES
    all_items: List[Dict] = []
    seen_urls: set = set()

    with tempfile.TemporaryDirectory(prefix="librarium_") as tmp_dir:
        for query in queries:
            query_dir = os.path.join(tmp_dir, query.replace(" ", "_")[:40])
            os.makedirs(query_dir, exist_ok=True)

            run_dir = _run_query(query, query_dir, group)
            if not run_dir:
                continue

            items = _parse_sources(run_dir)
            for item in items:
                # Deduplicate within this run
                if item["link"] not in seen_urls:
                    seen_urls.add(item["link"])
                    all_items.append(item)

    return all_items


if __name__ == "__main__":
    """Dry run — test librarium discovery without Firestore."""
    print("🔬 Librarium Discovery Dry Run")
    print("=" * 40)

    if not is_available():
        print("❌ librarium CLI not installed. Run: npm install -g librarium")
        exit(1)

    print(f"Using group: {DEFAULT_GROUP}")
    print(f"Queries: {len(GENRE_QUERIES)}")
    print()

    items = discover()
    print(f"\n{'=' * 40}")
    print(f"Total unique articles found: {len(items)}")
    for i, item in enumerate(items[:10], 1):
        print(f"  {i}. {item['title'][:60]}")
        print(f"     {item['link']}")
        print()
