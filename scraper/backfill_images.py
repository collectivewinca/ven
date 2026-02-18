#!/usr/bin/env python3
"""One-shot backfill: generate dall-e-3 images for docs with image_source=none."""

import json
import os
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from openai import OpenAI

FIREBASE_API_KEY = os.environ["FIREBASE_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
FIRESTORE_URL = "https://firestore.googleapis.com/v1/projects/miny-ven/databases/(default)/documents"

client = OpenAI(api_key=OPENAI_API_KEY)

DOCS_TO_BACKFILL = [
    {
        "doc_id": "willow-just-unveiled-her-9c9270aa23d383858812",
        "title": "WILLOW Just Unveiled Her Most Daring Album Yet",
        "artist": "WILLOW",
        "genre": "rock",
    },
    {
        "doc_id": "how-christian-music-got-b29bba097113d5aedb27",
        "title": "How Christian Music Got a Major Glow-Up",
        "artist": "",
        "genre": "gospel",
    },
]


def generate_image(title: str, artist: str, genre: str) -> str | None:
    prompt = (
        "Create a photorealistic editorial hero image for a music news card. "
        "No text, no logo, no watermark, no collage. "
        f"Artist focus: {artist or 'unknown artist'}. "
        f"Genre context: {genre or 'mixed'}. "
        f"Headline context: {title[:180]}."
    )
    result = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1792x1024",
    )
    first = (result.data or [None])[0]
    if first and getattr(first, "url", None):
        return first.url
    return None


def patch_firestore(doc_id: str, image_url: str) -> bool:
    url = (
        f"{FIRESTORE_URL}/articles/{doc_id}"
        f"?key={FIREBASE_API_KEY}"
        f"&updateMask.fieldPaths=image_url"
        f"&updateMask.fieldPaths=image_source"
    )
    payload = json.dumps({
        "fields": {
            "image_url": {"stringValue": image_url},
            "image_source": {"stringValue": "ai_generated_openai"},
        }
    }).encode()
    req = urllib.request.Request(url, data=payload, method="PATCH")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req, timeout=15)
    return resp.status in (200, 201)


def main():
    for doc in DOCS_TO_BACKFILL:
        print(f"\n--- {doc['doc_id']} ---")
        print(f"Generating image for: {doc['title']}")
        image_url = generate_image(doc["title"], doc["artist"], doc["genre"])
        if not image_url:
            print("  FAILED: no URL returned")
            continue
        print(f"  Got URL: {image_url[:80]}...")
        ok = patch_firestore(doc["doc_id"], image_url)
        print(f"  Firestore PATCH: {'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
