#!/usr/bin/env python3
"""One-shot backfill: generate NVIDIA SD3 images for docs with image_source=none.

Generates images via NVIDIA Stable Diffusion 3 Medium, compresses to WebP,
uploads to Firebase Storage, then patches Firestore with the permanent URL.

Previously used Gemini 2.5 Flash Image — retired 2026-04-20 when the leaked
GEMINI_API_KEY was rotated out of the stack.
"""

import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.request

import requests as req_lib

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

FIREBASE_API_KEY = os.environ["FIREBASE_API_KEY"]
NVIDIA_API_KEY = os.environ["NVIDIA_API_KEY"]
NVIDIA_IMAGE_URL = os.getenv(
    "NVIDIA_IMAGE_URL",
    "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-3-medium",
)
FIREBASE_STORAGE_BUCKET = os.getenv(
    "FIREBASE_STORAGE_BUCKET", "miny-ven.firebasestorage.app"
)
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
        app = firebase_admin.initialize_app(cred)
        bucket_candidates = []
        if FIREBASE_STORAGE_BUCKET:
            bucket_candidates.append(FIREBASE_STORAGE_BUCKET)
        for candidate in ["miny-ven.firebasestorage.app", "miny-ven.appspot.com"]:
            if candidate not in bucket_candidates:
                bucket_candidates.append(candidate)

        for candidate in bucket_candidates:
            try:
                test_bucket = storage.bucket(name=candidate, app=app)
                if test_bucket.exists():
                    _storage_bucket = test_bucket
                    print(f"✓ Firebase Storage initialized (bucket: {candidate})")
                    break
            except Exception:
                continue

        if not _storage_bucket:
            print("⚠ Firebase Storage bucket not found — using data URI fallback")
    except Exception as e:
        print(f"⚠ Firebase Storage init failed: {e}")
else:
    print("⚠ FIREBASE_SERVICE_ACCOUNT_B64 not set — cannot upload images")


def generate_image(title: str, artist: str, genre: str) -> bytes | None:
    """Generate image via NVIDIA SD3 and return raw image bytes."""
    prompt_attempts = [
        (
            "Create a photorealistic editorial hero image for a music news card. "
            "No text, no logo, no watermark, no collage. "
            f"Artist focus: {artist or 'unknown artist'}. "
            f"Genre context: {genre or 'mixed'}. "
            f"Headline context: {title[:180]}."
        ),
        (
            "Generate a cinematic music-magazine hero photo. "
            "Single scene, realistic lighting, no text overlays or logos. "
            f"Genre: {genre or 'mixed'}. Artist cue: {artist or 'unknown artist'}."
        ),
        (
            "Create an abstract-but-photoreal music atmosphere image for a news card. "
            "No text, no logos, no collage. "
            f"Theme: {genre or 'mixed'} music news."
        ),
    ]

    for attempt, prompt in enumerate(prompt_attempts, start=1):
        try:
            resp = req_lib.post(
                NVIDIA_IMAGE_URL,
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"prompt": prompt, "width": 1024, "height": 1024, "steps": 4, "seed": 0},
                timeout=120,
            )
            if resp.status_code != 200:
                print(
                    f"  FAILED: NVIDIA API error (attempt {attempt}): "
                    f"{resp.status_code} — {resp.text[:160]}"
                )
                time.sleep(1.2)
                continue

            data = resp.json()
            # FLUX returns artifacts[0].base64, SD3 returned .image
            image_b64 = data.get("image") or (
                data.get("artifacts", [{}])[0].get("base64", "") if data.get("artifacts") else ""
            )
            if image_b64:
                image_bytes = base64.b64decode(image_b64)
                print(f"  ✓ NVIDIA generated image ({len(image_bytes) // 1024}KB)")
                return image_bytes

            print(
                f"  FAILED: NVIDIA response had no image data (attempt {attempt})"
            )
            time.sleep(1.2)
        except Exception as e:
            print(f"  FAILED: NVIDIA error (attempt {attempt}): {e}")
            time.sleep(1.2)

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
    payload = json.dumps(
        {
            "fields": {
                "image_url": {"stringValue": image_url},
                "image_source": {"stringValue": "ai_generated_nvidia"},
            }
        }
    ).encode()
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
        url = (
            f"{FIRESTORE_URL}/articles?key={FIREBASE_API_KEY}&pageSize=200{token_param}"
        )
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
            artists = (
                fields.get("artist_names", {}).get("arrayValue", {}).get("values", [])
            )
            artist = artists[0].get("stringValue", "") if artists else ""
            doc_id = doc.get("name", "").split("/")[-1]

            # Backfill if no image or image source is "none"
            if not image_url or image_source == "none":
                fetched_at = fields.get("fetched_at", {}).get("stringValue", "")
                docs.append(
                    {
                        "doc_id": doc_id,
                        "title": title,
                        "artist": artist,
                        "genre": genre,
                        "fetched_at": fetched_at,
                    }
                )

        page_token = data.get("nextPageToken", "")
        if not page_token:
            break

    # Sort by most recent first
    docs.sort(key=lambda d: d.get("fetched_at", ""), reverse=True)
    return docs


def main():
    print("🎨 miny-ven Image Backfill (NVIDIA Stable Diffusion 3 Medium)")
    print("=" * 50)

    docs = find_articles_without_images()
    limit = int(os.getenv("BACKFILL_LIMIT", "0"))
    if limit > 0:
        docs = docs[:limit]
    print(f"Found {len(docs)} articles to backfill\n")

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
