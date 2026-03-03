#!/usr/bin/env python3
"""
miny-ven RSS Scraper with AI Summarization
Fetches music news from RSS feeds and summarizes them to 60 words.
Uses Perplexity SDK for headlines/research, DeepSeek for summaries,
and Firestore REST API for storage.
"""

import xml.etree.ElementTree as ET
import base64
import json
import requests
import re
import io
from datetime import datetime
from typing import Optional, Dict, List, Set, Tuple
from dataclasses import dataclass, asdict
import os
import sys
import hashlib
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin
from email.utils import parsedate_to_datetime

import librarium_discovery
import hackerfeeds_discovery

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

# Gemini API (optional — used for AI image generation fallback)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
if GEMINI_API_KEY:
    print(f"✓ Gemini image generation enabled (model: {GEMINI_IMAGE_MODEL})")
else:
    print("⚠ GEMINI_API_KEY not set, AI image generation disabled")

# Firebase Storage (optional — used to persist AI-generated images)
_storage_bucket = None
FIREBASE_STORAGE_BUCKET = os.getenv(
    "FIREBASE_STORAGE_BUCKET", "miny-ven.firebasestorage.app"
)
FIREBASE_SA_B64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "")
if FIREBASE_SA_B64:
    try:
        import firebase_admin
        from firebase_admin import credentials, storage

        sa_info = json.loads(base64.b64decode(FIREBASE_SA_B64))
        cred = credentials.Certificate(sa_info)
        app = firebase_admin.initialize_app(cred)
        bucket_candidates = []
        if FIREBASE_STORAGE_BUCKET:
            bucket_candidates.append(FIREBASE_STORAGE_BUCKET)
        for candidate in ["miny-ven.firebasestorage.app", "miny-ven.appspot.com"]:
            if candidate not in bucket_candidates:
                bucket_candidates.append(candidate)

        for candidate in bucket_candidates:
            try:
                test_bucket = storage.bucket(name=candidate, app=app)
                # Validate bucket existence up front to avoid runtime 404s.
                if test_bucket.exists():
                    _storage_bucket = test_bucket
                    FIREBASE_STORAGE_BUCKET = candidate
                    print(f"✓ Firebase Storage initialized (bucket: {candidate})")
                    break
            except Exception:
                continue

        if not _storage_bucket:
            print(
                "⚠ Firebase Storage bucket not found — using Firestore data URI fallback"
            )
    except Exception as e:
        print(f"⚠ Firebase Storage init failed: {e}")

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
    "tech": [
        "music tech",
        "music technology",
        "audio software",
        "music ai",
        "music streaming",
        "streaming platform",
        "music api",
        "daw",
        "midi",
        "synth",
        "synthesizer",
        "audio plugin",
        "vst",
        "music production",
        "beatmaking",
        "music startup",
        "music app",
        "sound design",
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
    image_source: str = "unknown"


class RSSScraper:
    def __init__(self):
        self.existing_source_urls: Set[str] = set()
        self.existing_titles: Set[str] = set()
        self.session = requests.Session()
        self.run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        self.events: List[Dict[str, object]] = []
        self.artifact_dir = Path(
            os.getenv("SCRAPER_ARTIFACT_DIR", Path(__file__).parent / "artifacts")
        )
        self.perplexity_disabled = False
        self.storage_upload_disabled = False

    def _log_event(self, event: str, level: str = "info", **data: object) -> None:
        self.events.append(
            {
                "ts": datetime.utcnow().isoformat() + "Z",
                "run_id": self.run_id,
                "event": event,
                "level": level,
                "data": data,
            }
        )

    def _flush_artifacts(self, summary: Dict[str, object]) -> None:
        try:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            summary_path = self.artifact_dir / f"summary_{self.run_id}.json"
            events_path = self.artifact_dir / f"events_{self.run_id}.jsonl"
            summary_path.write_text(
                json.dumps(summary, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            with events_path.open("w", encoding="utf-8") as f:
                for event in self.events:
                    f.write(
                        json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
                    )
            print(f"  ✓ Wrote artifacts: {summary_path} and {events_path}")
        except Exception as e:
            print(f"  ⚠ Failed writing artifacts: {e}")

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
            self._log_event(
                "feed_fetch_failed", level="error", feed_url=url, error=str(e)
            )
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

    def _extract_image_from_article_html(
        self, html: str, article_url: str
    ) -> Optional[str]:
        if not html:
            return None

        meta_tags = re.findall(r"<meta\\s+[^>]*>", html, flags=re.IGNORECASE)
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
                    r"([a-zA-Z_:.-]+)\\s*=\\s*['\\\"]([^'\\\"]*)['\\\"]", tag
                )
            )
            prop = attrs.get("property", "").lower()
            name = attrs.get("name", "").lower()
            content = attrs.get("content", "").strip()
            if (prop in wanted_props or name in wanted_props) and content:
                return urljoin(article_url, content)
        return None

    def _fetch_open_graph_image(self, article_url: str) -> Optional[str]:
        if not article_url:
            return None
        try:
            response = self.session.get(
                article_url,
                timeout=12,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; miny-ven-bot/1.0)"},
            )
            if response.status_code >= 400:
                return None
            content_type = (response.headers.get("content-type") or "").lower()
            if (
                "text/html" not in content_type
                and "application/xhtml+xml" not in content_type
            ):
                return None
            return self._extract_image_from_article_html(response.text, article_url)
        except Exception:
            return None

    def _is_valid_image_url(self, image_url: str) -> bool:
        value = (image_url or "").strip()
        if not value:
            return False
        scheme = urlsplit(value).scheme.lower()
        if scheme not in {"http", "https"}:
            return False
        try:
            head = self.session.head(value, timeout=8, allow_redirects=True)
            if head.status_code < 400:
                content_type = (head.headers.get("content-type") or "").lower()
                return content_type.startswith("image/") or not content_type
        except Exception:
            pass
        try:
            probe = self.session.get(
                value, timeout=8, stream=True, allow_redirects=True
            )
            if probe.status_code >= 400:
                return False
            content_type = (probe.headers.get("content-type") or "").lower()
            return content_type.startswith("image/")
        except Exception:
            return False

    def _fetch_artist_image(self, artist_name: str) -> Optional[str]:
        if not artist_name:
            return None
        try:
            # Public endpoint, no API key required.
            response = self.session.get(
                "https://api.deezer.com/search/artist",
                params={"q": artist_name},
                timeout=10,
            )
            if response.status_code != 200:
                return None
            data = response.json()
            for entry in data.get("data", [])[:3]:
                candidate = (
                    entry.get("picture_xl")
                    or entry.get("picture_big")
                    or entry.get("picture_medium")
                    or entry.get("picture")
                    or ""
                )
                if candidate and self._is_valid_image_url(candidate):
                    return candidate
        except Exception:
            return None
        return None

    def _compress_and_upload_image(
        self, image_url: str, storage_path: str
    ) -> Optional[str]:
        """Download image, compress to WebP, upload to Firebase Storage."""
        if not _storage_bucket:
            return None
        try:
            from PIL import Image

            resp = self.session.get(image_url, timeout=30)
            if resp.status_code >= 400:
                return None

            img = Image.open(io.BytesIO(resp.content))
            # Resize to max 800px wide, maintain aspect ratio
            max_width = 800
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
            # Convert to RGB if needed (WebP doesn't support all modes)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=80)
            webp_bytes = buf.getvalue()

            blob = _storage_bucket.blob(storage_path)
            blob.upload_from_string(webp_bytes, content_type="image/webp")
            blob.make_public()

            print(f"  ✓ Uploaded image ({len(webp_bytes) // 1024}KB): {storage_path}")
            self._log_event(
                "image_uploaded",
                storage_path=storage_path,
                size_kb=len(webp_bytes) // 1024,
            )
            return blob.public_url
        except Exception as e:
            print(f"  ⚠ Image upload failed: {e}")
            self._log_event(
                "image_upload_failed",
                level="warning",
                storage_path=storage_path,
                error=str(e),
            )
            return None

    def _generate_gemini_image(
        self, title: str, artist: str, genre: str
    ) -> Optional[str]:
        """Generate an image via Gemini, compress to WebP, upload to Firebase Storage.

        Uses the gemini-2.5-flash-image model which returns base64 data directly.
        Requires Firebase Storage for persistence (base64 is too large for Firestore).
        Returns a permanent public URL from Firebase Storage, or None on failure.
        """
        if not GEMINI_API_KEY:
            return None

        api_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_IMAGE_MODEL}:generateContent"
        )
        prompt_attempts = [
            (
                "Create a photorealistic editorial hero image for a music news card. "
                "No text, no logo, no watermark, no collage. "
                f"Artist focus: {artist or 'unknown artist'}. "
                f"Genre context: {genre or 'mixed'}. "
                f"Headline context: {title[:180]}."
            ),
            (
                "Generate a cinematic music-magazine hero photo. "
                "Single scene, realistic lighting, people/instruments allowed, no text overlays. "
                f"Genre: {genre or 'mixed'}. Artist cue: {artist or 'unknown artist'}."
            ),
            (
                "Create an abstract-but-photoreal music atmosphere image suitable for a news card. "
                "No text, no logos, no brand marks, no collage. "
                f"Theme: {genre or 'mixed'} music news."
            ),
        ]

        for attempt, prompt in enumerate(prompt_attempts, start=1):
            payload = json.dumps(
                {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseModalities": ["TEXT", "IMAGE"],
                    },
                }
            )

            try:
                resp = self.session.post(
                    api_url,
                    data=payload,
                    headers={
                        "x-goog-api-key": GEMINI_API_KEY,
                        "Content-Type": "application/json",
                    },
                    timeout=60,
                )
                if resp.status_code != 200:
                    print(
                        f"  ⚠ Gemini API error (attempt {attempt}): {resp.status_code} — {resp.text[:160]}"
                    )
                    self._log_event(
                        "gemini_image_generation_failed",
                        level="warning",
                        model=GEMINI_IMAGE_MODEL,
                        status_code=resp.status_code,
                        attempt=attempt,
                        error=resp.text[:300],
                    )
                    if "expired" in resp.text.lower() or "api key" in resp.text.lower():
                        return None
                    time.sleep(1.2)
                    continue

                data = resp.json()
                parts = (
                    data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                )

                for part in parts:
                    inline = part.get("inlineData") or part.get("inline_data")
                    if not inline or not inline.get("data"):
                        continue

                    image_bytes = base64.b64decode(inline["data"])
                    mime = inline.get("mimeType") or inline.get(
                        "mime_type", "image/png"
                    )
                    print(
                        f"  ✓ Gemini generated image ({len(image_bytes) // 1024}KB, {mime})"
                    )
                    return self._compress_and_upload_bytes(image_bytes, title)

                print(f"  ⚠ Gemini response had no image data (attempt {attempt})")
                self._log_event(
                    "gemini_image_no_data",
                    level="warning",
                    model=GEMINI_IMAGE_MODEL,
                    attempt=attempt,
                )
                time.sleep(1.2)
            except Exception as e:
                print(f"  ⚠ Gemini image generation failed (attempt {attempt}): {e}")
                self._log_event(
                    "gemini_image_generation_failed",
                    level="warning",
                    model=GEMINI_IMAGE_MODEL,
                    attempt=attempt,
                    error=str(e),
                )
                time.sleep(1.2)

        return None

    def _compress_and_upload_bytes(
        self, image_bytes: bytes, title: str
    ) -> Optional[str]:
        """Compress raw image bytes to WebP. Upload to Firebase Storage if
        available, otherwise return a data URI for direct embedding."""
        try:
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))

            # 800px covers desktop hero (780px rendered width)
            max_width = 800
            quality = 80 if _storage_bucket else 70

            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=quality)
            webp_bytes = buf.getvalue()

            # Attempt Firebase Storage upload
            if _storage_bucket and not self.storage_upload_disabled:
                try:
                    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:40].strip("-")
                    digest = hashlib.sha1(image_bytes[:256]).hexdigest()[:12]
                    storage_path = f"article-images/{slug}-{digest}.webp"

                    blob = _storage_bucket.blob(storage_path)
                    blob.upload_from_string(webp_bytes, content_type="image/webp")
                    blob.make_public()

                    print(
                        f"  ✓ Uploaded image ({len(webp_bytes) // 1024}KB): {storage_path}"
                    )
                    self._log_event(
                        "image_uploaded",
                        storage_path=storage_path,
                        size_kb=len(webp_bytes) // 1024,
                    )
                    return blob.public_url
                except Exception as e:
                    err = self._trim_error(e)
                    if any(x in err.lower() for x in ["billing", "403", "permission"]):
                        self.storage_upload_disabled = True
                    print(f"  ⚠ Storage upload failed, using data URI: {err}")

            # Fallback: return data URI (works directly in <img> tags)
            b64 = base64.b64encode(webp_bytes).decode()
            data_uri = f"data:image/webp;base64,{b64}"
            print(f"  ✓ Generated data URI ({len(webp_bytes) // 1024}KB)")
            self._log_event(
                "image_data_uri",
                size_kb=len(webp_bytes) // 1024,
            )
            return data_uri

        except Exception as e:
            print(f"  ⚠ Image compression failed: {e}")
            self._log_event(
                "image_compress_failed",
                level="warning",
                error=str(e),
            )
            return None

    def resolve_article_image(
        self,
        item: Dict[str, str],
        *,
        title: str,
        artist_names: List[str],
        primary_genre: str,
    ) -> Tuple[str, str]:
        article_url = self._normalize_source_url(item.get("link", ""))
        candidates = [
            ("rss", item.get("image", "")),
            ("open_graph", self._fetch_open_graph_image(article_url)),
        ]
        for strategy, candidate in candidates:
            if not candidate:
                continue
            normalized = self._normalize_source_url(
                urljoin(article_url, candidate.strip())
            )
            if self._is_valid_image_url(normalized):
                return normalized, strategy

        if artist_names:
            artist_img = self._fetch_artist_image(artist_names[0])
            if artist_img:
                return artist_img, "artist_api"

        generated = self._generate_gemini_image(
            title,
            artist_names[0] if artist_names else "",
            primary_genre,
        )
        if generated:
            return generated, "ai_generated_gemini"

        return "", "none"

    def summarize_with_gemini(self, title: str, content: str) -> str:
        """Summarize article to exactly 60 words using Gemini 2.5 Flash"""
        if not GEMINI_API_KEY:
            words = content.split()[:60]
            return " ".join(words) + "." if words else title

        GEMINI_SUMMARY_MODEL = "gemini-2.5-flash"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_SUMMARY_MODEL}:generateContent"
        )

        prompt = f"""Summarize this music news article in EXACTLY 60 words or less.

Title: {title}

Content: {content[:2000]}

Requirements:
- Exactly 60 words maximum
- Include artist names, labels, or platforms mentioned
- Mention the key development or news angle
- Write in a punchy music-journalist tone
- No filler words, no meta-commentary
- If this is not music-related, say SKIP

Summary (60 words max):"""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {
                "parts": [
                    {
                        "text": "You are a professional music journalist who writes concise 60-word news briefs for creators."
                    }
                ]
            },
            "generationConfig": {
                "maxOutputTokens": 256,
                "temperature": 0.7,
            },
        }

        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            summary = (
                result.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )

            if not summary or self._is_refusal(summary) or summary.upper().startswith("SKIP"):
                print("  ⚠ Gemini refused/skipped summary, using fallback")
                words = content.split()[:60]
                return " ".join(words) + "." if words else title

            words = summary.split()
            if len(words) > 60:
                summary = " ".join(words[:60]) + "."

            return summary
        except Exception as e:
            print(f"  ⚠ Gemini summary error: {e}, using fallback")
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
    def _trim_error(exc: Exception, limit: int = 180) -> str:
        text = str(exc).replace("\n", " ").replace("\r", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]

    @staticmethod
    def _is_perplexity_auth_or_quota_error(exc: Exception) -> bool:
        text = str(exc).lower()
        needles = [
            "401",
            "403",
            "authorization",
            "unauthorized",
            "forbidden",
            "quota",
            "credit",
            "insufficient",
            "billing",
        ]
        return any(n in text for n in needles)

    def _disable_perplexity_if_needed(self, exc: Exception, context: str) -> None:
        if self.perplexity_disabled:
            return
        if self._is_perplexity_auth_or_quota_error(exc):
            self.perplexity_disabled = True
            msg = self._trim_error(exc)
            print(f"  ⚠ Perplexity disabled for this run ({context}): {msg}")
            self._log_event(
                "perplexity_disabled",
                level="warning",
                context=context,
                error=msg,
            )

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
        if not _perplexity_client or self.perplexity_disabled:
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
            self._disable_perplexity_if_needed(e, "research")
            print(f"  ⚠ Perplexity research error: {self._trim_error(e)}")
            return ""

    def generate_cta_headline(
        self, original_title: str, content: str, artist: str
    ) -> str:
        """Generate high-converting CTA headline using Perplexity SDK"""
        if not _perplexity_client or self.perplexity_disabled:
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
            self._disable_perplexity_if_needed(e, "cta_headline")
            print(f"  ⚠ CTA headline error: {self._trim_error(e)}, using fallback")
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

    # Music-relevance keywords — at least one must appear for non-RSS articles
    MUSIC_RELEVANCE_KEYWORDS = {
        "music", "song", "songs", "album", "albums", "artist", "artists",
        "band", "bands", "tour", "tours", "concert", "festival", "dj",
        "hip hop", "hip-hop", "rap", "rapper", "pop", "rock", "gospel",
        "electronic", "edm", "r&b", "rnb", "singer", "vocalist",
        "grammy", "billboard", "spotify", "vinyl", "record label",
        "mixtape", "ep ", "lp ", "single", "remix", "producer",
        "beats", "lyrics", "verse", "chorus", "track", "tracklist",
        "streaming", "playlist", "soundcloud", "apple music",
        "music video", "headliner", "genre", "indie", "punk", "metal",
        "jazz", "classical", "country", "reggae", "latin", "afrobeat",
        "k-pop", "idol", "boyband", "girlband",
    }

    def is_music_relevant(self, title: str, content: str, source_genre: str) -> bool:
        """Gate: reject articles with no music relevance."""
        # Trusted RSS sources (pitchfork, billboard, etc.) are always relevant
        if source_genre in ("gospel", "mixed"):
            return True
        text = (title + " " + content).lower()
        return any(kw in text for kw in self.MUSIC_RELEVANCE_KEYWORDS)

    def classify_genre(self, title: str, content: str, source_genre: str) -> tuple:
        """Classify article genre based on content"""
        text = (title + " " + content).lower()

        if source_genre == "gospel":
            return "gospel", []
        if source_genre == "tech":
            return "tech", []

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

    def _normalize_source_url(self, raw_url: str) -> str:
        value = (raw_url or "").strip()
        if not value:
            return ""
        parts = urlsplit(value)
        if (parts.scheme or "").lower() == "http":
            parts = parts._replace(scheme="https")
            return urlunsplit(parts)
        return value

    def _build_doc_id(self, article: Article) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", (article.title or "").lower()).strip("-")
        slug = (slug[:24] or "article").strip("-")
        hash_input = (
            f"{article.source_url}|{article.published_at.isoformat()}|{article.title}"
        ).encode("utf-8", errors="ignore")
        digest = hashlib.sha1(hash_input).hexdigest()[:20]
        return f"{slug}-{digest}"

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
                    self._log_event(
                        "warm_index_failed",
                        level="warning",
                        status_code=response.status_code,
                        response_excerpt=(response.text or "")[:300],
                    )
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
                self._log_event("warm_index_exception", level="warning", error=str(e))
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
            if not API_KEY:
                print("  ✗ Failed to save: FIREBASE_API_KEY is missing")
                self._log_event(
                    "save_failed",
                    level="error",
                    reason="missing_api_key",
                    title=article.title,
                )
                return False

            article_dict = asdict(article)
            article_dict["published_at"] = article.published_at.isoformat()
            article_dict["fetched_at"] = article.fetched_at.isoformat()

            # Remove 'id' — Firestore rules only allow the 16 content fields.
            # The document ID is set via the URL path, not as a field.
            article_dict.pop("id", None)

            # Enforce Firestore rule constraints so writes aren't rejected.
            # source_url must start with https://
            article_dict["source_url"] = self._normalize_source_url(
                article_dict.get("source_url", "")
            )
            if not article_dict["source_url"].startswith("https://"):
                self._log_event(
                    "save_failed",
                    level="error",
                    reason="invalid_source_url",
                    source_url=article_dict["source_url"],
                    title=article.title,
                )
                print(
                    f"  ✗ Failed to save: invalid source_url ({article_dict['source_url']})"
                )
                return False

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

            canonical_url = self._normalize_url(article_dict["source_url"])
            doc_id = self._build_doc_id(
                Article(
                    **{
                        **article.__dict__,
                        "source_url": article_dict["source_url"],
                    }
                )
            )

            url = f"{FIRESTORE_URL}/articles/{doc_id}?key={API_KEY}"
            payload = {"fields": self.convert_to_firestore_fields(article_dict)}

            response = requests.patch(url, json=payload, timeout=10)

            if response.status_code in [200, 201]:
                print(f"  ✓ Saved: {article.title[:60]}...")
                self._log_event(
                    "save_ok",
                    doc_id=doc_id,
                    status_code=response.status_code,
                    title=article.title,
                    source=article.source,
                )
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
                # Backward compatibility: older deployed rules may not yet allow image_source.
                if article_dict.get("image_source") and response.status_code in (
                    400,
                    403,
                ):
                    compat_dict = dict(article_dict)
                    compat_dict.pop("image_source", None)
                    compat_payload = {
                        "fields": self.convert_to_firestore_fields(compat_dict)
                    }
                    compat_resp = requests.patch(url, json=compat_payload, timeout=10)
                    if compat_resp.status_code in (200, 201):
                        print(f"  ✓ Saved (compat): {article.title[:60]}...")
                        self._log_event(
                            "save_ok_compat",
                            doc_id=doc_id,
                            status_code=compat_resp.status_code,
                            title=article.title,
                            dropped_field="image_source",
                        )
                        if canonical_url:
                            self.existing_source_urls.add(canonical_url)
                        self.existing_titles.add((article.title or "").lower().strip())
                        return True

                print(f"  ✗ Failed to save: {response.status_code} — {detail}")
                self._log_event(
                    "save_failed",
                    level="error",
                    doc_id=doc_id,
                    status_code=response.status_code,
                    detail=detail,
                    title=article.title,
                )
                return False
        except Exception as e:
            print(f"  ✗ Error saving to Firebase: {e}")
            self._log_event(
                "save_exception", level="error", title=article.title, error=str(e)
            )
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

                summary = self.summarize_with_gemini(cta_title, content_with_research)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, source_config["genre"]
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))
                image_url, image_source = self.resolve_article_image(
                    item,
                    title=cta_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,  # Use CTA headline, not original
                    summary=summary,
                    full_content=content_with_research[:2000],
                    source=source_name.replace("_", " ").title(),
                    source_url=self._normalize_source_url(item["link"]),
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=image_url,
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                    image_source=image_source,
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
        if not _perplexity_client or self.perplexity_disabled:
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
                self._disable_perplexity_if_needed(e, "discovery")
                print(
                    f"  ⚠ Perplexity discovery error ({query[:30]}...): {self._trim_error(e)}"
                )
                if self.perplexity_disabled:
                    break

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

                if not self.is_music_relevant(original_title, content, "discovery"):
                    print(f"  ⛔ Not music-relevant: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                summary = self.summarize_with_gemini(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, "mixed"
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))
                image_url, image_source = self.resolve_article_image(
                    item,
                    title=cta_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,
                    summary=summary,
                    full_content=content[:2000],
                    source="Perplexity Discovery",
                    source_url=self._normalize_source_url(item["link"]),
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=image_url,
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                    image_source=image_source,
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

                if not self.is_music_relevant(original_title, content, "discovery"):
                    print(f"  ⛔ Not music-relevant: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                summary = self.summarize_with_gemini(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, "mixed"
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))
                image_url, image_source = self.resolve_article_image(
                    item,
                    title=cta_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,
                    summary=summary,
                    full_content=content[:2000],
                    source="Exa Discovery",
                    source_url=self._normalize_source_url(item["link"]),
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=image_url,
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                    image_source=image_source,
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
    # Librarium discovery (supplementary, after Exa)
    # ------------------------------------------------------------------

    def discover_librarium_articles(self) -> Tuple[int, int]:
        """Discover fresh music news via librarium multi-provider search.
        Runs after Exa as a supplementary source."""
        if not librarium_discovery.is_available():
            print("\n⚠ librarium CLI not available, skipping")
            return 0, 0

        print("\n🔎 Discovering articles via librarium (supplementary)...")
        items = librarium_discovery.discover()

        if not items:
            print("  librarium returned no results")
            return 0, 0

        print(f"  Found {len(items)} librarium results")

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

                if not self.is_music_relevant(original_title, content, "discovery"):
                    print(f"  ⛔ Not music-relevant: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                summary = self.summarize_with_gemini(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, "mixed"
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))
                image_url, image_source = self.resolve_article_image(
                    item,
                    title=cta_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,
                    summary=summary,
                    full_content=content[:2000],
                    source="Librarium Discovery",
                    source_url=self._normalize_source_url(item["link"]),
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=image_url,
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                    image_source=image_source,
                )

                if self.save_to_firebase(article):
                    processed += 1

            except Exception as e:
                errors += 1
                print(f"  ✗ Error processing librarium item: {e}")
                continue

        print(
            f"  [librarium_discovery] items={len(items)} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(items)

    # ------------------------------------------------------------------
    # hacker-feeds discovery (supplementary, after librarium)
    # ------------------------------------------------------------------

    def discover_hackerfeeds_articles(self) -> Tuple[int, int]:
        """Discover additional candidate links from hacker-feeds CLI."""
        if not hackerfeeds_discovery.is_available():
            print("\n⚠ hf CLI not available, skipping hackerfeeds discovery")
            return 0, 0

        print("\n🔎 Discovering articles via hacker-feeds (supplementary)...")
        items = hackerfeeds_discovery.discover()

        if not items:
            print("  hacker-feeds returned no results")
            return 0, 0

        print(f"  Found {len(items)} hacker-feeds results")

        processed = 0
        duplicates = 0
        errors = 0

        for item in items:
            try:
                original_title = item["title"]
                content = (
                    item.get("content") or item.get("description") or original_title
                )

                if self.check_duplicate(original_title, item["link"]):
                    duplicates += 1
                    continue

                if not self.is_music_relevant(original_title, content, "discovery"):
                    print(f"  ⛔ Not music-relevant: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                print("  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )
                summary = self.summarize_with_gemini(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, "mixed"
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))
                image_url, image_source = self.resolve_article_image(
                    item,
                    title=cta_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                source_label = "HackerFeeds Discovery"
                source_hint = str(item.get("source_hint", "")).strip()
                if source_hint:
                    source_label = f"HackerFeeds ({source_hint})"

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", cta_title.lower())[:50],
                    title=cta_title,
                    summary=summary,
                    full_content=content[:2000],
                    source=source_label,
                    source_url=self._normalize_source_url(item["link"]),
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=image_url,
                    published_at=pub_date,
                    read_time=60,
                    share_count=0,
                    email_count=0,
                    bookmark_count=0,
                    view_count=0,
                    fetched_at=datetime.now(),
                    image_source=image_source,
                )

                if self.save_to_firebase(article):
                    processed += 1

            except Exception as e:
                errors += 1
                print(f"  ✗ Error processing hacker-feeds item: {e}")
                continue

        print(
            f"  [hackerfeeds_discovery] items={len(items)} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(items)

    # ------------------------------------------------------------------
    # Archive stale articles
    # ------------------------------------------------------------------

    ARCHIVE_HOURS = int(os.getenv("ARCHIVE_AFTER_HOURS", "72"))

    def archive_stale_articles(self) -> int:
        """Move articles older than ARCHIVE_HOURS to articles_archive."""
        if not API_KEY:
            return 0

        cutoff = datetime.utcnow() - __import__("datetime").timedelta(
            hours=self.ARCHIVE_HOURS
        )
        print(
            f"\n🗄  Archiving articles older than {self.ARCHIVE_HOURS}h (before {cutoff.isoformat()}Z)..."
        )

        page_token = ""
        archived = 0
        errors = 0

        while True:
            try:
                token_param = f"&pageToken={page_token}" if page_token else ""
                url = (
                    f"{FIRESTORE_URL}/articles?key={API_KEY}&pageSize=200{token_param}"
                )
                response = self.session.get(url, timeout=15)
                if response.status_code != 200:
                    print(
                        f"  ⚠ Could not list articles for archiving: {response.status_code}"
                    )
                    break

                data = response.json()
                docs = data.get("documents", [])
                if not docs:
                    break

                for doc in docs:
                    fields = doc.get("fields", {})
                    doc_path = doc.get("name", "")
                    doc_id = doc_path.split("/")[-1]

                    # Determine age from fetched_at or published_at
                    ts_str = fields.get("fetched_at", {}).get(
                        "stringValue", ""
                    ) or fields.get("published_at", {}).get("stringValue", "")
                    if not ts_str:
                        continue

                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts_naive = ts.replace(tzinfo=None)
                    except Exception:
                        continue

                    if ts_naive >= cutoff:
                        continue

                    # Ensure required fields exist for archive write
                    if "image_source" not in fields:
                        fields["image_source"] = {"stringValue": "unknown"}

                    # Copy to articles_archive
                    archive_url = (
                        f"{FIRESTORE_URL}/articles_archive/{doc_id}?key={API_KEY}"
                    )
                    archive_payload = {"fields": fields}
                    try:
                        resp = requests.patch(
                            archive_url, json=archive_payload, timeout=10
                        )
                        if resp.status_code not in (200, 201):
                            errors += 1
                            continue

                        # Delete from articles
                        delete_url = f"{FIRESTORE_URL}/articles/{doc_id}?key={API_KEY}"
                        del_resp = requests.delete(delete_url, timeout=10)
                        if del_resp.status_code in (200, 204):
                            archived += 1
                        else:
                            errors += 1
                    except Exception as e:
                        errors += 1
                        continue

                page_token = data.get("nextPageToken", "")
                if not page_token:
                    break
            except Exception as e:
                print(f"  ⚠ Archive error: {e}")
                break

        print(f"  Archived {archived} articles ({errors} errors)")
        self._log_event("archive_complete", archived=archived, errors=errors)
        return archived

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

        if librarium_discovery.is_available():
            print("✓ Librarium CLI available for supplementary discovery")
        else:
            print(
                "⚠️  Warning: Librarium CLI not installed. Supplementary discovery disabled."
            )

        if hackerfeeds_discovery.is_available():
            print("✓ hacker-feeds CLI available for supplementary discovery")
        else:
            print("⚠️  Warning: hf CLI not installed. hacker-feeds discovery disabled.")
        print()

        total_processed = 0
        total_fetched_items = 0
        source_stats: Dict[str, Dict[str, int]] = {}

        self.load_existing_articles()

        # 1. RSS feeds
        for source_name, config in RSS_SOURCES.items():
            try:
                processed, fetched_items = self.process_feed(source_name, config)
                total_processed += processed
                total_fetched_items += fetched_items
                source_stats[source_name] = {
                    "saved": processed,
                    "items_found": fetched_items,
                }
            except Exception as e:
                print(f"  ✗ Error with {source_name}: {e}")
                self._log_event(
                    "source_failed", level="error", source=source_name, error=str(e)
                )
                continue

        # 2. Exa news discovery
        try:
            exa_processed, exa_items = self.discover_exa_articles()
            total_processed += exa_processed
            total_fetched_items += exa_items
            source_stats["exa_discovery"] = {
                "saved": exa_processed,
                "items_found": exa_items,
            }
        except Exception as e:
            print(f"  ✗ Error with Exa discovery: {e}")
            self._log_event(
                "source_failed", level="error", source="exa_discovery", error=str(e)
            )

        # 3. Librarium supplementary discovery
        try:
            lib_processed, lib_items = self.discover_librarium_articles()
            total_processed += lib_processed
            total_fetched_items += lib_items
            source_stats["librarium_discovery"] = {
                "saved": lib_processed,
                "items_found": lib_items,
            }
        except Exception as e:
            print(f"  ✗ Error with librarium discovery: {e}")
            self._log_event(
                "source_failed",
                level="error",
                source="librarium_discovery",
                error=str(e),
            )

        # 4. Archive stale articles
        try:
            hf_processed, hf_items = self.discover_hackerfeeds_articles()
            total_processed += hf_processed
            total_fetched_items += hf_items
            source_stats["hackerfeeds_discovery"] = {
                "saved": hf_processed,
                "items_found": hf_items,
            }
        except Exception as e:
            print(f"  ✗ Error with hacker-feeds discovery: {e}")
            self._log_event(
                "source_failed",
                level="error",
                source="hackerfeeds_discovery",
                error=str(e),
            )

        # 5. Archive stale articles
        try:
            archived_count = self.archive_stale_articles()
            source_stats["archive"] = {"archived": archived_count}
        except Exception as e:
            print(f"  ✗ Error archiving: {e}")
            self._log_event("archive_failed", level="error", error=str(e))

        print("\n" + "=" * 50)
        print(f"Fetched {total_fetched_items} feed items")
        print(f"✅ Complete! Added {total_processed} new articles")
        print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        summary = {
            "run_id": self.run_id,
            "version": "rss-main-plus-artifacts",
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "total_processed": total_processed,
            "total_fetched_items": total_fetched_items,
            "source_stats": source_stats,
        }
        self._log_event(
            "run_summary",
            total_processed=total_processed,
            total_fetched_items=total_fetched_items,
        )
        self._flush_artifacts(summary)

        if total_fetched_items == 0:
            raise RuntimeError("All RSS feeds returned zero items.")


if __name__ == "__main__":
    try:
        scraper = RSSScraper()
        scraper.run()
    except Exception as exc:
        print(f"❌ Scraper failed: {exc}")
        sys.exit(1)
