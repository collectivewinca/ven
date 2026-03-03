#!/usr/bin/env python3
"""
Upload outreach_manifest.json entities to Firestore `entities` collection.

Each entity becomes a document with fields ready for enrichment:
  - name, category, mention_score
  - bio, website, social_links, contact_email (empty, for enrichment)
  - enriched (bool), enriched_at (string)
"""

import json
import requests
import time

PROJECT_ID = "miny-ven"
FIRESTORE_URL = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    f"/databases/(default)/documents"
)


def slugify(name: str) -> str:
    """Turn entity name into a URL-safe document ID."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:60] or "unknown"


def to_firestore_fields(entity: dict) -> dict:
    """Convert entity dict to Firestore field format."""
    fields = {}
    for key, value in entity.items():
        if isinstance(value, str):
            fields[key] = {"stringValue": value}
        elif isinstance(value, bool):
            fields[key] = {"booleanValue": value}
        elif isinstance(value, int):
            fields[key] = {"integerValue": str(value)}
        elif isinstance(value, list):
            fields[key] = {
                "arrayValue": {
                    "values": [{"stringValue": str(v)} for v in value]
                }
            }
        elif value is None:
            fields[key] = {"nullValue": None}
    return fields


def upload_entity(doc_id: str, fields: dict) -> bool:
    """Create or overwrite entity document in Firestore."""
    url = f"{FIRESTORE_URL}/entities/{doc_id}"
    payload = {"fields": to_firestore_fields(fields)}
    r = requests.patch(url, json=payload, timeout=15)
    r.raise_for_status()
    return True


def main():
    with open("outreach_manifest.json") as f:
        manifest = json.load(f)

    total = 0
    errors = 0

    for category, items in manifest["categories"].items():
        print(f"\n--- {category.upper()} ({len(items)} entities) ---")

        for item in items:
            name = item["name"]
            doc_id = slugify(name)

            doc = {
                "name": name,
                "category": category,
                "mention_score": item["mention_score"],
                # Enrichment fields (empty, to be filled later)
                "bio": "",
                "website": "",
                "social_links": [],
                "contact_email": "",
                "genre_tags": [],
                "location": "",
                "notes": "",
                "enriched": False,
                "enriched_at": "",
            }

            try:
                upload_entity(doc_id, doc)
                total += 1
                if total % 25 == 0:
                    print(f"  Uploaded {total} entities...")
            except Exception as e:
                print(f"  Error uploading {name}: {e}")
                errors += 1

            # Firestore REST has no strict rate limit but be nice
            if total % 50 == 0:
                time.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Upload complete: {total} entities, {errors} errors")


if __name__ == "__main__":
    main()
