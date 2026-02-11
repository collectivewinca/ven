#!/usr/bin/env python3
"""
miny-ven RSS Scraper with OpenRouter Summarization
Fetches music news from RSS feeds and summarizes them to 60 words
"""

import xml.etree.ElementTree as ET
import requests
import json
import re
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
import firebase_admin
from firebase_admin import credentials, firestore
import os
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# RSS Feed Sources
RSS_SOURCES = {
    "jesusfreakhideout": {
        "url": "https://www.jesusfreakhideout.com/news/feed.xml",
        "genre": "gospel",
        "priority": 1,
    },
    "pitchfork_news": {
        "url": "https://pitchfork.com/feed/feed-news/rss",
        "genre": "mixed",
        "priority": 2,
    },
    "pitchfork_reviews": {
        "url": "https://pitchfork.com/feed/feed-album-reviews/rss",
        "genre": "mixed",
        "priority": 2,
    },
    "crossrhythms": {
        "url": "http://www.crossrhythms.co.uk/news/rss.xml",
        "genre": "gospel",
        "priority": 3,
    },
}

# Genre classification keywords
GENRE_KEYWORDS = {
    "gospel": [
        "gospel",
        "christian",
        "worship",
        "ccm",
        "church",
        "hymn",
        "praise",
        "jesus",
        "god",
    ],
    "hiphop": ["hip-hop", "rap", "trap", "r&b", "rnb", "drill", "grime", "mumble"],
    "pop": ["pop", "mainstream", "chart", "top 40", "bubblegum", "synth-pop"],
    "rock": ["rock", "alternative", "indie", "punk", "metal", "grunge", "garage"],
    "electronic": [
        "electronic",
        "edm",
        "house",
        "techno",
        "dubstep",
        "trance",
        "ambient",
    ],
}


@dataclass
class Article:
    id: str
    title: str
    summary: str
    full_content: str
    source: str
    source_url: str
    primary_genre: str
    secondary_genres: List[str]
    artist_names: List[str]
    image_url: Optional[str]
    published_at: datetime
    read_time: int
    share_count: int
    email_count: int
    bookmark_count: int
    view_count: int
    fetched_at: datetime


class RSSScraper:
    def __init__(self):
        self.db = self._init_firebase()

    def _init_firebase(self):
        """Initialize Firebase connection"""
        try:
            # Try to use existing app
            return firestore.client()
        except ValueError:
            # Initialize new app
            # You'll need to download your Firebase service account key
            cred_path = Path(__file__).parent / "firebase-credentials.json"
            if cred_path.exists():
                cred = credentials.Certificate(str(cred_path))
                firebase_admin.initialize_app(cred)
            else:
                # Use default credentials (for local development)
                firebase_admin.initialize_app()
            return firestore.client()

    def fetch_rss_feed(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            # Extract items
            items = []
            for item in root.findall(".//item"):
                article = {
                    "title": self._get_text(item, "title"),
                    "link": self._get_text(item, "link"),
                    "description": self._get_text(item, "description"),
                    "pub_date": self._get_text(item, "pubDate"),
                    "content": self._get_text(item, "content:encoded")
                    or self._get_text(item, "description"),
                    "image": self._extract_image(item),
                }
                if article["title"] and article["link"]:
                    items.append(article)

            return items
        except Exception as e:
            print(f"Error fetching RSS from {url}: {e}")
            return []

    def _get_text(self, element, tag: str) -> str:
        """Safely get text from XML element"""
        try:
            # Try with namespace
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            if ":" in tag:
                elem = element.find(f".//{tag}", ns)
            else:
                elem = element.find(f".//{tag}")
            return elem.text.strip() if elem is not None and elem.text else ""
        except:
            return ""

    def _extract_image(self, item) -> Optional[str]:
        """Extract image URL from RSS item"""
        # Try media:content
        media = item.find(
            ".//media:content", {"media": "http://search.yahoo.com/mrss/"}
        )
        if media is not None:
            return media.get("url")

        # Try enclosure
        enclosure = item.find(".//enclosure")
        if enclosure is not None:
            return enclosure.get("url")

        # Try to extract from description/content
        content = self._get_text(item, "description") or self._get_text(
            item, "content:encoded"
        )
        if content:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            if img_match:
                return img_match.group(1)

        return None

    def summarize_with_openrouter(self, title: str, content: str) -> str:
        """Summarize article to exactly 60 words using OpenRouter"""
        prompt = f"""Summarize this music news article in EXACTLY 60 words or less.

Title: {title}

Content: {content[:2000]}

Requirements:
- Exactly 60 words maximum (count carefully)
- Include artist names
- Mention the key development/news
- Keep it engaging and concise
- No filler words

Summary (60 words max):"""

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://miny-ven.vercel.app",
            "X-Title": "miny-ven",
        }

        data = {
            "model": "mistralai/mistral-7b-instruct:free",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional music journalist who writes concise 60-word summaries.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 100,
            "temperature": 0.7,
        }

        try:
            response = requests.post(
                OPENROUTER_URL, headers=headers, json=data, timeout=30
            )
            response.raise_for_status()
            result = response.json()

            summary = result["choices"][0]["message"]["content"].strip()

            # Ensure it's max 60 words
            words = summary.split()
            if len(words) > 60:
                summary = " ".join(words[:60]) + "."

            return summary
        except Exception as e:
            print(f"Error summarizing with OpenRouter: {e}")
            # Fallback: return first 60 words of content
            words = content.split()[:60]
            return " ".join(words) + "." if words else title

    def classify_genre(self, title: str, content: str, source_genre: str) -> tuple:
        """Classify article genre based on content"""
        text = (title + " " + content).lower()

        # If source is specifically gospel, trust it
        if source_genre == "gospel":
            return "gospel", []

        # Count keyword matches for each genre
        scores = {}
        for genre, keywords in GENRE_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                scores[genre] = score

        if scores:
            # Get genre with highest score
            primary = max(scores, key=scores.get)
            # Get secondary genres (other genres with scores)
            secondary = [g for g, s in scores.items() if g != primary and s > 0]
            return primary, secondary[:2]  # Max 2 secondary genres

        # Default to pop if no match
        return "pop", []

    def extract_artists(self, title: str, content: str) -> List[str]:
        """Extract artist names from article using simple heuristics"""
        artists = []

        # Common patterns: "Artist Name Announces...", "Artist Name Releases..."
        patterns = [
            r"^([A-Z][a-zA-Z\s]+)(?:Announces?|Releases?|Drops?|Debuts?|Wins?)",
            r"([A-Z][a-zA-Z\s]+)(?:and|&)\s+([A-Z][a-zA-Z\s]+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, title)
            for match in matches:
                if isinstance(match, tuple):
                    artists.extend([m.strip() for m in match if m.strip()])
                else:
                    artist = match.strip()
                    if artist and len(artist) > 2:
                        artists.append(artist)

        # Remove duplicates and limit
        return list(dict.fromkeys(artists))[:5]  # Max 5 artists

    def check_duplicate(self, title: str) -> bool:
        """Check if article already exists in Firestore"""
        try:
            # Normalize title for comparison
            normalized = title.lower().strip()

            # Check recent articles (last 7 days)
            docs = (
                self.db.collection("articles")
                .where("fetched_at", ">", datetime.now() - timedelta(days=7))
                .stream()
            )

            for doc in docs:
                if doc.to_dict().get("title", "").lower().strip() == normalized:
                    return True

            return False
        except Exception as e:
            print(f"Error checking duplicate: {e}")
            return False

    def save_to_firebase(self, article: Article):
        """Save article to Firebase Firestore"""
        try:
            # Convert to dict
            article_dict = asdict(article)
            # Convert datetime to string for JSON serialization
            article_dict["published_at"] = article.published_at.isoformat()
            article_dict["fetched_at"] = article.fetched_at.isoformat()

            # Generate unique ID from title
            doc_id = re.sub(r"[^a-zA-Z0-9]", "-", article.title.lower())[:50]

            # Save to Firestore
            self.db.collection("articles").document(doc_id).set(article_dict)
            print(f"✓ Saved: {article.title[:60]}...")

        except Exception as e:
            print(f"Error saving to Firebase: {e}")

    def process_feed(self, source_name: str, source_config: Dict):
        """Process a single RSS feed"""
        print(f"\n📡 Fetching {source_name}...")

        items = self.fetch_rss_feed(source_config["url"])
        print(f"  Found {len(items)} items")

        processed = 0
        for item in items[:5]:  # Process top 5 items per feed
            try:
                # Check for duplicate
                if self.check_duplicate(item["title"]):
                    print(f"  ⚠ Duplicate: {item['title'][:50]}...")
                    continue

                # Summarize content
                content = item["content"] or item["description"]
                summary = self.summarize_with_openrouter(item["title"], content)

                # Classify genre
                primary_genre, secondary_genres = self.classify_genre(
                    item["title"], content, source_config["genre"]
                )

                # Extract artists
                artists = self.extract_artists(item["title"], content)

                # Parse date
                try:
                    pub_date = datetime.strptime(
                        item["pub_date"], "%a, %d %b %Y %H:%M:%S %z"
                    )
                except:
                    pub_date = datetime.now()

                # Create article object
                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", item["title"].lower())[:50],
                    title=item["title"],
                    summary=summary,
                    full_content=content[:2000],
                    source=source_name.replace("_", " ").title(),
                    source_url=item["link"],
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=item["image"],
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                )

                # Save to Firebase
                self.save_to_firebase(article)
                processed += 1

            except Exception as e:
                print(f"  ✗ Error processing item: {e}")
                continue

        return processed

    def run(self):
        """Run the scraper for all sources"""
        print("🎵 miny-ven RSS Scraper")
        print("=" * 50)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        total_processed = 0

        for source_name, config in RSS_SOURCES.items():
            try:
                processed = self.process_feed(source_name, config)
                total_processed += processed
            except Exception as e:
                print(f"✗ Error with {source_name}: {e}")
                continue

        print("\n" + "=" * 50)
        print(f"✅ Complete! Processed {total_processed} new articles")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    from datetime import timedelta

    scraper = RSSScraper()
    scraper.run()
