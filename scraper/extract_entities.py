#!/usr/bin/env python3
"""
Entity extraction from miny-ven Firestore articles.

Uses Ollama Cloud (minimax-m2.7) via ollama_client.chat to extract structured
entities (artists, bands, venues, festivals, labels, producers) from article
titles + content. Outputs a deduplicated JSON manifest for outreach research.

Previously used Gemini 2.5 Flash with a hardcoded API key — that key leaked
in git history of the archived miny-ven repo and was retired 2026-04-20.
"""

import json
import os
import re
import time
from collections import defaultdict

import requests

from ollama_client import chat, OllamaError

PROJECT_ID = "miny-ven"
FIRESTORE_URL = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    f"/databases/(default)/documents"
)

BATCH_SIZE = 5  # Articles per Gemini call (keeps prompt reasonable)


def fetch_all_articles():
    """Fetch every article from Firestore."""
    fields = [
        "title", "summary", "full_content", "primary_genre",
        "source", "source_url", "artist_names", "published_at",
    ]
    field_params = "&".join(f"mask.fieldPaths={f}" for f in fields)

    all_docs = []
    next_token = None
    while True:
        url = f"{FIRESTORE_URL}/articles?pageSize=100&{field_params}"
        if next_token:
            url += f"&pageToken={next_token}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        all_docs.extend(data.get("documents", []))
        next_token = data.get("nextPageToken")
        if not next_token:
            break

    return all_docs


def get_field(fields, name):
    f = fields.get(name, {})
    if "stringValue" in f:
        return f["stringValue"]
    if "arrayValue" in f:
        return [v.get("stringValue", "") for v in f.get("arrayValue", {}).get("values", [])]
    return ""


def extract_entities_batch(articles_text: str) -> dict:
    """Send a batch of article summaries to Ollama Cloud for entity extraction."""
    prompt = f"""Extract ALL named entities from these music news articles.

{articles_text}

Return a JSON object with these arrays (no duplicates within each):

{{
  "artists": ["name1", "name2"],
  "bands": ["name1", "name2"],
  "venues": ["name1", "name2"],
  "festivals": ["name1", "name2"],
  "labels": ["name1", "name2"],
  "producers": ["name1", "name2"],
  "organizations": ["name1", "name2"]
}}

Rules:
- Artists = solo performers, singers, rappers, DJs
- Bands = groups, duos, ensembles
- Venues = concert halls, arenas, clubs, stadiums
- Festivals = music festivals, award shows (Grammy, SOAR, BET, etc.)
- Labels = record labels, music publishers, distributors
- Producers = music producers, beatmakers, songwriters
- Organizations = streaming platforms, music tech companies, industry orgs
- Include EVERY entity mentioned, even minor ones
- Use proper capitalization
- Do NOT include generic terms like "artists", "bands", "musicians"
- Return ONLY the JSON, no explanation"""

    try:
        text = chat(
            prompt=prompt,
            system="You are a music industry entity extractor. Return ONLY valid JSON, nothing else.",
            max_tokens=2048,
            temperature=0.2,
        )
    except OllamaError as e:
        print(f"  Warning: Ollama call failed: {e}")
        return {}

    # Extract JSON from potential markdown code block
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    # Or just find the first { ... }
    elif not text.startswith("{"):
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            text = text[brace_start:brace_end]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  Warning: Could not parse JSON response")
        return {}


def main():
    print("Fetching all articles from Firestore...")
    docs = fetch_all_articles()
    print(f"Got {len(docs)} articles\n")

    # Build article text blocks for batching
    article_blocks = []
    article_meta = []
    for doc in docs:
        fields = doc.get("fields", {})
        title = get_field(fields, "title")
        summary = get_field(fields, "summary")
        content = get_field(fields, "full_content") or summary
        genre = get_field(fields, "primary_genre")
        source = get_field(fields, "source")
        doc_id = doc["name"].split("/")[-1]

        block = f"[{genre.upper()}] {title}\n{content[:500]}"
        article_blocks.append(block)
        article_meta.append({
            "doc_id": doc_id,
            "title": title,
            "genre": genre,
            "source": source,
        })

    # Process in batches
    all_entities = defaultdict(lambda: defaultdict(set))
    # all_entities[category][entity_name] = set of article doc_ids

    total_batches = (len(article_blocks) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(article_blocks), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = article_blocks[i:i + BATCH_SIZE]
        batch_meta = article_meta[i:i + BATCH_SIZE]
        batch_text = "\n\n---\n\n".join(batch)

        print(f"[Batch {batch_num}/{total_batches}] Processing {len(batch)} articles...")

        try:
            result = extract_entities_batch(batch_text)
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(1)
            continue

        # Merge results
        for category in ["artists", "bands", "venues", "festivals", "labels", "producers", "organizations"]:
            for entity in result.get(category, []):
                entity = entity.strip()
                if entity and len(entity) > 1:
                    # Track which articles mentioned this entity
                    for meta in batch_meta:
                        all_entities[category][entity].add(meta["doc_id"])

        time.sleep(0.5)  # Rate limit

    # Build output manifest
    manifest = {"total_articles": len(docs), "entities": {}}

    for category in ["artists", "bands", "venues", "festivals", "labels", "producers", "organizations"]:
        entities = all_entities[category]
        sorted_entities = sorted(
            entities.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )
        manifest["entities"][category] = [
            {"name": name, "mentions": len(doc_ids), "article_ids": sorted(doc_ids)}
            for name, doc_ids in sorted_entities
        ]

    # Write manifest
    out_path = os.path.join(os.path.dirname(__file__), "entities.json")
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"ENTITY EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Articles analyzed: {len(docs)}")
    print()

    for category in ["artists", "bands", "venues", "festivals", "labels", "producers", "organizations"]:
        items = manifest["entities"][category]
        print(f"\n{category.upper()} ({len(items)} unique)")
        print("-" * 40)
        for item in items[:15]:
            print(f"  {item['mentions']:2d}x  {item['name']}")
        if len(items) > 15:
            print(f"  ... and {len(items) - 15} more")

    print(f"\nFull manifest saved to: {out_path}")


if __name__ == "__main__":
    main()
