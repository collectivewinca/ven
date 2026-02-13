#!/usr/bin/env python3
"""
miny-ven RSS Scraper with AI Summarization
Fetches music news from RSS feeds and summarizes them to 60 words.
Uses Perplexity SDK for headlines/research, DeepSeek for summaries,
and Firestore REST API for storage.
"""

import xml.etree.ElementTree as ET
import json
import requests
import re
from datetime import datetime
from typing import Optional, Dict, List, Set, Tuple
from dataclasses import dataclass, asdict
import os
import sys
import hashlib
from urllib.parse import urlsplit, urlunsplit
from email.utils import parsedate_to_datetime

# Load environment variables
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Perplexity SDK (optional — falls back to basic transforms if unavailable)
_perplexity_client = None
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
if PERPLEXITY_API_KEY:
    try:
        from perplexity import Perplexity

        _perplexity_client = Perplexity(api_key=PERPLEXITY_API_KEY)
    except ImportError:
        print("⚠ perplexityai package not installed, using fallbacks")

# Exa SDK (optional — used for article research and news discovery)
_exa_client = None
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
if EXA_API_KEY:
    try:
        from exa_py import Exa

        _exa_client = Exa(api_key=EXA_API_KEY)
    except ImportError:
        print("⚠ exa_py package not installed, Exa features disabled")

# Configuration
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
        self.existing_source_urls: Set[str] = set()
        self.existing_titles: Set[str] = set()
        self.session = requests.Session()

    def fetch_rss_feed(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed"""
        try:
            response = self.session.get(
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

    def parse_pub_date(self, value: str) -> datetime:
        """Parse RSS publication dates safely, fallback to now."""
        try:
            if not value:
                raise ValueError("missing pub_date")
            dt = parsedate_to_datetime(value)
            if dt is None:
                raise ValueError("unparseable pub_date")
            return dt
        except Exception:
            return datetime.now()

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

            # Guard against model meta-commentary
            if self._is_refusal(summary):
                print("  ⚠ DeepSeek refused summary, using fallback")
                words = content.split()[:60]
                return " ".join(words) + "." if words else title

            words = summary.split()
            if len(words) > 60:
                summary = " ".join(words[:60]) + "."

            return summary
        except Exception as e:
            print(f"  ⚠ DeepSeek error: {e}, using fallback")
            words = content.split()[:60]
            return " ".join(words) + "." if words else title

    # Phrases that indicate the model broke character instead of
    # producing a real headline or summary.  Checked case-insensitively
    # against the full text (not just the prefix).
    _REFUSAL_PATTERNS = re.compile(
        r"(?i)"
        r"(?:"
        r"i appreciate|i need to|i can'?t|as an ai|i'?m sorry"
        r"|i notice|i see that|i don'?t have|unfortunately"
        r"|based on the search|the search results"
        r"|provided don'?t contain|no (?:relevant|specific) (?:information|results|data)"
        r"|i (?:wasn'?t|was not) able"
        r"|(?:here(?:'s| is) (?:a|the|my))|let me "
        r")"
    )

    @classmethod
    def _is_refusal(cls, text: str) -> bool:
        """Return True if *text* looks like model meta-commentary."""
        return bool(cls._REFUSAL_PATTERNS.search(text))

    @staticmethod
    def _clean_perplexity_text(text: str) -> str:
        """Strip markdown bold, citation brackets, and stray whitespace."""
        text = text.strip()
        text = re.sub(r"\*+", "", text)  # **bold** → bold
        text = re.sub(r"\[[\d,\s]+\]", "", text)  # [1][2] → ""
        text = text.strip("\"'")
        return text.strip()

    def research_with_exa(self, artist: str, topic: str) -> str:
        """Research article topic using Exa search for deeper insights."""
        if not _exa_client:
            return self._research_with_perplexity_fallback(artist, topic)

        query = f"{artist} {topic} music news 2026".strip()
        try:
            result = _exa_client.search(
                query,
                type="auto",
                num_results=3,
                contents={"text": {"max_characters": 500}},
            )
            snippets = []
            for r in result.results:
                if r.text:
                    # Strip HTML residue and take first 200 chars
                    clean = re.sub(r"<[^>]+>", "", r.text).strip()
                    clean = re.sub(r"\s+", " ", clean)[:200]
                    if clean:
                        snippets.append(clean)
            if snippets:
                return " | ".join(snippets[:2])
            return ""
        except Exception as e:
            print(f"  ⚠ Exa research error: {e}")
            return self._research_with_perplexity_fallback(artist, topic)

    def _research_with_perplexity_fallback(self, artist: str, topic: str) -> str:
        """Fallback: research using Perplexity SDK if Exa is unavailable."""
        if not _perplexity_client:
            return ""

        prompt = (
            f"Research the latest news about {artist} and {topic}. "
            "Provide 2-3 key facts or developments that would be interesting "
            "to music fans. Keep it concise and factual."
        )

        try:
            result = _perplexity_client.chat.completions.create(
                model="sonar",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a music industry research assistant. "
                            "Provide factual, current information about "
                            "artists and music news."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.3,
            )
            research = result.choices[0].message.content.strip()
            return self._clean_perplexity_text(research)
        except Exception as e:
            print(f"  ⚠ Perplexity research error: {e}")
            return ""

    def generate_cta_headline(
        self, original_title: str, content: str, artist: str
    ) -> str:
        """Generate high-converting CTA headline using Perplexity SDK"""
        if not _perplexity_client:
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
- Return ONLY the headline text, no markdown or citations

Examples of good CTA headlines:
- "Breaking: [Artist] Just Dropped Something Huge"
- "The Real Reason [Artist] Is Making Waves"
- "What [Artist] Just Revealed Changes Everything"
- "Exclusive: Inside [Artist]'s Latest Move"

New CTA Headline:"""

        try:
            result = _perplexity_client.chat.completions.create(
                model="sonar",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a viral headline writer for a music news app. "
                            "Create headlines that get clicks while staying authentic "
                            "to the story. Return ONLY the headline, no markdown "
                            "formatting, no citations, no brackets."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100,
                temperature=0.8,
            )
            headline = result.choices[0].message.content.strip()
            headline = self._clean_perplexity_text(headline)

            # Guard against model refusals / meta-commentary
            if self._is_refusal(headline):
                print("  ⚠ Perplexity refused headline, using fallback")
                return self._transform_title_fallback(original_title)

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

    def _normalize_url(self, url: str) -> str:
        """Canonicalize URL for reliable duplicate detection."""
        try:
            parts = urlsplit((url or "").strip())
            netloc = parts.netloc.lower()
            path = re.sub(r"/+$", "", parts.path or "")
            return urlunsplit((parts.scheme.lower(), netloc, path, "", ""))
        except Exception:
            return (url or "").strip()

    def load_existing_articles(self):
        """Warm duplicate indexes from Firestore."""
        if not API_KEY:
            return

        self.existing_source_urls.clear()
        self.existing_titles.clear()
        page_token = ""

        while True:
            try:
                token_param = f"&pageToken={page_token}" if page_token else ""
                url = (
                    f"{FIRESTORE_URL}/articles?key={API_KEY}&pageSize=200{token_param}"
                )
                response = self.session.get(url, timeout=15)
                if response.status_code != 200:
                    print(f"  ⚠ Could not warm duplicate index: {response.status_code}")
                    return

                data = response.json()
                for doc in data.get("documents", []):
                    fields = doc.get("fields", {})
                    source_url = fields.get("source_url", {}).get("stringValue", "")
                    title = fields.get("title", {}).get("stringValue", "")
                    if source_url:
                        self.existing_source_urls.add(self._normalize_url(source_url))
                    if title:
                        self.existing_titles.add(title.lower().strip())

                page_token = data.get("nextPageToken", "")
                if not page_token:
                    break
            except Exception as e:
                print(f"  ⚠ Error warming duplicate index: {e}")
                return

        print(
            f"Loaded duplicate index: {len(self.existing_source_urls)} URLs, {len(self.existing_titles)} titles"
        )

    def check_duplicate(self, title: str, source_url: str) -> bool:
        """Check duplicates primarily via canonical source URL."""
        try:
            normalized_title = (title or "").lower().strip()
            normalized_url = self._normalize_url(source_url)

            if normalized_url and normalized_url in self.existing_source_urls:
                return True

            if normalized_title and normalized_title in self.existing_titles:
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

            # Remove 'id' — Firestore rules only allow the 16 content fields.
            # The document ID is set via the URL path, not as a field.
            article_dict.pop("id", None)

            # Enforce Firestore rule constraints so writes aren't rejected.
            # source_url must start with https://
            if not article_dict.get("source_url", "").startswith("https://"):
                article_dict["source_url"] = article_dict["source_url"].replace(
                    "http://", "https://", 1
                )

            # title: max 200 chars
            if len(article_dict.get("title", "")) > 200:
                article_dict["title"] = article_dict["title"][:197] + "..."

            # summary: max 1000 chars
            if len(article_dict.get("summary", "")) > 1000:
                article_dict["summary"] = article_dict["summary"][:997] + "..."

            # full_content: max 4000 chars
            if len(article_dict.get("full_content", "")) > 4000:
                article_dict["full_content"] = (
                    article_dict["full_content"][:3997] + "..."
                )

            canonical_url = self._normalize_url(article.source_url)
            doc_id = hashlib.md5(canonical_url.encode("utf-8")).hexdigest()[:32]

            url = f"{FIRESTORE_URL}/articles/{doc_id}?key={API_KEY}"
            payload = {"fields": self.convert_to_firestore_fields(article_dict)}

            response = requests.patch(url, json=payload, timeout=10)

            if response.status_code in [200, 201]:
                print(f"  ✓ Saved: {article.title[:60]}...")
                if canonical_url:
                    self.existing_source_urls.add(canonical_url)
                self.existing_titles.add((article.title or "").lower().strip())
                return True
            else:
                detail = ""
                try:
                    detail = response.json().get("error", {}).get("message", "")
                except Exception:
                    detail = response.text[:200]
                print(f"  ✗ Failed to save: {response.status_code} — {detail}")
                return False
        except Exception as e:
            print(f"  ✗ Error saving to Firebase: {e}")
            return False

    def process_feed(self, source_name: str, source_config: Dict) -> Tuple[int, int]:
        """Process a single RSS feed with CTA headlines and Perplexity research"""
        print(f"\n📡 Fetching {source_name}...")

        items = self.fetch_rss_feed(source_config["url"])
        print(f"  Found {len(items)} items")
        items = sorted(
            items,
            key=lambda item: self.parse_pub_date(item.get("pub_date", "")),
            reverse=True,
        )
        if items:
            newest = self.parse_pub_date(items[0].get("pub_date", ""))
            oldest = self.parse_pub_date(items[-1].get("pub_date", ""))
            print(
                f"  Feed window: newest={newest.isoformat()} oldest={oldest.isoformat()}"
            )

        processed = 0
        duplicates = 0
        errors = 0
        for item in items[:12]:
            try:
                original_title = item["title"]
                content = item["content"] or item["description"]

                # Check duplicates before expensive model calls
                if self.check_duplicate(original_title, item["link"]):
                    duplicates += 1
                    print(f"  ⚠ Duplicate: {original_title[:50]}...")
                    continue

                # Extract artists first for research
                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                # Generate high-CTA headline (not copy-paste)
                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                # Research with Exa (falls back to Perplexity)
                research = ""
                if main_artist and (_exa_client or _perplexity_client):
                    provider = "Exa" if _exa_client else "Perplexity"
                    print(f"  🔍 Researching with {provider}...")
                    topic = original_title.replace(main_artist, "").strip()
                    research = self.research_with_exa(main_artist, topic)

                # Summarize with DeepSeek (including research if available)
                content_with_research = content
                if research:
                    content_with_research += f"\n\nAdditional context: {research}"

                summary = self.summarize_with_deepseek(cta_title, content_with_research)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, source_config["genre"]
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,  # Use CTA headline, not original
                    summary=summary,
                    full_content=content_with_research[:2000],
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
                errors += 1
                print(f"  ✗ Error processing item: {e}")
                continue

        attempted = min(len(items), 12)
        print(
            f"  [{source_name}] items={len(items)} attempted={attempted} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(items)

    # ------------------------------------------------------------------
    # Exa news discovery
    # ------------------------------------------------------------------

    EXA_QUERIES = [
        "latest hip hop rap music news today",
        "new pop music releases albums today",
        "rock alternative music news today",
        "electronic EDM music news today",
        "gospel christian music news today",
    ]

    def _discover_perplexity_fallback(self) -> Tuple[int, int]:
        """Fallback discovery using Perplexity when Exa is unavailable."""
        if not _perplexity_client:
            print("  ⚠ Neither Exa nor Perplexity available for discovery.")
            return 0, 0

        print("\n🔎 Discovering articles via Perplexity (Exa fallback)...")
        items: List[Dict] = []

        for query in self.EXA_QUERIES:
            prompt = (
                f"Find 3 recent music news articles about: {query}. "
                "For each article, provide ONLY a JSON array with objects "
                'having keys "title", "url", "summary". '
                "No other text, just the JSON array."
            )
            try:
                result = _perplexity_client.chat.completions.create(
                    model="sonar",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a music news researcher. Return ONLY "
                                "valid JSON arrays, no markdown, no explanation."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=600,
                    temperature=0.3,
                )
                raw = result.choices[0].message.content.strip()
                # Strip markdown code fences if present
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
                articles = json.loads(raw)
                for a in articles:
                    title = a.get("title", "").strip()
                    url = a.get("url", "").strip()
                    summary = a.get("summary", "").strip()
                    if title and url and url.startswith("http"):
                        items.append(
                            {
                                "title": title,
                                "link": url,
                                "description": summary[:500],
                                "content": summary,
                                "pub_date": "",
                                "image": None,
                            }
                        )
            except Exception as e:
                print(f"  ⚠ Perplexity discovery error ({query[:30]}...): {e}")

        print(f"  Found {len(items)} Perplexity discovery results")

        processed = 0
        duplicates = 0
        errors = 0

        for item in items:
            try:
                original_title = item["title"]
                content = item["content"] or item["description"]

                if self.check_duplicate(original_title, item["link"]):
                    duplicates += 1
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                summary = self.summarize_with_deepseek(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, "mixed"
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,
                    summary=summary,
                    full_content=content[:2000],
                    source="Perplexity Discovery",
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
                errors += 1
                print(f"  ✗ Error processing Perplexity item: {e}")
                continue

        print(
            f"  [perplexity_discovery] items={len(items)} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(items)

    def discover_exa_articles(self) -> Tuple[int, int]:
        """Discover fresh music news via Exa search and process them.
        Falls back to Perplexity-based discovery when Exa is unavailable."""
        if not _exa_client:
            return self._discover_perplexity_fallback()

        print("\n🔎 Discovering articles via Exa...")
        items: List[Dict] = []

        for query in self.EXA_QUERIES:
            try:
                result = _exa_client.search(
                    query,
                    type="auto",
                    num_results=5,
                    contents={"text": {"max_characters": 2000}},
                )
                for r in result.results:
                    if not r.url or not r.title:
                        continue
                    text = re.sub(r"<[^>]+>", "", r.text or "").strip()
                    text = re.sub(r"\s+", " ", text)
                    items.append(
                        {
                            "title": r.title.strip(),
                            "link": r.url,
                            "description": text[:500],
                            "content": text,
                            "pub_date": "",
                            "image": None,
                        }
                    )
            except Exception as e:
                print(f"  ⚠ Exa query error ({query[:30]}...): {e}")

        print(f"  Found {len(items)} Exa results")

        if not items:
            print("  Exa returned no results, falling back to Perplexity...")
            return self._discover_perplexity_fallback()

        processed = 0
        duplicates = 0
        errors = 0

        for item in items:
            try:
                original_title = item["title"]
                content = item["content"] or item["description"]

                if self.check_duplicate(original_title, item["link"]):
                    duplicates += 1
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                summary = self.summarize_with_deepseek(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, "mixed"
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,
                    summary=summary,
                    full_content=content[:2000],
                    source="Exa Discovery",
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
                errors += 1
                print(f"  ✗ Error processing Exa item: {e}")
                continue

        print(
            f"  [exa_discovery] items={len(items)} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(items)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

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

        if not _perplexity_client:
            print("⚠️  Warning: Perplexity SDK not available. Using fallback headlines.")
            print()

        if not _exa_client:
            print(
                "⚠️  Warning: Exa SDK not available. Will use Perplexity for discovery."
            )
            print()

        total_processed = 0
        total_fetched_items = 0

        self.load_existing_articles()

        # 1. RSS feeds
        for source_name, config in RSS_SOURCES.items():
            try:
                processed, fetched_items = self.process_feed(source_name, config)
                total_processed += processed
                total_fetched_items += fetched_items
            except Exception as e:
                print(f"  ✗ Error with {source_name}: {e}")
                continue

        # 2. Exa news discovery
        try:
            exa_processed, exa_items = self.discover_exa_articles()
            total_processed += exa_processed
            total_fetched_items += exa_items
        except Exception as e:
            print(f"  ✗ Error with Exa discovery: {e}")

        print("\n" + "=" * 50)
        print(f"Fetched {total_fetched_items} feed items")
        print(f"✅ Complete! Added {total_processed} new articles")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if total_fetched_items == 0:
            raise RuntimeError("All RSS feeds returned zero items.")


if __name__ == "__main__":
    try:
        scraper = RSSScraper()
        scraper.run()
    except Exception as exc:
        print(f"❌ Scraper failed: {exc}")
        sys.exit(1)
