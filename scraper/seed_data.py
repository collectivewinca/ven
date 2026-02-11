#!/usr/bin/env python3
"""
Seed Firebase with initial articles from mock data
Run this to populate Firestore before the RSS scraper takes over
"""

import json
from datetime import datetime
from pathlib import Path

# Mock articles data (same as frontend)
mock_articles = [
    {
        "id": "kanye-west-gospel-album",
        "title": "Kanye West Releases New Gospel Album",
        "summary": "Kanye West drops surprise sequel to his 2019 gospel album featuring Sunday Service Choir. The 12-track project includes collaborations with Kirk Franklin and Fred Hammond, blending traditional gospel with contemporary hip-hop production.",
        "full_content": "Kanye West drops surprise sequel to his 2019 gospel album featuring Sunday Service Choir. The 12-track project includes collaborations with Kirk Franklin and Fred Hammond, blending traditional gospel with contemporary hip-hop production.",
        "source": "Jesusfreakhideout",
        "source_url": "https://www.jesusfreakhideout.com",
        "primary_genre": "gospel",
        "secondary_genres": ["hip-hop", "contemporary"],
        "artist_names": [
            "Kanye West",
            "Sunday Service Choir",
            "Kirk Franklin",
            "Fred Hammond",
        ],
        "image_url": "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=800",
        "published_at": "2026-02-10T14:30:00",
        "read_time": 60,
        "share_count": 245,
        "email_count": 89,
        "bookmark_count": 156,
        "view_count": 1205,
        "fetched_at": "2026-02-10T20:00:00",
    },
    {
        "id": "drake-north-american-tour",
        "title": "Drake Announces North American Tour with Special Guest",
        "summary": "Drake reveals massive North American tour dates starting in Toronto this summer. The hip-hop superstar will be joined by 21 Savage and J. Cole for select dates across 30 cities.",
        "full_content": "Drake reveals massive North American tour dates starting in Toronto this summer. The hip-hop superstar will be joined by 21 Savage and J. Cole for select dates across 30 cities. Tickets go on sale next week with special VIP packages available.",
        "source": "Pitchfork",
        "source_url": "https://pitchfork.com",
        "primary_genre": "hiphop",
        "secondary_genres": ["rap", "canadian"],
        "artist_names": ["Drake", "21 Savage", "J. Cole"],
        "image_url": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800",
        "published_at": "2026-02-10T12:00:00",
        "read_time": 60,
        "share_count": 892,
        "email_count": 234,
        "bookmark_count": 445,
        "view_count": 3200,
        "fetched_at": "2026-02-10T20:00:00",
    },
    {
        "id": "taylor-swift-acoustic-ep",
        "title": "Taylor Swift Drops Surprise Acoustic EP",
        "summary": "Taylor Swift releases unexpected acoustic EP featuring stripped-down versions of hits from Midnights. The 6-track collection showcases raw vocals and piano arrangements.",
        "full_content": "Taylor Swift releases unexpected acoustic EP featuring stripped-down versions of hits from Midnights. The 6-track collection showcases raw vocals and piano arrangements recorded at her home studio in Nashville.",
        "source": "Pitchfork",
        "source_url": "https://pitchfork.com",
        "primary_genre": "pop",
        "secondary_genres": ["acoustic", "indie"],
        "artist_names": ["Taylor Swift"],
        "image_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800",
        "published_at": "2026-02-10T10:15:00",
        "read_time": 60,
        "share_count": 1523,
        "email_count": 456,
        "bookmark_count": 678,
        "view_count": 5400,
        "fetched_at": "2026-02-10T20:00:00",
    },
]

# Save as JSON for easy import
output_file = Path(__file__).parent / "seed_data.json"
with open(output_file, "w") as f:
    json.dump(mock_articles, f, indent=2)

print(f"Seed data saved to {output_file}")
print(f"Total articles: {len(mock_articles)}")
print("\nTo import to Firebase:")
print("1. Go to Firebase Console > Firestore Database")
print("2. Import JSON file to 'articles' collection")
print("3. Or run: python seed_firebase.py")
