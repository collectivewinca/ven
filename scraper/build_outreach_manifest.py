#!/usr/bin/env python3
"""
Build a clean, deduplicated outreach manifest from raw entities.json.

Merges duplicates (Grammy/Grammys/Grammy Awards), removes noise (social
platforms, generic news sites), and outputs outreach_manifest.json ready
for deep research.
"""

import json
import re
from collections import defaultdict

# Canonical name mappings — map variations to a single name
MERGE_MAP = {
    # Artists
    "Beyonce": "Beyoncé",
    "Jay-Z": "JAY-Z",
    "J.Cole": "J. Cole",
    "DEITRICK HADDON": "Deitrick Haddon",
    "Armin Van Buuren": "Armin van Buuren",
    "Leigh-Anne": "Leigh-Anne Pinnock",
    "Sean 'Diddy'": "Diddy",
    "Ye": "Kanye West",
    "Fred again..": "Fred again..",

    # Bands
    "BLACKPINK": "Blackpink",
    "BEARTOOTH": "Beartooth",
    "Tri City Singers": "Tri-City Singers",

    # Festivals
    "Grammys": "Grammy Awards",
    "Grammy": "Grammy Awards",
    "GRAMMY": "Grammy Awards",
    "GRAMMY®": "Grammy Awards",
    "Brit Awards": "BRIT Awards",
    "BRIT Awards 2026": "BRIT Awards",
    "BRITs 2026": "BRIT Awards",
    "The BRIT Awards": "BRIT Awards",
    "The BRIT Awards 2026": "BRIT Awards",
    "Brit Awards 2026": "BRIT Awards",
    "2026 BRIT Awards": "BRIT Awards",
    "NAACP Image Award": "NAACP Image Awards",
    "NAACP Image Awards Hall of Fame": "NAACP Image Awards",
    "Stellar Award": "Stellar Awards",
    "Dove Award": "Dove Awards",
    "Grammy Awards": "Grammy Awards",
    "When We Were Young": "When We Were Young Festival",

    # Venues
    "Manchester's Co-op Live": "Co-op Live",
    "Co-op Live Arena": "Co-op Live",

    # Orgs
    "Youtube": "YouTube",
}

# Entities to exclude entirely (noise, social platforms, generic)
EXCLUDE = {
    # Social platforms & generic tech
    "Billboard", "Instagram", "Facebook", "Twitter", "Apple Music", "Spotify",
    "YouTube", "TikTok", "Pinterest", "NME", "Pitchfork", "EDMTunes",
    "Rolling Stone", "Meta Pay", "EDM House Network", "GospelFlava.com",
    "Amazon Music", "Deezer", "SoundCloud", "Bandcamp", "Tidal",
    "X", "Meta", "Google", "Shazam", "Reddit", "WhatsApp",
    "BBC", "CNN", "The Guardian", "VICE", "Netflix", "Amazon",
    "Meta Store", "Meta Quest", "Ray-Ban Meta", "Meta AI", "Messenger",
    "Facebook Lite", "Tumblr", "RSS", "Bing", "Snapchat", "Page Six",
    "EIN Presswire", "USA TODAY Network", "XPR Media",
    # News aggregation noise
    "Consequence", "HipHopDX", "AllHipHop", "HotNewHipHop", "The Music Universe",
    "Jesusfreakhideout.com", "GodTube.com", "EDM Identity", "Rock Sound",
    "Billboard Hot 100", "Billboard 200",
    # Non-music
    "Anthropic", "ICE", "Department of Homeland Security",
    # Too generic
    "Manchester", "London", "Las Vegas", "King",
}

# Also exclude entries that are clearly not entities
MIN_NAME_LEN = 2


def load_and_merge():
    with open("entities.json") as f:
        data = json.load(f)

    merged = defaultdict(lambda: defaultdict(int))

    for category in ["artists", "bands", "venues", "festivals", "labels", "producers", "organizations"]:
        for item in data["entities"].get(category, []):
            name = item["name"].strip()
            if not name or len(name) < MIN_NAME_LEN:
                continue
            if name in EXCLUDE:
                continue

            # Apply merge map
            canonical = MERGE_MAP.get(name, name)
            if canonical in EXCLUDE:
                continue

            # Remap organizations to music_orgs
            out_cat = "music_orgs" if category == "organizations" else category
            merged[out_cat][canonical] += item["mentions"]

    return merged, data["total_articles"]


def main():
    merged, total_articles = load_and_merge()

    manifest = {
        "total_articles_analyzed": total_articles,
        "extraction_model": "gemini-2.5-flash",
        "categories": {},
    }

    grand_total = 0
    for category in ["artists", "bands", "venues", "festivals", "labels", "producers", "music_orgs"]:
        items = sorted(merged[category].items(), key=lambda x: x[1], reverse=True)
        manifest["categories"][category] = [
            {"name": name, "mention_score": score}
            for name, score in items
        ]
        grand_total += len(items)

    manifest["total_unique_entities"] = grand_total

    with open("outreach_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Print report
    print(f"OUTREACH MANIFEST")
    print(f"{'='*60}")
    print(f"Articles analyzed: {total_articles}")
    print(f"Total unique entities: {grand_total}")
    print()

    for category in ["artists", "bands", "venues", "festivals", "labels", "producers", "music_orgs"]:
        items = manifest["categories"][category]
        label = category.replace("_", " ").upper()
        print(f"\n{label} ({len(items)})")
        print("-" * 50)
        for item in items[:20]:
            bar = "█" * min(20, item["mention_score"] // 5)
            print(f"  {item['mention_score']:3d}  {bar:<20s}  {item['name']}")
        if len(items) > 20:
            print(f"  ... +{len(items) - 20} more (see outreach_manifest.json)")

    print(f"\nSaved to: outreach_manifest.json")


if __name__ == "__main__":
    main()
