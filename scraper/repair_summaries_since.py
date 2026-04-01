#!/usr/bin/env python3
"""
Repair article summaries in Firestore from a cutoff date onward.

For each matching article:
1. Fetch the current Firestore document metadata/content
2. Re-fetch article text from source_url when possible
3. Regenerate a cleaned summary using the current scraper summarizer
4. Patch summary (and full_content when improved) back to Firestore
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRAPER_DIR = Path(__file__).resolve().parent
CUTOFF_ISO = "2026-03-21T00:00:00+00:00"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ROOT_DIR / ".env")
load_env_file(SCRAPER_DIR / ".env")

from rss_scraper import RSSScraper  # noqa: E402


PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("VITE_FIREBASE_PROJECT_ID") or "miny-ven"
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY") or os.getenv("VITE_FIREBASE_API_KEY") or ""
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"
CUTOFF_DT = datetime.fromisoformat(CUTOFF_ISO)


def get_field(fields: Dict[str, Any], name: str) -> Any:
    field = fields.get(name, {})
    if "stringValue" in field:
        return field["stringValue"]
    if "integerValue" in field:
        return int(field["integerValue"])
    if "doubleValue" in field:
        return float(field["doubleValue"])
    if "arrayValue" in field:
        return [v.get("stringValue", "") for v in field.get("arrayValue", {}).get("values", [])]
    return ""


def parse_iso_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iter_articles(session: requests.Session) -> Iterable[Dict[str, Any]]:
    page_token = ""
    field_paths = [
        "title",
        "summary",
        "full_content",
        "source",
        "source_url",
        "artist_names",
        "published_at",
    ]

    while True:
        params: List[tuple[str, str]] = [("pageSize", "300")]
        if FIREBASE_API_KEY:
            params.append(("key", FIREBASE_API_KEY))
        if page_token:
            params.append(("pageToken", page_token))
        params.extend(("mask.fieldPaths", field) for field in field_paths)

        url = f"{FIRESTORE_URL}/articles?{urlencode(params)}"
        response = session.get(url, timeout=30)
        response.raise_for_status()
        payload = response.json()

        for doc in payload.get("documents", []):
            yield doc

        page_token = payload.get("nextPageToken", "")
        if not page_token:
            return


def patch_article(
    session: requests.Session,
    doc_name: str,
    new_summary: str,
    new_content: Optional[str],
) -> None:
    mask_fields = ["summary"]
    fields: Dict[str, Any] = {"summary": {"stringValue": new_summary}}

    if new_content:
        mask_fields.append("full_content")
        fields["full_content"] = {"stringValue": new_content[:4000]}

    query = "&".join(f"updateMask.fieldPaths={field}" for field in mask_fields)
    suffix = f"&key={FIREBASE_API_KEY}" if FIREBASE_API_KEY else ""
    url = f"https://firestore.googleapis.com/v1/{doc_name}?{query}{suffix}"

    response = session.patch(url, json={"fields": fields}, timeout=20)
    response.raise_for_status()


def main() -> int:
    if not FIREBASE_API_KEY:
        print("FIREBASE_API_KEY or VITE_FIREBASE_API_KEY is required.")
        return 1

    scraper = RSSScraper()
    session = requests.Session()

    total_seen = 0
    total_matched = 0
    total_updated = 0
    total_skipped = 0
    total_failed = 0

    print(f"Repairing summaries for articles published on or after {CUTOFF_DT.date()} UTC")
    print(f"Firestore project: {PROJECT_ID}")
    print()

    for doc in iter_articles(session):
        total_seen += 1
        fields = doc.get("fields", {})
        published_at_raw = get_field(fields, "published_at")
        published_at = parse_iso_datetime(published_at_raw)

        if not published_at or published_at < CUTOFF_DT:
            continue

        total_matched += 1
        doc_name = doc["name"]
        doc_id = doc_name.split("/")[-1]
        title = get_field(fields, "title") or ""
        existing_summary = get_field(fields, "summary") or ""
        existing_content = get_field(fields, "full_content") or ""
        source_url = get_field(fields, "source_url") or ""

        print(f"[{total_matched}] {published_at.date()} {title[:90]}")

        try:
            fetched_content = scraper._fetch_article_text(source_url) if source_url else ""
            candidate_content = fetched_content or existing_content or existing_summary or title
            clean_content = scraper._clean_summary_text(candidate_content)

            if not clean_content:
                print("   skipped: no usable content")
                total_skipped += 1
                continue

            new_summary = scraper.summarize_with_gemini(title, clean_content)
            new_summary = scraper._clean_summary_text(new_summary)

            if not new_summary:
                print("   skipped: summarizer returned empty text")
                total_skipped += 1
                continue

            new_content = clean_content if clean_content != existing_content else None
            patch_article(session, doc_name, new_summary, new_content)
            total_updated += 1
            print(f"   updated: {doc_id} | {new_summary[:100]}")
            time.sleep(0.35)
        except Exception as exc:
            total_failed += 1
            print(f"   failed: {doc_id} | {exc}")
            continue

    print()
    print("Repair complete")
    print(f"Seen: {total_seen}")
    print(f"Matched since cutoff: {total_matched}")
    print(f"Updated: {total_updated}")
    print(f"Skipped: {total_skipped}")
    print(f"Failed: {total_failed}")
    return 0 if total_failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
