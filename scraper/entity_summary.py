#!/usr/bin/env python3
"""Summarize the restored outreach entity manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path(__file__).with_name("outreach_manifest.json")


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def print_summary(manifest: dict[str, Any], top_n: int) -> None:
    print(f"Manifest: {manifest.get('_restored_from', {}).get('original_path', 'unknown')}")
    print(f"Articles analyzed: {manifest.get('total_articles_analyzed', 'unknown')}")
    print(f"Extraction model: {manifest.get('extraction_model', 'unknown')}")
    print(f"Unique entities: {manifest.get('total_unique_entities', 'unknown')}")
    print("")

    categories = manifest.get("categories", {})
    if not isinstance(categories, dict) or not categories:
        print("No categories found.")
        return

    for category, entries in categories.items():
        if not isinstance(entries, list):
            continue
        print(f"[{category}]")
        for item in entries[:top_n]:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "unknown")
            score = item.get("mention_score", "n/a")
            print(f"- {name} ({score})")
        print("")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a concise summary of the outreach entity manifest."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the outreach manifest JSON file.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of top entries to print per category.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()

    if args.top < 1:
        raise SystemExit("--top must be at least 1")
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    manifest = load_manifest(manifest_path)
    print_summary(manifest, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
