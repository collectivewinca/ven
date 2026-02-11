#!/usr/bin/env python3
"""
miny-ven RSS Scraper with OpenRouter Summarization
Fetches music news from RSS feeds and summarizes them to 60 words
Uses REST API instead of firebase_admin
"""

import xml.etree.ElementTree as ET
import requests
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
import os
from pathlib import Path

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "miny-ven")
API_KEY = os.getenv("FIREBASE_API_KEY", "")
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

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
    "rollingstone_music": {
        "url": "https://www.rollingstone.com/music/feed/",
        "genre": "mixed",
        "priority": 2,
    },
    "billboard": {
        "url": "https://www.billboard.com/music/feed/",
        "genre": "mixed",
        "priority": 2,
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
        pass

    def fetch_rss_feed(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed"""
        try:
            response = requests.get(
                url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0 (compatible; miny-ven-bot/1.0)"},
            )
            response.raise_for_status()

            root = ET.fromstring(response.content)
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
            print(f"  ✗ Error fetching RSS from {url}: {e}")
            return []

    def _get_text(self, element, tag: str) -> str:
        """Safely get text from XML element"""
        try:
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
        media = item.find(
            ".//media:content", {"media": "http://search.yahoo.com/mrss/"}
        )
        if media is not None:
            return media.get("url")

        enclosure = item.find(".//enclosure")
        if enclosure is not None:
            return enclosure.get("url")

        content = self._get_text(item, "description") or self._get_text(
            item, "content:encoded"
        )
        if content:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
            if img_match:
                return img_match.group(1)

        return None

    def summarize_with_deepseek(self, title: str, content: str) -> str:
        """Summarize article to exactly 60 words using DeepSeek API"""
        DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
        DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

        if not DEEPSEEK_API_KEY:
            # Fallback without API
            words = content.split()[:60]
            return " ".join(words) + "." if words else title

        prompt = f"""Summarize this music news article in EXACTLY 60 words or less.

Title: {title}

Content: {content[:2000]}

Requirements:
- Exactly 60 words maximum
- Include artist names
- Mention the key development/news
- Keep it engaging and concise
- No filler words

Summary (60 words max):"""

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        }

        data = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional music journalist who writes concise 60-word summaries.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 100,
            "temperature": 0.7,
            "stream": False,
        }

        try:
            response = requests.post(
                DEEPSEEK_URL, headers=headers, json=data, timeout=30
            )
            response.raise_for_status()
            result = response.json()
            summary = result["choices"][0]["message"]["content"].strip()

            words = summary.split()
            if len(words) > 60:
                summary = " ".join(words[:60]) + "."

            return summary
        except Exception as e:
            print(f"  ⚠ DeepSeek error: {e}, using fallback")
            words = content.split()[:60]
            return " ".join(words) + "." if words else title

        prompt = f"""Summarize this music news article in EXACTLY 60 words or less.

Title: {title}

Content: {content[:2000]}

Requirements:
- Exactly 60 words maximum
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

            words = summary.split()
            if len(words) > 60:
                summary = " ".join(words[:60]) + "."

            return summary
        except Exception as e:
            print(f"  ⚠ OpenRouter error: {e}, using fallback")
            words = content.split()[:60]
            return " ".join(words) + "." if words else title

    def classify_genre(self, title: str, content: str, source_genre: str) -> tuple:
        """Classify article genre based on content"""
        text = (title + " " + content).lower()

        if source_genre == "gospel":
            return "gospel", []

        scores = {}
        for genre, keywords in GENRE_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                scores[genre] = score

        if scores:
            primary = max(scores, key=scores.get)
            secondary = [g for g, s in scores.items() if g != primary and s > 0]
            return primary, secondary[:2]

        return "pop", []

    def extract_artists(self, title: str, content: str) -> List[str]:
        """Extract artist names from article"""
        artists = []
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

        return list(dict.fromkeys(artists))[:5]

    def convert_to_firestore_fields(self, data: dict) -> dict:
        """Convert Python dict to Firestore fields format"""
        fields = {}
        for key, value in data.items():
            if isinstance(value, str):
                fields[key] = {"stringValue": value}
            elif isinstance(value, int):
                fields[key] = {"integerValue": str(value)}
            elif isinstance(value, float):
                fields[key] = {"doubleValue": value}
            elif isinstance(value, bool):
                fields[key] = {"booleanValue": value}
            elif isinstance(value, list):
                fields[key] = {
                    "arrayValue": {"values": [{"stringValue": str(v)} for v in value]}
                }
            elif value is None:
                fields[key] = {"nullValue": None}
        return fields

    def check_duplicate(self, title: str) -> bool:
        """Check if article already exists in Firestore using fuzzy matching"""
        try:
            # Fetch all articles and check titles
            url = f"{FIRESTORE_URL}/articles?key={API_KEY}"
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                return False

            data = response.json()
            if not data.get("documents"):
                return False

            # Normalize the new title
            normalized = title.lower().strip()

            # Extract key words (remove common words like "the", "a", "to", etc.)
            def extract_key_words(text):
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
                }
                words = text.lower().strip().split()
                return set(w for w in words if w not in common_words and len(w) > 2)

            new_key_words = extract_key_words(title)

            for doc in data["documents"]:
                fields = doc.get("fields", {})
                existing_title = (
                    fields.get("title", {}).get("stringValue", "").lower().strip()
                )

                # Check for exact match
                if existing_title == normalized:
                    return True

                # Check for high similarity (if key words overlap significantly)
                existing_key_words = extract_key_words(existing_title)
                if new_key_words and existing_key_words:
                    # Calculate Jaccard similarity
                    intersection = len(new_key_words & existing_key_words)
                    union = len(new_key_words | existing_key_words)
                    if union > 0:
                        similarity = intersection / union
                        # If 80% or more key words match, consider it a duplicate
                        if similarity >= 0.8:
                            print(
                                f"  ⚠ Similar title detected ({similarity:.0%} match): {existing_title[:50]}..."
                            )
                            return True

            return False
        except Exception as e:
            print(f"  ⚠ Error checking duplicate: {e}")
            return False

    def save_to_firebase(self, article: Article):
        """Save article to Firebase Firestore via REST API"""
        try:
            article_dict = asdict(article)
            article_dict["published_at"] = article.published_at.isoformat()
            article_dict["fetched_at"] = article.fetched_at.isoformat()

            doc_id = re.sub(r"[^a-zA-Z0-9]", "-", article.title.lower())[:50]

            url = f"{FIRESTORE_URL}/articles/{doc_id}?key={API_KEY}"
            payload = {"fields": self.convert_to_firestore_fields(article_dict)}

            response = requests.patch(url, json=payload, timeout=10)

            if response.status_code in [200, 201]:
                print(f"  ✓ Saved: {article.title[:60]}...")
                return True
            else:
                print(f"  ✗ Failed to save: {response.status_code}")
                return False
        except Exception as e:
            print(f"  ✗ Error saving to Firebase: {e}")
            return False

    def process_feed(self, source_name: str, source_config: Dict):
        """Process a single RSS feed"""
        print(f"\n📡 Fetching {source_name}...")

        items = self.fetch_rss_feed(source_config["url"])
        print(f"  Found {len(items)} items")

        processed = 0
        for item in items[:5]:  # Process top 5 items per feed
            try:
                if self.check_duplicate(item["title"]):
                    print(f"  ⚠ Duplicate: {item['title'][:50]}...")
                    continue

                content = item["content"] or item["description"]
                summary = self.summarize_with_deepseek(item["title"], content)

                primary_genre, secondary_genres = self.classify_genre(
                    item["title"], content, source_config["genre"]
                )

                artists = self.extract_artists(item["title"], content)

                try:
                    pub_date = datetime.strptime(
                        item["pub_date"], "%a, %d %b %Y %H:%M:%S %z"
                    )
                except:
                    pub_date = datetime.now()

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
                    image_url=item["image"]
                    or "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800",
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                )

                if self.save_to_firebase(article):
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
        print(f"Project: {PROJECT_ID}")
        print()

        if not API_KEY:
            print("⚠️  Warning: FIREBASE_API_KEY not set. Articles won't be saved.")
            print()

        if not OPENROUTER_API_KEY:
            print("⚠️  Warning: OPENROUTER_API_KEY not set. Using basic summaries.")
            print()

        total_processed = 0

        for source_name, config in RSS_SOURCES.items():
            try:
                processed = self.process_feed(source_name, config)
                total_processed += processed
            except Exception as e:
                print(f"  ✗ Error with {source_name}: {e}")
                continue

        print("\n" + "=" * 50)
        print(f"✅ Complete! Added {total_processed} new articles")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    scraper = RSSScraper()
    scraper.run()
