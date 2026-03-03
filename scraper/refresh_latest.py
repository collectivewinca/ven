#!/usr/bin/env python3
"""
Refresh the latest 20 articles in Firestore with new CTA titles and summaries
using Gemini 3 Flash Preview.
"""

import json
import requests
import time

GEMINI_API_KEY = "AIzaSyBstb1UtEi88OZx497UX7G6slItECSI640"
GEMINI_MODEL = "gemini-3-flash-preview"
PROJECT_ID = "miny-ven"
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"


def fetch_latest_articles(n=20):
    """Fetch latest n articles from Firestore."""
    fields = [
        "title", "summary", "source", "source_url", "primary_genre",
        "full_content", "artist_names", "published_at"
    ]
    params = {"pageSize": str(n)}
    for f in fields:
        params.setdefault("mask.fieldPaths", [])
    # Build URL with multiple mask.fieldPaths
    base = f"{FIRESTORE_URL}/articles"
    field_params = "&".join(f"mask.fieldPaths={f}" for f in fields)
    url = f"{base}?pageSize={n}&{field_params}"

    r = requests.get(url, timeout=30)
    r.raise_for_status()
    docs = r.json().get("documents", [])

    # Sort by published_at desc
    def get_pub(doc):
        pa = doc.get("fields", {}).get("published_at", {}).get("stringValue", "")
        return pa
    docs.sort(key=get_pub, reverse=True)
    return docs[:n]


def get_field(fields, name):
    f = fields.get(name, {})
    if "stringValue" in f:
        return f["stringValue"]
    if "arrayValue" in f:
        return [v.get("stringValue", "") for v in f.get("arrayValue", {}).get("values", [])]
    return ""


def generate_cta_title(original_title, content, artist):
    """Generate high-CTA headline using Gemini."""
    prompt = f"""Create an engaging, click-worthy headline for this music news story.

Original Title: {original_title}
Artist: {artist}
Content: {content[:800]}

Requirements:
- Write a NEW headline (NOT a copy of the original)
- Use power words that drive clicks (Breaking, Exclusive, Revealed, Unveiled, etc.)
- Create curiosity or urgency
- Keep under 80 characters
- Make it punchy and shareable for a music news app
- Return ONLY the headline text, nothing else

New CTA Headline:"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": "You are a viral headline writer for a music news app. Return ONLY the headline, no quotes, no markdown."}]
        },
        "generationConfig": {"maxOutputTokens": 512, "temperature": 0.8},
    }

    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    # Clean up quotes, markdown, and reasoning leaks
    text = text.strip('"\'').strip()
    if text.startswith("**") and text.endswith("**"):
        text = text[2:-2]
    # Take only first line to prevent thinking-model reasoning leaks
    text = text.split("\n")[0].strip()
    return text[:200]


def generate_summary(title, content):
    """Generate 60-word summary using Gemini."""
    prompt = f"""Summarize this music news article in EXACTLY 60 words or less.

Title: {title}

Content: {content[:2000]}

Requirements:
- Exactly 60 words maximum
- Include artist names, labels, or platforms mentioned
- Mention the key development or news angle
- Write in a punchy music-journalist tone
- No filler words, no meta-commentary

Summary (60 words max):"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {
            "parts": [{"text": "You are a professional music journalist who writes concise 60-word news briefs for creators."}]
        },
        "generationConfig": {"maxOutputTokens": 256, "temperature": 0.7},
    }

    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    words = text.split()
    if len(words) > 60:
        text = " ".join(words[:60]) + "."
    return text


def patch_article(doc_name, new_title, new_summary):
    """Patch title and summary fields in Firestore."""
    url = f"https://firestore.googleapis.com/v1/{doc_name}?updateMask.fieldPaths=title&updateMask.fieldPaths=summary"
    payload = {
        "fields": {
            "title": {"stringValue": new_title},
            "summary": {"stringValue": new_summary},
        }
    }
    r = requests.patch(url, json=payload, timeout=15)
    r.raise_for_status()
    return True


def main():
    print("Fetching latest 20 articles from Firestore...")
    docs = fetch_latest_articles(20)
    print(f"Got {len(docs)} articles\n")

    for i, doc in enumerate(docs, 1):
        fields = doc.get("fields", {})
        doc_name = doc["name"]
        doc_id = doc_name.split("/")[-1]

        old_title = get_field(fields, "title")
        old_summary = get_field(fields, "summary")
        content = get_field(fields, "full_content") or old_summary
        artists = get_field(fields, "artist_names")
        artist = artists[0] if isinstance(artists, list) and artists else ""
        genre = get_field(fields, "primary_genre")
        source = get_field(fields, "source")

        print(f"[{i}/20] {old_title[:70]}...")
        print(f"        genre={genre} source={source} artist={artist}")

        try:
            new_title = generate_cta_title(old_title, content, artist)
            time.sleep(0.5)  # Rate limit
            new_summary = generate_summary(new_title, content)
            time.sleep(0.5)

            print(f"   NEW: {new_title[:70]}")
            print(f"   SUM: {new_summary[:80]}...")

            patch_article(doc_name, new_title, new_summary)
            print(f"   ✓ Updated\n")

        except Exception as e:
            print(f"   ✗ Error: {e}\n")
            continue

    print("Done! Refresh ven.minyvinyl.com to see updated articles.")


if __name__ == "__main__":
    main()
