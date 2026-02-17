#!/usr/bin/env python3
"""
miny-ven RSS Scraper with OpenRouter Summarization
Fetches music news from RSS feeds and summarizes them to 60 words
Uses REST API instead of firebase_admin
"""

import xml.etree.ElementTree as ET
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
import os
from pathlib import Path
from urllib.parse import urljoin, urlencode, urlparse, urlunparse

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "miny-ven")
API_KEY = os.getenv("FIREBASE_API_KEY", "")
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"
PUBLIC_APP_URL = (
    os.getenv("PUBLIC_APP_URL")
    or os.getenv("VITE_PUBLIC_APP_URL")
    or "https://minyven-news.vercel.app"
).rstrip("/")

SCRAPER_VERSION = "2026-02-12"
DEFAULT_TIMEOUT_SECONDS = 20

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
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD", "POST", "PUT", "PATCH"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Cache titles once per run to avoid re-fetching the full collection for every item.
        self._existing_titles: Optional[List[str]] = None
        self.run_id: Optional[str] = None
        self.artifact_dir = Path(
            os.getenv("SCRAPER_ARTIFACT_DIR", Path(__file__).parent / "artifacts")
        )
        self.events: List[Dict[str, Any]] = []

    def _request(self, method: str, url: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("User-Agent", "Mozilla/5.0 (compatible; miny-ven-bot/1.0)")
        return self.session.request(method, url, headers=headers, timeout=timeout, **kwargs)

    def _log_event(self, event: str, level: str = "info", **data: Any) -> None:
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "run_id": self.run_id or "",
            "event": event,
            "level": level,
            "data": data,
        }
        self.events.append(entry)

    def _flush_artifacts(self, summary: Dict[str, Any], source_stats: Dict[str, Dict[str, int]]) -> None:
        try:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            rid = summary.get("run_id") or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            summary_path = self.artifact_dir / f"summary_{rid}.json"
            events_path = self.artifact_dir / f"events_{rid}.jsonl"

            summary_payload = {
                "summary": summary,
                "source_stats": source_stats,
                "event_count": len(self.events),
            }
            summary_path.write_text(
                json.dumps(summary_payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            with events_path.open("w", encoding="utf-8") as f:
                for event in self.events:
                    f.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")

            print(f"  ✓ Wrote artifacts: {summary_path} and {events_path}")
        except Exception as e:
            print(f"  ⚠ Failed writing artifacts: {e}")

    def _normalize_source_url(self, raw_url: str) -> str:
        value = (raw_url or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme == "http":
            parsed = parsed._replace(scheme="https")
            return urlunparse(parsed)
        return value

    def _build_doc_id(self, article: Article) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (article.title or "").lower()).strip("-")
        slug = (slug[:24] or "article").strip("-")
        hash_input = (
            f"{article.source_url}|{article.published_at.isoformat()}|{article.title}"
        ).encode("utf-8", errors="ignore")
        digest = hashlib.sha1(hash_input).hexdigest()[:20]
        return f"{slug}-{digest}"

    def _extract_key_words(self, text: str) -> set:
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

    def _jaccard_similarity(self, a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        union = len(a | b)
        if union == 0:
            return 0.0
        return len(a & b) / union

    def _load_existing_titles(self) -> List[str]:
        if self._existing_titles is not None:
            return self._existing_titles

        titles: List[str] = []
        if not API_KEY:
            self._existing_titles = titles
            return titles

        try:
            url = f"{FIRESTORE_URL}/articles?key={API_KEY}"
            response = self._request("GET", url, timeout=15)
            if response.status_code != 200:
                self._log_event(
                    "preload_titles_failed",
                    level="warning",
                    status_code=response.status_code,
                    response_excerpt=(response.text or "")[:300],
                )
                self._existing_titles = titles
                return titles

            data = response.json()
            for doc in data.get("documents", []) or []:
                fields = doc.get("fields", {}) or {}
                title = fields.get("title", {}).get("stringValue", "")
                if isinstance(title, str) and title:
                    titles.append(title.lower().strip())
        except Exception as e:
            print(f"  ⚠ Error preloading titles: {e}")
            self._log_event("preload_titles_exception", level="warning", error=str(e))

        self._existing_titles = titles
        return titles

    def fetch_rss_feed(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed"""
        try:
            response = self._request("GET", url, timeout=DEFAULT_TIMEOUT_SECONDS)
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
            self._log_event("feed_fetch_failed", level="error", feed_url=url, error=str(e))
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

    def _extract_image_from_article_html(self, html: str, article_url: str) -> Optional[str]:
        """Extract preferred social image tags from article HTML."""
        if not html:
            return None

        meta_tags = re.findall(r"<meta\s+[^>]*>", html, flags=re.IGNORECASE)
        wanted_props = {
            "og:image",
            "og:image:secure_url",
            "twitter:image",
            "twitter:image:src",
        }

        for tag in meta_tags:
            attrs = dict(
                (k.lower(), v.strip())
                for k, v in re.findall(
                    r'([a-zA-Z_:.-]+)\s*=\s*["\']([^"\']*)["\']', tag
                )
            )
            prop = attrs.get("property", "").lower()
            name = attrs.get("name", "").lower()
            content = attrs.get("content", "").strip()
            if (prop in wanted_props or name in wanted_props) and content:
                return urljoin(article_url, content)

        link_tags = re.findall(r"<link\s+[^>]*>", html, flags=re.IGNORECASE)
        for tag in link_tags:
            attrs = dict(
                (k.lower(), v.strip())
                for k, v in re.findall(
                    r'([a-zA-Z_:.-]+)\s*=\s*["\']([^"\']*)["\']', tag
                )
            )
            rel = attrs.get("rel", "").lower()
            href = attrs.get("href", "").strip()
            if rel == "image_src" and href:
                return urljoin(article_url, href)

        return None

    def _fetch_article_meta_image(self, article_url: str) -> Optional[str]:
        """Fetch article page and extract OG/Twitter image."""
        if not article_url:
            return None
        try:
            response = self._request("GET", article_url, timeout=12, allow_redirects=True)
            if response.status_code >= 400:
                return None
            content_type = (response.headers.get("content-type") or "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return None
            return self._extract_image_from_article_html(response.text, article_url)
        except Exception:
            return None

    def _is_valid_remote_image(self, url: str) -> bool:
        """Check URL is https and likely returns an image."""
        if not url or not url.startswith("https://"):
            return False

        try:
            head = self._request("HEAD", url, timeout=8, allow_redirects=True)
            if head.status_code < 400:
                content_type = (head.headers.get("content-type") or "").lower()
                if content_type.startswith("image/"):
                    return True
                # Some hosts skip content-type on HEAD; accept if status is good.
                if not content_type:
                    return True
            if head.status_code == 405:
                # Host doesn't allow HEAD; fall through to GET probe.
                pass
            elif head.status_code >= 400:
                return False
        except Exception:
            # Retry with GET probe below.
            pass

        try:
            get_probe = self._request("GET", url, timeout=8, stream=True, allow_redirects=True)
            if get_probe.status_code >= 400:
                return False
            content_type = (get_probe.headers.get("content-type") or "").lower()
            return content_type.startswith("image/")
        except Exception:
            return False

    def build_banner_url(
        self, title: str, source: str, genre: str, published_at: Optional[datetime]
    ) -> str:
        """Build deterministic intelligent-banner fallback URL."""
        safe_title = re.sub(r"\s+", " ", (title or "").strip())[:180]
        date_value = ""
        if isinstance(published_at, datetime):
            date_value = published_at.strftime("%Y-%m-%d")
        params = urlencode(
            {
                "title": safe_title,
                "source": source or "",
                "genre": genre or "mixed",
                "date": date_value,
            }
        )
        return f"{PUBLIC_APP_URL}/api/banner?{params}"

    def resolve_image_url(
        self,
        item: Dict[str, str],
        *,
        title: str,
        source: str,
        genre: str,
        published_at: Optional[datetime],
    ) -> Tuple[str, str]:
        """Resolve best image URL with fallback strategy."""
        candidates: List[Tuple[str, Optional[str]]] = [
            ("rss", item.get("image")),
            ("open_graph", self._fetch_article_meta_image(item.get("link", ""))),
        ]

        for strategy, candidate in candidates:
            if not candidate:
                continue
            normalized = urljoin(item.get("link", ""), candidate).strip()
            if self._is_valid_remote_image(normalized):
                return normalized, strategy

        return self.build_banner_url(title, source, genre, published_at), "generated_banner"

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
            response = self._request("POST", DEEPSEEK_URL, headers=headers, json=data, timeout=DEFAULT_TIMEOUT_SECONDS)
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

    def research_with_perplexity(self, artist: str, topic: str) -> str:
        """Research article topic using Perplexity API for deeper insights"""
        if not PERPLEXITY_API_KEY:
            return ""

        prompt = f"""Research the latest news about {artist} and {topic}. 
        Provide 2-3 key facts or developments that would be interesting to music fans.
        Keep it concise and factual."""

        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        }

        data = {
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a music industry research assistant. Provide factual, current information about artists and music news.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 200,
            "temperature": 0.3,
        }

        try:
            response = self._request("POST", PERPLEXITY_URL, headers=headers, json=data, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            result = response.json()
            research = result["choices"][0]["message"]["content"].strip()
            return research
        except Exception as e:
            print(f"  ⚠ Perplexity research error: {e}")
            return ""

    def generate_cta_headline(
        self, original_title: str, content: str, artist: str
    ) -> str:
        """Generate high-converting CTA headline that's not copy-paste"""
        if not PERPLEXITY_API_KEY:
            # Fallback: transform original title
            return self._transform_title_fallback(original_title)

        prompt = f"""Create an engaging, click-worthy headline for this music news story.
        
Original Title: {original_title}
Artist: {artist}
Content Summary: {content[:500]}

Requirements:
- Write a NEW headline (NOT a copy-paste of the original)
- Use power words that drive clicks (Breaking, Exclusive, Revealed, Unveiled, Must-See, etc.)
- Create curiosity gap or urgency
- Keep under 80 characters
- Make it punchy and shareable
- Avoid clickbait that doesn't deliver

Examples of good CTA headlines:
- "Breaking: [Artist] Just Dropped Something Huge"
- "The Real Reason [Artist] Is Making Waves"
- "What [Artist] Just Revealed Changes Everything"
- "Exclusive: Inside [Artist]'s Latest Move"

New CTA Headline:"""

        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        }

        data = {
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a viral headline writer for a music news app. Create headlines that get clicks while staying authentic to the story.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 100,
            "temperature": 0.8,
        }

        try:
            response = self._request("POST", PERPLEXITY_URL, headers=headers, json=data, timeout=DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            result = response.json()
            headline = result["choices"][0]["message"]["content"].strip()

            # Clean up quotes if present
            headline = headline.strip("\"'")

            # Ensure it's not too long
            if len(headline) > 100:
                headline = headline[:97] + "..."

            return headline
        except Exception as e:
            print(f"  ⚠ CTA headline error: {e}, using fallback")
            return self._transform_title_fallback(original_title)

    def _transform_title_fallback(self, original_title: str) -> str:
        """Fallback method to transform title without API"""
        # Remove publication names and common prefixes
        title = re.sub(
            r"^(Premiere:|Exclusive:|Watch:|Listen:|Review:|Interview:)\s*",
            "",
            original_title,
            flags=re.IGNORECASE,
        )

        # Power words to add
        power_words = [
            "Breaking",
            "Exclusive",
            "Revealed",
            "Unveiled",
            "Must-See",
            "Inside",
        ]

        # Check if title already has power words
        has_power_word = any(word.lower() in title.lower() for word in power_words)

        if not has_power_word and len(title) < 70:
            # Add a power word
            import random

            power_word = random.choice(power_words)
            title = f"{power_word}: {title}"

        return title.strip()

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
            existing_titles = self._load_existing_titles()
            normalized = title.lower().strip()
            if normalized in existing_titles:
                return True

            new_key_words = self._extract_key_words(title)
            for existing_title in existing_titles:
                if existing_title == normalized:
                    return True

                similarity = self._jaccard_similarity(new_key_words, self._extract_key_words(existing_title))
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
            if not API_KEY:
                print("  ✗ Failed to save: FIREBASE_API_KEY is missing")
                self._log_event("save_failed", level="error", reason="missing_api_key", title=article.title)
                return False

            article_dict = asdict(article)
            article_dict["published_at"] = article.published_at.isoformat()
            article_dict["fetched_at"] = article.fetched_at.isoformat()

            if not article.source_url.startswith("https://"):
                print(f"  ✗ Failed to save: source_url must be https ({article.source_url})")
                self._log_event(
                    "save_failed",
                    level="error",
                    reason="invalid_source_url",
                    source_url=article.source_url,
                    title=article.title,
                )
                return False

            doc_id = self._build_doc_id(article)

            url = f"{FIRESTORE_URL}/articles/{doc_id}?key={API_KEY}"
            payload = {"fields": self.convert_to_firestore_fields(article_dict)}

            response = self._request("PATCH", url, json=payload, timeout=DEFAULT_TIMEOUT_SECONDS)

            if response.status_code in [200, 201]:
                print(f"  ✓ Saved: {article.title[:60]}...")
                self._log_event(
                    "save_ok",
                    doc_id=doc_id,
                    status_code=response.status_code,
                    source=article.source,
                    title=article.title,
                )
                if self._existing_titles is not None:
                    self._existing_titles.append(article.title.lower().strip())
                return True
            else:
                error_excerpt = (response.text or "")[:400]
                print(f"  ✗ Failed to save: {response.status_code} - {error_excerpt}")
                self._log_event(
                    "save_failed",
                    level="error",
                    doc_id=doc_id,
                    status_code=response.status_code,
                    response_excerpt=error_excerpt,
                    title=article.title,
                )
                return False
        except Exception as e:
            print(f"  ✗ Error saving to Firebase: {e}")
            self._log_event("save_exception", level="error", title=article.title, error=str(e))
            return False

    def process_feed(self, source_name: str, source_config: Dict) -> Dict[str, int]:
        """Process a single RSS feed with CTA headlines and Perplexity research"""
        print(f"\n📡 Fetching {source_name}...")

        items = self.fetch_rss_feed(source_config["url"])
        print(f"  Found {len(items)} items")

        stats = {
            "items_found": len(items),
            "items_considered": 0,
            "duplicates_skipped": 0,
            "saved": 0,
            "failed": 0,
            "rss_image_used": 0,
            "og_image_used": 0,
            "banner_image_used": 0,
        }

        for item in items[:5]:  # Process top 5 items per feed
            try:
                stats["items_considered"] += 1
                original_title = item["title"]
                content = item["content"] or item["description"]

                # Check for duplicate using original title
                if self.check_duplicate(original_title):
                    print(f"  ⚠ Duplicate: {original_title[:50]}...")
                    stats["duplicates_skipped"] += 1
                    continue

                # Extract artists first for research
                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                # Generate high-CTA headline (not copy-paste)
                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                # Research with Perplexity for additional insights
                research = ""
                if main_artist and PERPLEXITY_API_KEY:
                    print(f"  🔍 Researching with Perplexity...")
                    # Extract topic from title
                    topic = original_title.replace(main_artist, "").strip()
                    research = self.research_with_perplexity(main_artist, topic)

                # Summarize with DeepSeek (including research if available)
                content_with_research = content
                if research:
                    content_with_research += f"\n\nAdditional context: {research}"

                summary = self.summarize_with_deepseek(cta_title, content_with_research)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, source_config["genre"]
                )

                try:
                    pub_date = datetime.strptime(
                        item["pub_date"], "%a, %d %b %Y %H:%M:%S %z"
                    )
                except:
                    pub_date = datetime.now()

                resolved_source_name = source_name.replace("_", " ").title()
                resolved_image_url, image_strategy = self.resolve_image_url(
                    item,
                    title=cta_title,
                    source=resolved_source_name,
                    genre=primary_genre,
                    published_at=pub_date,
                )
                if image_strategy == "rss":
                    stats["rss_image_used"] += 1
                elif image_strategy == "open_graph":
                    stats["og_image_used"] += 1
                else:
                    stats["banner_image_used"] += 1

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,  # Use CTA headline, not original
                    summary=summary,
                    full_content=content_with_research[:2000],
                    source=resolved_source_name,
                    source_url=self._normalize_source_url(item.get("link", "")),
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=resolved_image_url,
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                )

                if self.save_to_firebase(article):
                    print(f"  ✓ Saved: {cta_title[:60]}...")
                    stats["saved"] += 1
                else:
                    stats["failed"] += 1

            except Exception as e:
                print(f"  ✗ Error processing item: {e}")
                stats["failed"] += 1
                continue

        return stats

    def save_run_summary(self, summary: Dict[str, Any]) -> bool:
        if not API_KEY:
            return False
        try:
            run_id = summary.get("run_id") or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            url = f"{FIRESTORE_URL}/scrape_runs/{run_id}?key={API_KEY}"
            payload = {"fields": self.convert_to_firestore_fields(summary)}
            response = self._request("PATCH", url, json=payload, timeout=DEFAULT_TIMEOUT_SECONDS)
            return response.status_code in (200, 201)
        except Exception as e:
            print(f"  ⚠ Failed to persist run summary: {e}")
            return False

    def run(self):
        """Run the scraper for all sources"""
        started_at = datetime.utcnow()
        self.run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
        self.events = []
        print("🎵 miny-ven RSS Scraper")
        print("=" * 50)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Project: {PROJECT_ID}")
        print()

        if not API_KEY:
            print("⚠️  Warning: FIREBASE_API_KEY not set. Articles won't be saved.")
            self._log_event("missing_env", level="warning", name="FIREBASE_API_KEY")
            print()

        if not OPENROUTER_API_KEY:
            print("⚠️  Warning: OPENROUTER_API_KEY not set. Using basic summaries.")
            self._log_event("missing_env", level="warning", name="OPENROUTER_API_KEY")
            print()

        self._load_existing_titles()
        total_saved = 0
        sources_ok = 0
        sources_failed = 0
        source_stats: Dict[str, Dict[str, int]] = {}

        for source_name, config in RSS_SOURCES.items():
            try:
                stats = self.process_feed(source_name, config)
                source_stats[source_name] = stats
                total_saved += stats.get("saved", 0)
                sources_ok += 1
            except Exception as e:
                print(f"  ✗ Error with {source_name}: {e}")
                sources_failed += 1
                continue

        finished_at = datetime.utcnow()

        run_id = self.run_id or started_at.strftime("%Y%m%dT%H%M%SZ")
        summary = {
            "run_id": run_id,
            "version": SCRAPER_VERSION,
            "started_at": started_at.isoformat() + "Z",
            "finished_at": finished_at.isoformat() + "Z",
            "total_sources": len(RSS_SOURCES),
            "sources_ok": sources_ok,
            "sources_failed": sources_failed,
            "total_processed": total_saved,
            "source_stats_json": json.dumps(source_stats, separators=(",", ":"), sort_keys=True),
        }
        print("\n📊 Run summary (JSON):")
        print(json.dumps(summary, indent=2, sort_keys=True))
        persisted = self.save_run_summary(summary)
        if persisted:
            print("  ✓ Persisted run summary to Firestore: scrape_runs/" + run_id)
        else:
            print("  ⚠ Run summary not persisted (rules/API key may block).")
        self._log_event(
            "run_summary",
            persisted=persisted,
            total_saved=total_saved,
            total_sources=len(RSS_SOURCES),
            sources_ok=sources_ok,
            sources_failed=sources_failed,
        )
        self._flush_artifacts(summary, source_stats)

        print("\n" + "=" * 50)
        print(f"✅ Complete! Added {total_saved} new articles")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    scraper = RSSScraper()
    scraper.run()
