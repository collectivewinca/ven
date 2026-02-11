#!/usr/bin/env python3
"""Clean up duplicate articles from Firestore"""

import requests
import json
import re
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FIREBASE_API_KEY", "")
PROJECT_ID = "miny-ven"
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"


def fetch_all_articles():
    """Fetch all articles from Firestore"""
    url = f"{FIRESTORE_URL}/articles?key={API_KEY}"
    response = requests.get(url, timeout=30)

    if response.status_code != 200:
        print(f"Error fetching articles: {response.status_code}")
        return []

    data = response.json()
    return data.get("documents", [])


def find_duplicates(docs):
    """Find duplicate articles based on fuzzy title matching"""
    duplicates = []
    processed = set()

    def extract_key_words(text):
        """Extract significant words from title"""
        common_words = {
            "the",
            "a",
            "an",
            "to",
            "for",
            "of",
            "in",
            "on",
            "at",
            "with",
            "and",
            "is",
            "are",
            "was",
            "were",
            "his",
            "her",
            "their",
            "this",
            "no",
            "joke",
            "new",
            " announces",
            "releases",
            "drops",
        }
        words = re.sub(r"[^\w\s]", "", text.lower()).split()
        return set(w for w in words if w not in common_words and len(w) > 2)

    def calculate_similarity(title1, title2):
        """Calculate Jaccard similarity between two titles"""
        words1 = extract_key_words(title1)
        words2 = extract_key_words(title2)

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    # Compare each article with every other article
    for i, doc1 in enumerate(docs):
        if i in processed:
            continue

        fields1 = doc1.get("fields", {})
        title1 = fields1.get("title", {}).get("stringValue", "")
        doc_id1 = doc1.get("name", "").split("/")[-1]

        group = [(title1, doc_id1)]

        for j, doc2 in enumerate(docs[i + 1 :], start=i + 1):
            if j in processed:
                continue

            fields2 = doc2.get("fields", {})
            title2 = fields2.get("title", {}).get("stringValue", "")
            doc_id2 = doc2.get("name", "").split("/")[-1]

            similarity = calculate_similarity(title1, title2)

            # If 75% or more similar, consider it a duplicate
            if similarity >= 0.75:
                group.append((title2, doc_id2))
                processed.add(j)

        if len(group) > 1:
            duplicates.append(group)
            processed.add(i)

    return duplicates


def delete_article(doc_id):
    """Delete an article from Firestore"""
    url = f"{FIRESTORE_URL}/articles/{doc_id}?key={API_KEY}"
    response = requests.delete(url, timeout=10)
    return response.status_code in [200, 204]


def main():
    print("🧹 Cleaning up duplicate articles...")
    print("=" * 60)

    # Fetch all articles
    docs = fetch_all_articles()
    print(f"Total articles: {len(docs)}")

    # Find duplicates
    duplicate_groups = find_duplicates(docs)

    if not duplicate_groups:
        print("\n✅ No duplicates found!")
        return

    print(f"\nDuplicate groups: {len(duplicate_groups)}")
    print("\nArticles to delete (keeping first occurrence):")

    to_delete = []
    for articles in duplicate_groups:
        print(f"\n{articles[0][0][:70]}...")
        for i, (title, doc_id) in enumerate(articles):
            if i == 0:
                print(f"  ✓ KEEP: {doc_id[:50]}...")
            else:
                print(f"  ✗ DELETE: {doc_id[:50]}...")
                to_delete.append((title, doc_id))

    print(f"\n{'=' * 60}")
    print(f"Total duplicates to remove: {len(to_delete)}")

    # Delete duplicates
    deleted = 0
    for title, doc_id in to_delete:
        if delete_article(doc_id):
            print(f"✓ Deleted: {title[:60]}...")
            deleted += 1
        else:
            print(f"✗ Failed to delete: {title[:60]}...")

    print(f"\n{'=' * 60}")
    print(f"✅ Cleanup complete! Removed {deleted} duplicate articles")
    print(f"Remaining articles: {len(docs) - deleted}")


if __name__ == "__main__":
    main()
