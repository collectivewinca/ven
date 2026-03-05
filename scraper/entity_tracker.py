#!/usr/bin/env python3
"""
entity_tracker.py — Music entity tracker for miny-ven.

Reads articles from Firestore, uses Gemini to extract:
  - Artists, albums, tracks/singles, release dates
  - Release highlights (key facts, review snippets, context)
  - Buzz scores (mention counts over 7d/30d windows)

Upserts results to Firestore `entities` collection.

Usage:
    python entity_tracker.py [--dry-run] [--limit N] [--hours N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "miny-ven")
API_KEY = os.getenv("FIREBASE_API_KEY", "")
FIRESTORE_URL = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    f"/databases/(default)/documents"
)

BATCH_SIZE = 3  # Articles per Gemini call (smaller = more reliable JSON)


# ---------------------------------------------------------------------------
# Firestore helpers
# ---------------------------------------------------------------------------

def fs_val(v: Any) -> dict:
    """Convert a Python value to a Firestore REST field value."""
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [fs_val(i) for i in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: fs_val(vv) for k, vv in v.items()}}}
    return {"stringValue": str(v)}


def fs_fields(d: dict) -> dict:
    return {k: fs_val(v) for k, v in d.items()}


def get_field(fields: dict, name: str) -> Any:
    f = fields.get(name, {})
    if "stringValue" in f:
        return f["stringValue"]
    if "integerValue" in f:
        return int(f["integerValue"])
    if "booleanValue" in f:
        return f["booleanValue"]
    if "arrayValue" in f:
        vals = f["arrayValue"].get("values", [])
        return [v.get("stringValue", "") for v in vals]
    if "mapValue" in f:
        inner = f["mapValue"].get("fields", {})
        return {k: get_field(inner, k) for k in inner}
    return None


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60] or "unknown"


# ---------------------------------------------------------------------------
# Firestore fetch
# ---------------------------------------------------------------------------

def fetch_articles(since_hours: int = 72, limit: int | None = None) -> list[dict]:
    """Fetch recent articles from Firestore."""
    all_docs = []
    next_token = None
    fields = ["title", "summary", "full_content", "primary_genre",
              "source_url", "artist_names", "published_at"]
    field_params = "&".join(f"mask.fieldPaths={f}" for f in fields)

    while True:
        url = f"{FIRESTORE_URL}/articles?pageSize=200&{field_params}"
        if next_token:
            url += f"&pageToken={next_token}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        all_docs.extend(data.get("documents", []))
        next_token = data.get("nextPageToken")
        if not next_token:
            break
        if limit and len(all_docs) >= limit:
            break

    # Filter by recency
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    recent = []
    for doc in all_docs:
        fields_d = doc.get("fields", {})
        pub = get_field(fields_d, "published_at") or ""
        try:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if dt >= cutoff:
                recent.append(doc)
        except Exception:
            recent.append(doc)  # include if unparseable

    if limit:
        recent = recent[:limit]

    print(f"  Fetched {len(recent)} articles (within {since_hours}h window)")
    return recent


# ---------------------------------------------------------------------------
# Gemini entity extraction
# ---------------------------------------------------------------------------

EXTRACT_PROMPT = """\
Analyze these music news articles and extract structured music entities.

{articles}

Return a JSON array. Each element is one entity found across the articles:

[
  {{
    "name": "Artist or Album or Track name",
    "type": "artist|album|track|band",
    "genres": ["hiphop", "pop"],
    "artist": "artist name (if type is album or track)",
    "release_date": "YYYY-MM-DD or YYYY-MM or YYYY or null",
    "release_highlights": "2-3 sentence highlight: what makes this release notable, any critical reception, collaborators, themes, or industry context. Be specific.",
    "article_ids": ["doc_id1", "doc_id2"],
    "sources": ["https://..."]
  }}
]

Rules:
- type "artist" or "band": solo performers, groups
- type "album": full-length albums, EPs, mixtapes being reviewed or announced
- type "track": singles, songs, featured tracks
- release_highlights: only for albums and tracks — capture the most newsworthy detail
  (e.g. critical score, chart position, collaborator names, production credits, themes)
- If multiple articles mention the same entity, merge into one entry with all article_ids
- Skip generic terms, streaming platforms, award show names
- Return ONLY valid JSON array, no explanation
"""


def extract_entities_batch(
    article_blocks: list[dict],
) -> list[dict]:
    """Call Gemini to extract entities from a batch of articles."""
    text_blocks = []
    for a in article_blocks:
        # Keep content short — long text causes Gemini to truncate JSON output
        content = a['content'][:350].replace('"', "'").replace('\\', '')
        block = f"[ID:{a['doc_id']}] [{a['genre'].upper()}] {a['title']}\n{content}"
        text_blocks.append(block)

    prompt = EXTRACT_PROMPT.format(articles="\n\n---\n\n".join(text_blocks))

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": "You are a music industry analyst. Return ONLY valid JSON arrays."}]
        },
        "generationConfig": {
            "maxOutputTokens": 4096,
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    r.raise_for_status()

    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # Extract first JSON array
    if not raw.startswith("["):
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to salvage complete objects from a truncated array
        objects = []
        depth = 0
        start = None
        for i, ch in enumerate(raw):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        objects.append(json.loads(raw[start:i+1]))
                    except json.JSONDecodeError:
                        pass
                    start = None
        if objects:
            print(f"  ⚠ Salvaged {len(objects)} objects from partial JSON")
            return objects
        print(f"  ⚠ JSON parse error: could not salvage any objects")
        return []


# ---------------------------------------------------------------------------
# Merge + buzz scoring
# ---------------------------------------------------------------------------

def merge_entities(batches: list[list[dict]]) -> dict[str, dict]:
    """
    Merge entity results across batches.
    Key: slugified name. Deduplicates by name+type.
    """
    merged: dict[str, dict] = {}

    for batch in batches:
        for ent in batch:
            name = (ent.get("name") or "").strip()
            etype = (ent.get("type") or "artist").lower()
            if not name or len(name) < 2:
                continue

            key = f"{etype}:{slugify(name)}"
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "type": etype,
                    "genres": ent.get("genres") or [],
                    "artist": ent.get("artist") or "",
                    "release_date": ent.get("release_date") or "",
                    "release_highlights": ent.get("release_highlights") or "",
                    "article_ids": list(ent.get("article_ids") or []),
                    "sources": list(ent.get("sources") or []),
                }
            else:
                # Merge article_ids and sources
                existing = merged[key]
                existing["article_ids"] = list(
                    set(existing["article_ids"] + list(ent.get("article_ids") or []))
                )
                existing["sources"] = list(
                    set(existing["sources"] + list(ent.get("sources") or []))
                )
                # Keep the richer highlights
                if len(ent.get("release_highlights") or "") > len(existing.get("release_highlights") or ""):
                    existing["release_highlights"] = ent["release_highlights"]
                # Fill missing fields
                if not existing.get("release_date") and ent.get("release_date"):
                    existing["release_date"] = ent["release_date"]
                if not existing.get("genres") and ent.get("genres"):
                    existing["genres"] = ent["genres"]

    return merged


def compute_buzz(entities: dict[str, dict], article_dates: dict[str, datetime]) -> dict[str, dict]:
    """Add buzz_7d, buzz_30d, buzz_score to each entity."""
    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    for key, ent in entities.items():
        ids = ent.get("article_ids") or []
        count_7d = sum(
            1 for aid in ids
            if article_dates.get(aid, now).astimezone(timezone.utc) >= cutoff_7d
        )
        count_30d = sum(
            1 for aid in ids
            if article_dates.get(aid, now).astimezone(timezone.utc) >= cutoff_30d
        )
        total = len(ids)

        # Weighted buzz: recent mentions count more
        buzz = (count_7d * 3) + (count_30d * 1.5) + total
        ent["buzz_7d"] = count_7d
        ent["buzz_30d"] = count_30d
        ent["buzz_score"] = round(buzz, 1)
        ent["mention_count"] = total

    return entities


# ---------------------------------------------------------------------------
# Firestore upsert
# ---------------------------------------------------------------------------

def upsert_entity(slug: str, ent: dict, dry_run: bool = False) -> bool:
    """Upsert one entity document to Firestore `entities` collection."""
    doc = {
        "name": ent["name"],
        "type": ent["type"],
        "genres": ent.get("genres") or [],
        "artist": ent.get("artist") or "",
        "release_date": ent.get("release_date") or "",
        "release_highlights": ent.get("release_highlights") or "",
        "article_ids": ent.get("article_ids") or [],
        "sources": ent.get("sources") or [],
        "mention_count": ent.get("mention_count", 0),
        "buzz_7d": ent.get("buzz_7d", 0),
        "buzz_30d": ent.get("buzz_30d", 0),
        "buzz_score": ent.get("buzz_score", 0.0),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  [DRY-RUN] Would upsert: {ent['type']}:{ent['name']} "
              f"(buzz={ent.get('buzz_score', 0)}, articles={len(ent.get('article_ids', []))})")
        if ent.get("release_highlights"):
            print(f"    → {ent['release_highlights'][:120]}...")
        return True

    url = f"{FIRESTORE_URL}/entities/{slug}?key={API_KEY}"
    payload = {"fields": fs_fields(doc)}
    r = requests.patch(url, json=payload, timeout=15)
    return r.status_code in (200, 201)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract and track music entities from miny-ven articles")
    parser.add_argument("--dry-run", action="store_true", help="Print results without writing to Firestore")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to process")
    parser.add_argument("--hours", type=int, default=72, help="Lookback window in hours (default: 72)")
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY not set")
    if not API_KEY and not args.dry_run:
        raise SystemExit("FIREBASE_API_KEY not set (use --dry-run to test without Firestore)")

    print(f"\n🎵 miny-ven entity tracker")
    print(f"   lookback: {args.hours}h | model: {GEMINI_MODEL}\n")

    # 1. Fetch articles
    print("📥 Fetching articles...")
    docs = fetch_articles(since_hours=args.hours, limit=args.limit)
    if not docs:
        print("No articles found.")
        return

    # Build article blocks + date index
    article_blocks = []
    article_dates: dict[str, datetime] = {}
    for doc in docs:
        f = doc.get("fields", {})
        doc_id = doc["name"].split("/")[-1]
        title = get_field(f, "title") or ""
        summary = get_field(f, "summary") or ""
        content = get_field(f, "full_content") or summary
        genre = get_field(f, "primary_genre") or "mixed"
        source_url = get_field(f, "source_url") or ""
        pub = get_field(f, "published_at") or ""

        try:
            article_dates[doc_id] = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            article_dates[doc_id] = datetime.now(timezone.utc)
        article_blocks.append({
            "doc_id": doc_id,
            "title": title,
            "genre": genre,
            "content": content,
            "source_url": source_url,
        })

    # 2. Extract entities in batches
    print(f"\n🤖 Extracting entities ({len(article_blocks)} articles, batch size {BATCH_SIZE})...")
    batch_results = []
    total_batches = (len(article_blocks) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(article_blocks), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = article_blocks[i:i + BATCH_SIZE]
        print(f"  Batch {batch_num}/{total_batches}...", end=" ", flush=True)
        try:
            result = extract_entities_batch(batch)
            batch_results.append(result)
            counts = defaultdict(int)
            for e in result:
                counts[e.get("type", "?")] += 1
            summary = ", ".join(f"{v} {k}s" for k, v in counts.items())
            print(f"found {len(result)} entities ({summary})")
        except Exception as e:
            print(f"error: {e}")
            batch_results.append([])
        time.sleep(0.5)

    # 3. Merge + buzz
    print("\n🔀 Merging and scoring...")
    entities = merge_entities(batch_results)
    entities = compute_buzz(entities, article_dates)

    # Sort by buzz score
    ranked = sorted(entities.items(), key=lambda x: x[1].get("buzz_score", 0), reverse=True)

    # 4. Print summary
    print(f"\n{'='*60}")
    print(f"  ENTITY TRACKER RESULTS ({len(entities)} unique entities)")
    print(f"{'='*60}")

    by_type: dict[str, list] = defaultdict(list)
    for slug, ent in ranked:
        by_type[ent["type"]].append((slug, ent))

    for etype in ["artist", "band", "album", "track"]:
        items = by_type.get(etype, [])
        if not items:
            continue
        print(f"\n🎯 {etype.upper()}S  (top {min(10, len(items))} by buzz)")
        print("-" * 50)
        for slug, ent in items[:10]:
            highlights = ent.get("release_highlights") or ""
            print(f"  [{ent['buzz_score']:5.1f}] {ent['name']}")
            if ent.get("release_date"):
                print(f"          release: {ent['release_date']}")
            if highlights:
                print(f"          → {highlights[:150]}")
            print(f"          mentions: {ent['mention_count']} total | {ent['buzz_7d']} this week")

    # 5. Upsert to Firestore
    print(f"\n{'='*60}")
    action = "DRY-RUN" if args.dry_run else "Saving to Firestore"
    print(f"💾 {action} → entities collection")
    print(f"{'='*60}")

    saved = 0
    failed = 0
    for slug, ent in ranked:
        ok = upsert_entity(slug, ent, dry_run=args.dry_run)
        if ok:
            saved += 1
        else:
            failed += 1
            print(f"  ✗ Failed: {ent['name']}")

    print(f"\n✅ Done — {saved} entities {'would be saved' if args.dry_run else 'saved'}"
          f"{f', {failed} failed' if failed else ''}")


if __name__ == "__main__":
    main()
