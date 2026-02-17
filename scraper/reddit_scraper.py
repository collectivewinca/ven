#!/usr/bin/env python3
"""
miny-ven Reddit Scraper for Artist Discovery
Fetches trending music posts from Reddit using hf CLI
"""

import subprocess
import json
import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
import os
from html import escape as html_escape
from dataclasses import dataclass, asdict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urlunparse

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Configuration
PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "miny-ven")
API_KEY = os.getenv("FIREBASE_API_KEY", "")
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"
PUBLIC_APP_URL = (
    os.getenv("PUBLIC_APP_URL")
    or os.getenv("VITE_PUBLIC_APP_URL")
    or "https://minyven-news.vercel.app"
).rstrip("/")

SCRAPER_VERSION = "2026-02-13-reddit"
DEFAULT_TIMEOUT_SECONDS = 30


def _safe_int(val, default=0):
    """Safely convert a value to int, handling '1.2k' style strings"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

# Music subreddits to monitor
MUSIC_SUBREDDITS = [
    "hiphopheads",  # Hip-hop releases, news, discussions
    "Music",  # General music
    "indieheads",  # Indie/alternative
    "popheads",  # Pop music
    "electronicmusic",  # Electronic music
    "gospelmusic",  # Gospel music
    "rock",  # Rock music
    "rnb",  # R&B music
    "jazz",  # Jazz music
    "metal",  # Metal music
]

# Genre classification based on subreddit
SUBREDDIT_GENRES = {
    "hiphopheads": "hiphop",
    "Music": "mixed",
    "indieheads": "rock",
    "popheads": "pop",
    "electronicmusic": "electronic",
    "gospelmusic": "gospel",
    "rock": "rock",
    "rnb": "hiphop",  # R&B falls under hip-hop category
    "jazz": "mixed",
    "metal": "rock",
}

# Keywords for artist extraction
ARTIST_PATTERNS = [
    r"\[FRESH\s+(?:ALBUM|EP|VIDEO|SINGLE|TRACK)\]?\s*([^-]+)\s*-",
    r"\[FRESH\]\s*([^-]+)\s*-",
    r"\[DISCUSSION\]\s*([^-]+)\s*-",
    r"([A-Z][a-zA-Z\s&]+)\s+drops?\s+(?:new|latest)",
    r"([A-Z][a-zA-Z\s&]+)\s+announces?\s+(?:new|upcoming)",
    r"([A-Z][a-zA-Z\s&]+)\s+releases?\s+(?:new|latest)",
]

# Minimum upvotes required to consider a post for artist extraction
MIN_VOTES_THRESHOLD = 10

# Blocklist: common meta-post titles that are NOT artist names
TITLE_BLOCKLIST = {
    "daily discussion",
    "daily music discussion",
    "general discussion",
    "top ten pop ten",
    "teatime & trending topics",
    "teatime &amp; trending topics",
    "fresh finds friday",
    "what have you been listening to",
    "album of the year",
    "song of the year",
    "best of",
    "weekly discussion",
    "monthly discussion",
    "sunday general discussion",
    "saturday general discussion",
    "friday general discussion",
    "hype thursday",
    "recommend if you like",
    "roast my playlist",
    "ama",
    "announcement",
}


@dataclass
class RedditPost:
    """Data class for Reddit post"""

    title: str
    url: str
    subreddit: str
    votes: int
    comments: int
    content: str = ""
    published: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


class RedditScraper:
    """Scraper for Reddit music posts using hf CLI"""

    def __init__(self):
        self.session = self._create_session()
        self.existing_titles: Set[str] = set()
        self.events: List[Dict[str, Any]] = []

    def _create_session(self):
        """Create HTTP session with retry logic"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _log_event(self, event: str, level: str = "info", **data: Any) -> None:
        self.events.append(
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "event": event,
                "level": level,
                "data": data,
            }
        )

    def _normalize_https_url(self, raw_url: str) -> str:
        value = (raw_url or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme == "http":
            parsed = parsed._replace(scheme="https")
            return urlunparse(parsed)
        return value

    def _build_doc_id(self, title: str, source_url: str, published: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "").lower()).strip("-")
        slug = (slug[:24] or "article").strip("-")
        digest = hashlib.sha1(
            f"{source_url}|{published}|{title}".encode("utf-8", errors="ignore")
        ).hexdigest()[:20]
        return f"{slug}-{digest}"

    def fetch_reddit_posts(self, subreddit: str, limit: int = 20) -> List[RedditPost]:
        """Fetch posts from Reddit using hf CLI"""
        try:
            print(f"  📥 Fetching r/{subreddit}...")

            # Run hf CLI command
            result = subprocess.run(
                ["hf", "reddit", "-t", subreddit],
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )

            if result.returncode != 0:
                print(f"  ✗ Error running hf command: {result.stderr}")
                return []

            # Parse the output (hf doesn't have --json flag based on test)
            posts = self._parse_hf_output(result.stdout, subreddit)
            return posts[:limit]

        except subprocess.TimeoutExpired:
            print(f"  ⏰ Timeout fetching r/{subreddit}")
            return []
        except Exception as e:
            print(f"  ✗ Error fetching r/{subreddit}: {e}")
            return []

    def _parse_hf_output(self, output: str, subreddit: str) -> List[RedditPost]:
        """Parse hf CLI output format"""
        posts = []
        lines = output.strip().split("\n")

        current_post = {}
        in_content = False
        content_lines = []

        for line in lines:
            line = line.strip()

            # Start of new post
            if line.startswith("Title :"):
                # Save previous post if exists
                if current_post:
                    post = RedditPost(
                        title=current_post.get("title", ""),
                        url=current_post.get("url", ""),
                        subreddit=subreddit,
                        votes=_safe_int(current_post.get("votes", 0)),
                        comments=_safe_int(current_post.get("comments", 0)),
                        content="\n".join(content_lines).strip(),
                        published=datetime.now().isoformat(),
                    )
                    posts.append(post)

                # Start new post
                current_post = {"title": line.replace("Title :", "").strip()}
                content_lines = []
                in_content = False

            # Parse other fields
            elif line.startswith("Link :"):
                current_post["url"] = line.replace("Link :", "").strip()
            elif line.startswith("Comment:"):
                # Extract comments and votes
                parts = line.replace("Comment:", "").strip().split("|")
                if len(parts) >= 2:
                    current_post["comments"] = parts[0].strip()
                    votes_part = parts[1].replace("Votes:", "").strip()
                    current_post["votes"] = votes_part
            elif line.startswith("Content :"):
                in_content = True
                content_text = line.replace("Content :", "").strip()
                if content_text:
                    content_lines.append(content_text)
            elif in_content and line and not line.startswith("---"):
                content_lines.append(line)

        # Add last post
        if current_post:
            post = RedditPost(
                title=current_post.get("title", ""),
                url=current_post.get("url", ""),
                subreddit=subreddit,
                votes=_safe_int(current_post.get("votes", 0)),
                comments=_safe_int(current_post.get("comments", 0)),
                content="\n".join(content_lines).strip(),
                published=datetime.now().isoformat(),
            )
            posts.append(post)

        return posts

    def extract_artists_from_posts(
        self, posts: List[RedditPost]
    ) -> List[Dict[str, Any]]:
        """Extract artist information from Reddit posts"""
        artists = []
        seen_artists = set()

        for post in posts:
            # Skip low-engagement posts (likely noise)
            if post.votes < MIN_VOTES_THRESHOLD:
                continue

            # Try to extract artist from title
            artist_name = self._extract_artist_from_title(post.title)

            if artist_name and artist_name not in seen_artists:
                seen_artists.add(artist_name)

                # Determine genre from subreddit
                genre = SUBREDDIT_GENRES.get(post.subreddit, "mixed")

                # Create artist entry
                artist = {
                    "name": artist_name,
                    "subreddit": post.subreddit,
                    "source_post": post.title,
                    "source_url": post.url,
                    "genre": genre,
                    "votes": post.votes,
                    "comments": post.comments,
                    "discovered_at": datetime.now().isoformat(),
                    "scraper_version": SCRAPER_VERSION,
                }
                artists.append(artist)

        return artists

    def _extract_artist_from_title(self, title: str) -> Optional[str]:
        """Extract artist name from Reddit post title"""
        # Remove ALL bracket tags (e.g. [FRESH], [LEAK], [ALBUM DISCUSSION], etc.)
        clean_title = re.sub(r"\[[^\]]*\]", "", title).strip()

        # Try pattern matching first
        for pattern in ARTIST_PATTERNS:
            match = re.search(pattern, clean_title, re.IGNORECASE)
            if match:
                artist = match.group(1).strip()
                artist = self._clean_artist_name(artist)
                if self._is_valid_artist_name(artist):
                    return artist

        # Fallback: split on dash (only if clean title has a dash)
        if " - " in clean_title:
            artist = clean_title.split(" - ")[0].strip()
            artist = self._clean_artist_name(artist)
            if self._is_valid_artist_name(artist):
                return artist

        return None

    def _clean_artist_name(self, artist: str) -> str:
        """Clean up extracted artist name"""
        artist = re.sub(r"\s+[-–]\s+.*$", "", artist)
        artist = re.sub(r"\s+ft\.?.*$", "", artist, flags=re.IGNORECASE)
        artist = re.sub(r"\s+feat\.?.*$", "", artist, flags=re.IGNORECASE)
        artist = re.sub(r"\s+w/.*$", "", artist, flags=re.IGNORECASE)
        artist = re.sub(r"\s*\[.*\]$", "", artist)
        # Remove leading/trailing quotes and whitespace
        artist = artist.strip().strip('"\'')
        return artist.strip()

    def _is_valid_artist_name(self, name: str) -> bool:
        """Validate that an extracted string is likely an artist name"""
        if not name or len(name) < 2 or len(name) > 80:
            return False
        # Reject blocklisted meta-post titles
        if name.lower() in TITLE_BLOCKLIST:
            return False
        # Reject strings that look like sentences (5+ words starting with lowercase)
        words = name.split()
        if len(words) >= 5 and words[0][0].islower():
            return False
        return True

    def create_articles_from_artists(
        self, artists: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create miny-ven articles from discovered artists"""
        articles = []

        for artist in artists[:10]:  # Limit to top 10
            # Skip if already exists
            article_title = f"Reddit Trending: {artist['name']}"
            if article_title in self.existing_titles:
                continue

            # Create summary
            subreddit = artist["subreddit"]
            votes = artist["votes"]
            comments = artist["comments"]

            summary = (
                f"{artist['name']} is trending on r/{subreddit} with {votes} votes and {comments} comments. "
                f"The community is discussing their latest work. Check out the Reddit thread for more details."
            )

            # Truncate to ~60 words
            words = summary.split()
            if len(words) > 60:
                summary = " ".join(words[:60]) + "..."

            article = {
                "title": article_title,
                "summary": summary,
                "link": artist["source_url"],
                "published": artist["discovered_at"],
                "genre": artist["genre"],
                "source": f"r/{subreddit}",
                "image": self._get_artist_image(artist["name"], artist["genre"]),
                "scraper_version": SCRAPER_VERSION,
                "type": "reddit_discovery",
            }

            articles.append(article)
            self.existing_titles.add(article_title)

        return articles

    def _get_artist_image(self, artist_name: str, genre: str) -> str:
        """Get placeholder image based on genre"""
        # In production, you might want to fetch actual artist images
        # For now, return genre-based placeholder
        genre_colors = {
            "gospel": "#4A90E2",
            "hiphop": "#FF6B6B",
            "pop": "#FFD166",
            "rock": "#06D6A0",
            "electronic": "#118AB2",
            "mixed": "#EF476F",
        }

        color = genre_colors.get(genre, "#6C757D")
        # Create a simple SVG placeholder (escape artist name to prevent XSS)
        safe_name = html_escape(artist_name[:20], quote=True)
        return f"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='400' height='225'><rect width='400' height='225' fill='{color}'/><text x='200' y='112' font-family='Arial' font-size='24' fill='white' text-anchor='middle'>{safe_name}</text></svg>"

    def save_to_firebase(self, articles: List[Dict[str, Any]]) -> int:
        """Save articles to Firebase Firestore - matches RSS scraper schema exactly"""
        if not articles:
            return 0
        if not API_KEY:
            print("  ✗ Failed to save: FIREBASE_API_KEY is missing")
            self._log_event("save_failed", level="error", reason="missing_api_key")
            return 0

        saved_count = 0

        for article in articles:
            try:
                # Extract artist name from the "Reddit Trending: <name>" title
                artist_name = article["title"].removeprefix("Reddit Trending: ").strip()
                artist_names = [artist_name] if artist_name else []

                # Create document ID from title (match RSS scraper pattern)
                source_url = self._normalize_https_url(article["link"])
                if not source_url.startswith("https://"):
                    print(f"  ✗ Failed to save: source_url must be https ({article['link']})")
                    self._log_event(
                        "save_failed",
                        level="error",
                        reason="invalid_source_url",
                        title=article["title"],
                        source_url=article["link"],
                    )
                    continue
                doc_id = self._build_doc_id(article["title"], source_url, article["published"])

                # Prepare document data - MUST match RSS article schema exactly
                # See firestore.rules for required fields
                doc_data = {
                    "fields": {
                        "title": {"stringValue": article["title"]},
                        "summary": {"stringValue": article["summary"]},
                        "full_content": {
                            "stringValue": article["summary"]
                        },  # Use summary as full content
                        "source": {"stringValue": article["source"]},
                        "source_url": {
                            "stringValue": source_url
                        },  # Map link → source_url
                        "primary_genre": {
                            "stringValue": article["genre"]
                        },  # Map genre → primary_genre
                        "secondary_genres": {
                            "arrayValue": {"values": []}
                        },  # Empty list
                        "artist_names": {
                            "arrayValue": {
                                "values": [
                                    {"stringValue": name} for name in artist_names
                                ]
                            }
                        },
                        "image_url": {
                            "stringValue": article.get("image", "")
                        },  # Map image → image_url
                        "published_at": {
                            "stringValue": article["published"]
                        },  # Map published → published_at
                        "read_time": {
                            "integerValue": "1"
                        },  # Default 1 minute read time
                        "share_count": {"integerValue": "0"},
                        "email_count": {"integerValue": "0"},
                        "bookmark_count": {"integerValue": "0"},
                        "view_count": {"integerValue": "0"},
                        "fetched_at": {"stringValue": datetime.now().isoformat()},
                    }
                }

                # Save to Firebase - match RSS scraper format exactly
                url = f"{FIRESTORE_URL}/articles/{doc_id}?key={API_KEY}"

                response = self.session.patch(
                    url, json=doc_data, timeout=DEFAULT_TIMEOUT_SECONDS
                )

                if response.status_code in [200, 201]:
                    saved_count += 1
                    print(f"  ✓ Saved: {article['title'][:50]}...")
                    self._log_event(
                        "save_ok",
                        doc_id=doc_id,
                        status_code=response.status_code,
                        title=article["title"],
                    )
                else:
                    error_excerpt = (response.text or "")[:400]
                    print(
                        f"  ✗ Failed to save: {response.status_code} - {error_excerpt}"
                    )
                    self._log_event(
                        "save_failed",
                        level="error",
                        doc_id=doc_id,
                        status_code=response.status_code,
                        response_excerpt=error_excerpt,
                        title=article["title"],
                    )

            except Exception as e:
                print(f"  ✗ Error saving article: {e}")
                self._log_event("save_exception", level="error", error=str(e))

        return saved_count

    def load_existing_titles(self):
        """Load existing article titles from Firebase to avoid duplicates"""
        try:
            url = f"{FIRESTORE_URL}/articles?key={API_KEY}&pageSize=100&orderBy=fields.published desc"

            response = self.session.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)
            if response.status_code == 200:
                data = response.json()
                titles = set()

                if "documents" in data:
                    for doc in data["documents"]:
                        if "fields" in doc and "title" in doc["fields"]:
                            title = doc["fields"]["title"]["stringValue"]
                            titles.add(title)

                self.existing_titles = titles
                print(f"  📋 Loaded {len(titles)} existing titles")
            else:
                print(f"  ⚠ Could not load existing titles: {response.status_code}")

        except Exception as e:
            print(f"  ⚠ Error loading existing titles: {e}")
            self.existing_titles = set()


def main():
    """Main function to run Reddit scraper"""
    print("🎵 miny-ven Reddit Scraper")
    print("=" * 50)

    # Initialize scraper
    scraper = RedditScraper()

    # Load existing titles to avoid duplicates
    scraper.load_existing_titles()

    all_articles = []

    # Fetch from top music subreddits
    for subreddit in MUSIC_SUBREDDITS[:3]:  # Start with top 3
        print(f"\n🔍 Scanning r/{subreddit}...")

        # Fetch posts
        posts = scraper.fetch_reddit_posts(subreddit, limit=15)
        print(f"  📊 Found {len(posts)} posts")

        if not posts:
            continue

        # Extract artists
        artists = scraper.extract_artists_from_posts(posts)
        print(f"  🎤 Extracted {len(artists)} artists")

        # Create articles
        articles = scraper.create_articles_from_artists(artists)
        print(f"  📝 Created {len(articles)} articles")

        all_articles.extend(articles)

    # Save to Firebase
    if all_articles:
        print(f"\n💾 Saving {len(all_articles)} articles to Firebase...")
        saved = scraper.save_to_firebase(all_articles)
        print(f"✅ Saved {saved} new articles")
    else:
        print("\n📭 No new articles to save")

    print(
        f"\n🎉 Reddit scraper completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


if __name__ == "__main__":
    main()
