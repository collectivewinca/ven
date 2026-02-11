#!/usr/bin/env python3
"""
Seed Firebase with initial articles using Google Cloud credentials
Run this in Google Cloud Shell to populate Firestore
"""

import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import json

import os
from dotenv import load_dotenv

load_dotenv()

# Get project ID from environment or use default
project_id = os.getenv("FIREBASE_PROJECT_ID", "miny-ven")

# Use default credentials (works in Cloud Shell or with gcloud auth)
cred = credentials.ApplicationDefault()

# Initialize Firebase
firebase_admin.initialize_app(
    cred,
    {
        "projectId": project_id,
    },
)

db = firestore.client()

# Sample articles to seed
articles = [
    {
        "id": "kanye-west-gospel-album",
        "title": 'Kanye West Releases New Gospel Album "Jesus Is King 2"',
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
        "published_at": datetime(2026, 2, 10, 14, 30).isoformat(),
        "read_time": 60,
        "share_count": 245,
        "email_count": 89,
        "bookmark_count": 156,
        "view_count": 1205,
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "id": "drake-north-american-tour",
        "title": "Drake Announces North American Tour with Special Guest",
        "summary": "Drake reveals massive North American tour dates starting in Toronto this summer. The hip-hop superstar will be joined by 21 Savage and J. Cole for select dates across 30 cities. Tickets go on sale next week with special VIP packages available.",
        "full_content": "Drake reveals massive North American tour dates starting in Toronto this summer. The hip-hop superstar will be joined by 21 Savage and J. Cole for select dates across 30 cities. Tickets go on sale next week with special VIP packages available.",
        "source": "Pitchfork",
        "source_url": "https://pitchfork.com",
        "primary_genre": "hiphop",
        "secondary_genres": ["rap", "canadian"],
        "artist_names": ["Drake", "21 Savage", "J. Cole"],
        "image_url": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800",
        "published_at": datetime(2026, 2, 10, 12, 0).isoformat(),
        "read_time": 60,
        "share_count": 892,
        "email_count": 234,
        "bookmark_count": 445,
        "view_count": 3200,
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "id": "taylor-swift-acoustic-ep",
        "title": "Taylor Swift Drops Surprise Acoustic EP",
        "summary": "Taylor Swift releases unexpected acoustic EP featuring stripped-down versions of hits from Midnights. The 6-track collection showcases raw vocals and piano arrangements recorded at her home studio in Nashville.",
        "full_content": "Taylor Swift releases unexpected acoustic EP featuring stripped-down versions of hits from Midnights. The 6-track collection showcases raw vocals and piano arrangements recorded at her home studio in Nashville. Fans are calling it her most intimate release yet.",
        "source": "Pitchfork",
        "source_url": "https://pitchfork.com",
        "primary_genre": "pop",
        "secondary_genres": ["acoustic", "indie"],
        "artist_names": ["Taylor Swift"],
        "image_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800",
        "published_at": datetime(2026, 2, 10, 10, 15).isoformat(),
        "read_time": 60,
        "share_count": 1523,
        "email_count": 456,
        "bookmark_count": 678,
        "view_count": 5400,
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "id": "arctic-monkeys-new-album",
        "title": "Arctic Monkeys Announce New Album Release Date",
        "summary": "The Sheffield rock legends reveal their seventh studio album will drop next month. Produced by James Ford, the record promises a return to their guitar-driven sound with experimental production techniques.",
        "full_content": "The Sheffield rock legends reveal their seventh studio album will drop next month. Produced by James Ford, the record promises a return to their guitar-driven sound with experimental production techniques. Lead single premieres this Friday.",
        "source": "Pitchfork",
        "source_url": "https://pitchfork.com",
        "primary_genre": "rock",
        "secondary_genres": ["indie", "alternative"],
        "artist_names": ["Arctic Monkeys", "James Ford"],
        "image_url": "https://images.unsplash.com/photo-1511735111819-9a3f77ebd235?w=800",
        "published_at": datetime(2026, 2, 10, 8, 45).isoformat(),
        "read_time": 60,
        "share_count": 567,
        "email_count": 123,
        "bookmark_count": 289,
        "view_count": 2100,
        "fetched_at": datetime.now().isoformat(),
    },
    {
        "id": "daft-punk-reunion-rumors",
        "title": "Daft Punk Reunion Rumors Heat Up for Coachella 2026",
        "summary": "Electronic music fans are buzzing with speculation about a possible Daft Punk comeback at Coachella this year. Industry insiders suggest the French duo has been working on new material.",
        "full_content": "Electronic music fans are buzzing with speculation about a possible Daft Punk comeback at Coachella this year. Industry insiders suggest the French duo has been working on new material. Neither member has confirmed or denied the rumors yet.",
        "source": "Pitchfork",
        "source_url": "https://pitchfork.com",
        "primary_genre": "electronic",
        "secondary_genres": ["house", "french"],
        "artist_names": ["Daft Punk"],
        "image_url": "https://images.unsplash.com/photo-1571266028243-e4733b0f0bb0?w=800",
        "published_at": datetime(2026, 2, 10, 6, 30).isoformat(),
        "read_time": 60,
        "share_count": 2134,
        "email_count": 678,
        "bookmark_count": 890,
        "view_count": 6800,
        "fetched_at": datetime.now().isoformat(),
    },
]

print("🎵 Seeding Firebase with initial articles...")
print(f"Project ID: {project_id}")
print()

for article in articles:
    try:
        db.collection("articles").document(article["id"]).set(article)
        print(f"✓ Added: {article['title'][:50]}...")
    except Exception as e:
        print(f"✗ Error adding {article['id']}: {e}")

print("\n✅ Done! Added 5 articles to Firebase.")
print("\nYour app should now display these articles.")
