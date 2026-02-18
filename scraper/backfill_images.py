#!/usr/bin/env python3
"""One-shot backfill: generate dall-e-3 images for docs with image_source=none.

Generates images, compresses to WebP, uploads to Firebase Storage,
then patches Firestore with the permanent URL.
"""

import base64
import hashlib
import io
import json
import os
import re
import urllib.request

import requests as req_lib

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

# Firebase Storage (optional but recommended)
_storage_bucket = None
FIREBASE_SA_B64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "")
if FIREBASE_SA_B64:
    try:
        import firebase_admin
        from firebase_admin import credentials, storage

        sa_info = json.loads(base64.b64decode(FIREBASE_SA_B64))
        cred = credentials.Certificate(sa_info)
        firebase_admin.initialize_app(
            cred, {"storageBucket": "miny-ven.firebasestorage.app"}
        )
        _storage_bucket = storage.bucket()
        print("✓ Firebase Storage initialized")
    except Exception as e:
        print(f"⚠ Firebase Storage init failed: {e}")
else:
    print("⚠ FIREBASE_SERVICE_ACCOUNT_B64 not set — images will use temporary OpenAI URLs")


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


def compress_and_upload(image_url: str, title: str) -> str | None:
    """Download, compress to WebP, upload to Firebase Storage."""
    if not _storage_bucket:
        return None
    try:
        from PIL import Image

        resp = req_lib.get(image_url, timeout=30)
        if resp.status_code >= 400:
            return None

        img = Image.open(io.BytesIO(resp.content))
        max_width = 800
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=80)
        webp_bytes = buf.getvalue()

        slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-")
        digest = hashlib.sha1(image_url.encode()).hexdigest()[:12]
        storage_path = f"article-images/{slug}-{digest}.webp"

        blob = _storage_bucket.blob(storage_path)
        blob.upload_from_string(webp_bytes, content_type="image/webp")
        blob.make_public()

        print(f"  ✓ Uploaded ({len(webp_bytes)//1024}KB): {storage_path}")
        return blob.public_url
    except Exception as e:
        print(f"  ⚠ Upload failed: {e}")
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
        raw_url = generate_image(doc["title"], doc["artist"], doc["genre"])
        if not raw_url:
            print("  FAILED: no URL returned from OpenAI")
            continue
        print(f"  OpenAI URL: {raw_url[:80]}...")

        # Compress and upload to Firebase Storage
        permanent_url = compress_and_upload(raw_url, doc["title"])
        final_url = permanent_url or raw_url

        ok = patch_firestore(doc["doc_id"], final_url)
        storage_note = "Firebase Storage" if permanent_url else "temporary OpenAI URL"
        print(f"  Firestore PATCH ({storage_note}): {'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
