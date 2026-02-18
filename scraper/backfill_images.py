#!/usr/bin/env python3
"""One-shot backfill: generate Gemini images for docs with image_source=none.

Generates images via Gemini 2.5 Flash, compresses to WebP, uploads to
Firebase Storage, then patches Firestore with the permanent URL.
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

FIREBASE_API_KEY = os.environ["FIREBASE_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
FIRESTORE_URL = "https://firestore.googleapis.com/v1/projects/miny-ven/databases/(default)/documents"

# Firebase Storage
_storage_bucket = None
FIREBASE_SA_B64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "")
if FIREBASE_SA_B64:
    try:
        import firebase_admin
        from firebase_admin import credentials, storage

        sa_info = json.loads(base64.b64decode(FIREBASE_SA_B64))
        cred = credentials.Certificate(sa_info)
        firebase_admin.initialize_app(
            cred, {"storageBucket": "miny-ven.appspot.com"}
        )
        _storage_bucket = storage.bucket()
        print("✓ Firebase Storage initialized")
    except Exception as e:
        print(f"⚠ Firebase Storage init failed: {e}")
else:
    print("⚠ FIREBASE_SERVICE_ACCOUNT_B64 not set — cannot upload images")


def generate_image(title: str, artist: str, genre: str) -> bytes | None:
    """Generate image via Gemini and return raw image bytes."""
    prompt = (
        "Create a photorealistic editorial hero image for a music news card. "
        "No text, no logo, no watermark, no collage. "
        f"Artist focus: {artist or 'unknown artist'}. "
        f"Genre context: {genre or 'mixed'}. "
        f"Headline context: {title[:180]}."
    )

    api_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_IMAGE_MODEL}:generateContent"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }).encode()

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())

        parts = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        for part in parts:
            # REST API uses camelCase (inlineData/mimeType)
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                image_bytes = base64.b64decode(inline["data"])
                print(f"  ✓ Gemini generated image ({len(image_bytes) // 1024}KB)")
                return image_bytes

        print("  FAILED: Gemini response contained no image data")
        return None
    except Exception as e:
        print(f"  FAILED: Gemini error: {e}")
        return None


def compress_and_upload(image_bytes: bytes, title: str) -> str | None:
    """Compress raw bytes to WebP. Upload to Firebase Storage if available,
    otherwise return a data URI for direct embedding."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        max_width = 800
        quality = 80 if _storage_bucket else 70

        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=quality)
        webp_bytes = buf.getvalue()

        # Try Firebase Storage first
        if _storage_bucket:
            try:
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-")
                digest = hashlib.sha1(image_bytes[:256]).hexdigest()[:12]
                storage_path = f"article-images/{slug}-{digest}.webp"

                blob = _storage_bucket.blob(storage_path)
                blob.upload_from_string(webp_bytes, content_type="image/webp")
                blob.make_public()

                print(f"  ✓ Uploaded ({len(webp_bytes) // 1024}KB): {storage_path}")
                return blob.public_url
            except Exception as e:
                print(f"  ⚠ Storage upload failed, using data URI: {e}")

        # Fallback: return data URI
        b64 = base64.b64encode(webp_bytes).decode()
        data_uri = f"data:image/webp;base64,{b64}"
        print(f"  ✓ Generated data URI ({len(webp_bytes) // 1024}KB)")
        return data_uri
    except Exception as e:
        print(f"  ⚠ Compression failed: {e}")
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
            "image_source": {"stringValue": "ai_generated_gemini"},
        }
    }).encode()
    req = urllib.request.Request(url, data=payload, method="PATCH")
    req.add_header("Content-Type", "application/json")
    resp = urllib.request.urlopen(req, timeout=15)
    return resp.status in (200, 201)


def find_articles_without_images() -> list[dict]:
    """Query Firestore for articles with empty or missing image_url."""
    docs = []
    page_token = ""

    while True:
        token_param = f"&pageToken={page_token}" if page_token else ""
        url = f"{FIRESTORE_URL}/articles?key={FIREBASE_API_KEY}&pageSize=200{token_param}"
        resp = req_lib.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"⚠ Could not list articles: {resp.status_code}")
            break

        data = resp.json()
        for doc in data.get("documents", []):
            fields = doc.get("fields", {})
            image_url = fields.get("image_url", {}).get("stringValue", "").strip()
            image_source = fields.get("image_source", {}).get("stringValue", "")
            title = fields.get("title", {}).get("stringValue", "")
            genre = fields.get("primary_genre", {}).get("stringValue", "")
            artists = fields.get("artist_names", {}).get("arrayValue", {}).get("values", [])
            artist = artists[0].get("stringValue", "") if artists else ""
            doc_id = doc.get("name", "").split("/")[-1]

            # Backfill if no image or image source is "none"
            if not image_url or image_source == "none":
                docs.append({
                    "doc_id": doc_id,
                    "title": title,
                    "artist": artist,
                    "genre": genre,
                })

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    return docs


def main():
    print(f"🎨 miny-ven Image Backfill (Gemini {GEMINI_IMAGE_MODEL})")
    print("=" * 50)

    docs = find_articles_without_images()
    print(f"Found {len(docs)} articles needing images\n")

    success = 0
    for doc in docs:
        print(f"\n--- {doc['doc_id']} ---")
        print(f"Generating image for: {doc['title'][:60]}")

        image_bytes = generate_image(doc["title"], doc["artist"], doc["genre"])
        if not image_bytes:
            continue

        permanent_url = compress_and_upload(image_bytes, doc["title"])
        if not permanent_url:
            continue

        ok = patch_firestore(doc["doc_id"], permanent_url)
        print(f"  Firestore PATCH: {'OK' if ok else 'FAILED'}")
        if ok:
            success += 1

    print(f"\n{'=' * 50}")
    print(f"✅ Backfilled {success}/{len(docs)} articles with Gemini images")


if __name__ == "__main__":
    main()
