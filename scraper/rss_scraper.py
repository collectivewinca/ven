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
from datetime import datetime, timedelta, timezone
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

# Brave Search API (primary article discovery — replaces Exa)
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
if BRAVE_API_KEY:
    print("✓ Brave Search enabled for article discovery")
else:
    print("⚠ BRAVE_API_KEY not set, Brave discovery disabled")

# DDGS (optional — supplementary web discovery)
_ddgs_client = None
try:
    from ddgs import DDGS

    _ddgs_client = DDGS()
except ImportError:
    print("⚠ ddgs package not installed, DDGS discovery disabled")
except Exception as e:
    print(f"⚠ DDGS init failed: {e}")

# Gemini removed 2026-04-20 — images via NVIDIA SD3, text via NVIDIA MiniMax / DeepSeek.

# DeepSeek API (optional — used as text generation fallback after NVIDIA)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
if DEEPSEEK_API_KEY:
    print(f"✓ DeepSeek text generation enabled (model: {DEEPSEEK_MODEL})")

# NVIDIA NIM chat/image APIs (optional — primary for text and image generation)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_CHAT_MODEL = os.getenv("NVIDIA_CHAT_MODEL", "minimaxai/minimax-m2.5")
NVIDIA_CHAT_URL = os.getenv(
    "NVIDIA_CHAT_URL", "https://integrate.api.nvidia.com/v1/chat/completions"
)
NVIDIA_IMAGE_URL = os.getenv(
    "NVIDIA_IMAGE_URL",
    "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell",
)
if NVIDIA_API_KEY:
    print(f"✓ NVIDIA enabled (chat model: {NVIDIA_CHAT_MODEL})")
else:
    print("⚠ NVIDIA_API_KEY not set, NVIDIA generation disabled")

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
    "alfitude": {"url": "https://alfitude.com/feed/", "genre": "mixed", "priority": 2},
    "bandcamp_daily": {"url": "https://daily.bandcamp.com/feed", "genre": "mixed", "priority": 2},
    "brazil_beat": {"url": "https://brazilbeatblog.wordpress.com/feed/", "genre": "mixed", "priority": 2},
    "consequence": {"url": "https://consequence.net/feed/", "genre": "mixed", "priority": 2},
    "diy_mag": {"url": "https://diymag.com/feeds/all", "genre": "mixed", "priority": 2, "display_name": "DIY Mag"},
    "dj_mag": {"url": "https://djmag.com/feed", "genre": "mixed", "priority": 2, "display_name": "DJ Mag"},
    "earmilk": {"url": "https://earmilk.com/feed/", "genre": "mixed", "priority": 2},
    "east_of_8th": {"url": "https://eastof8th.com/feed/", "genre": "mixed", "priority": 2, "display_name": "East of 8th"},
    "fact_mag": {"url": "https://www.factmag.com/feed/", "genre": "mixed", "priority": 2, "display_name": "FACT Mag"},
    "for_the_love_of_bands": {"url": "https://fortheloveofbands.com/feed/", "genre": "mixed", "priority": 2, "display_name": "For the Love of Bands"},
    "good_because_danish": {"url": "https://goodbecausedanish.com/feed/", "genre": "mixed", "priority": 2, "display_name": "Good Because Danish"},
    "gorilla_vs_bear": {"url": "https://www.gorillavsbear.net/feed/", "genre": "mixed", "priority": 2, "display_name": "Gorilla vs Bear"},
    "iq_mag": {"url": "https://www.iq-mag.net/feed/", "genre": "mixed", "priority": 2, "display_name": "IQ Mag"},
    "lefuturewave": {"url": "https://lefuturewave.com/feed/", "genre": "mixed", "priority": 2},
    "line_of_best_fit": {"url": "https://www.thelineofbestfit.com/feed", "genre": "mixed", "priority": 2, "display_name": "The Line of Best Fit"},
    "metropolis_japan": {"url": "https://metropolisjapan.com/feed/", "genre": "mixed", "priority": 2, "display_name": "Metropolis Japan"},
    "moroccan_tape_stash": {"url": "https://moroccantapestash.blogspot.com/feeds/posts/default", "genre": "mixed", "priority": 2, "display_name": "Moroccan Tape Stash"},
    "music_mecca": {"url": "https://musicmecca.org/feed/", "genre": "mixed", "priority": 2},
    "muzique_magazine": {"url": "https://muziquemagazine.com/feed/", "genre": "mixed", "priority": 2, "display_name": "Muzique Magazine"},
    "nme": {"url": "https://www.nme.com/feed", "genre": "mixed", "priority": 2, "display_name": "NME"},
    "obscure_sound": {"url": "https://obscuresound.com/feed/", "genre": "mixed", "priority": 2},
    "parapop": {"url": "https://parapop.net/feed/", "genre": "mixed", "priority": 2},
    "quietus": {"url": "https://thequietus.com/feed", "genre": "mixed", "priority": 2},
    "radionica": {"url": "https://www.radionica.rocks/rss.xml", "genre": "mixed", "priority": 2},
    "remezcla": {"url": "https://remezcla.com/feed/", "genre": "mixed", "priority": 2},
    "sounds_and_colours": {"url": "https://soundsandcolours.com/music/feed/", "genre": "mixed", "priority": 2, "display_name": "Sounds and Colours"},
    "stereogum": {"url": "https://www.stereogum.com/feed/", "genre": "mixed", "priority": 2},
    "the_beat_bali": {"url": "https://thebeatbali.com/feed/", "genre": "mixed", "priority": 2, "display_name": "The Beat Bali"},
    "twangville": {"url": "https://twangville.com/feed/", "genre": "mixed", "priority": 2},
    "under_the_radar": {"url": "http://www.undertheradarmag.com/site/rss", "genre": "mixed", "priority": 2, "display_name": "Under the Radar"},
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
    location: str = ""


class RSSScraper:
    # Max articles for the same primary artist in the active (72h) window.
    # Prevents one artist/event dominating the feed.
    MAX_ARTICLES_PER_ARTIST = 2

    def __init__(self):
        self.existing_source_urls: Set[str] = set()
        self.existing_titles: Set[str] = set()
        self.existing_artist_counts: Dict[str, int] = {}
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

    def _extract_model_text(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            return ""
        # Remove explicit thinking blocks.
        t = re.sub(r"<think>.*?</think>", "", t, flags=re.IGNORECASE | re.DOTALL)
        # Some providers emit an opening <think> without a closing tag.
        if t.lstrip().lower().startswith("<think>"):
            t = re.sub(r"^\s*<think>", "", t, flags=re.IGNORECASE)
            parts = re.split(r"\n\s*\n", t, maxsplit=1)
            if len(parts) == 2:
                t = parts[1]
        return t.strip()

    def _generate_text_response(
        self,
        prompt: str,
        *,
        system_prompt: str,
        max_tokens: int = 800,
        temperature: float = 0.6,
    ) -> str:
        if NVIDIA_API_KEY:
            try:
                payload = {
                    "model": NVIDIA_CHAT_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                r = self.session.post(
                    NVIDIA_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {NVIDIA_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=45,
                )
                r.raise_for_status()
                raw = (
                    r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                )
                cleaned = self._extract_model_text(raw)
                if cleaned:
                    return cleaned
            except Exception as e:
                print(f"  ⚠ NVIDIA text generation error: {self._trim_error(e)}")

        if DEEPSEEK_API_KEY:
            try:
                payload = {
                    "model": DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max(256, max_tokens * 4),
                    "temperature": temperature,
                }
                r = self.session.post(
                    f"{DEEPSEEK_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30,
                )
                r.raise_for_status()
                raw = (
                    r.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                cleaned = self._extract_model_text(raw)
                if cleaned:
                    return cleaned
            except Exception as e:
                print(f"  ⚠ DeepSeek text generation error: {self._trim_error(e)}")

        return ""

    def _decode_nvidia_image_payload(self, image_value: str) -> Optional[bytes]:
        raw = (image_value or "").strip()
        if not raw:
            return None
        if raw.startswith("data:"):
            try:
                raw = raw.split(",", 1)[1]
            except Exception:
                return None
        try:
            return base64.b64decode(raw)
        except Exception:
            return None

    def _generate_nvidia_image(self, title: str, artist: str, genre: str) -> Optional[str]:
        if not NVIDIA_API_KEY:
            return None
        prompt = (
            "Create a photorealistic editorial hero image for a music news card. "
            "No text, no logo, no watermark. "
            f"Artist focus: {artist or 'unknown artist'}. "
            f"Genre context: {genre or 'mixed'}. "
            f"Headline context: {title[:180]}."
        )
        try:
            r = self.session.post(
                NVIDIA_IMAGE_URL,
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"prompt": prompt, "width": 1024, "height": 1024, "steps": 4, "seed": 0},
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            # FLUX returns {"artifacts":[{"base64":...}]}, SD3 returned {"image":...}
            image_b64 = data.get("image") or (
                data.get("artifacts", [{}])[0].get("base64", "") if data.get("artifacts") else ""
            )
            image_bytes = self._decode_nvidia_image_payload(image_b64)
            if not image_bytes:
                return None
            print(f"  ✓ NVIDIA generated image ({len(image_bytes) // 1024}KB)")
            return self._compress_and_upload_bytes(image_bytes, title)
        except Exception as e:
            print(f"  ⚠ NVIDIA image generation failed: {self._trim_error(e)}")
            return None

    # _generate_gemini_image removed 2026-04-20 — NVIDIA SD3 (_generate_nvidia_image) is the
    # sole image-gen path. If NVIDIA fails the image flow returns ("", "none").

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

        generated = self._generate_nvidia_image(
            title,
            artist_names[0] if artist_names else "",
            primary_genre,
        )
        if generated:
            return generated, "ai_generated_nvidia"

        return "", "none"

    def summarize_with_gemini(self, title: str, content: str) -> str:
        """Summarize article to ~60 words via NVIDIA (primary) / DeepSeek (fallback).

        Name retained for backward compatibility with existing call sites.
        Internally routes through _generate_text_response (no Gemini dependency).
        """
        # If content is too sparse, try fetching the source URL from title context
        if len(content.split()) < 40 and content.startswith("http"):
            content = self._fetch_article_text(content) or content

        prompt = f"""Write a 60-word music news summary. Count every word carefully — it must be between 55 and 65 words.

Title: {title}

Article: {content[:2000]}

Rules:
- MUST be 55–65 words (count carefully before responding)
- Include the artist name, the news development, and why it matters
- Punchy music-journalist tone — no filler, no fluff
- If article is thin, expand with context about the artist or event
- Do NOT start with "Summary:" or the title
- If this is clearly not music-related, say SKIP

Your 60-word summary:"""

        try:
            summary = self._generate_text_response(
                prompt,
                system_prompt=(
                    "You are a professional music journalist writing 60-word news briefs. "
                    "Always write the full summary; no preface, no markdown."
                ),
                max_tokens=420,
                temperature=0.7,
            )

            if (
                not summary
                or self._is_refusal(summary)
                or summary.upper().startswith("SKIP")
            ):
                print("  ⚠ Model refused/skipped summary, using fallback")
                words = content.split()
                return " ".join(words[:60]) + "." if words else title

            words = summary.split()
            if len(words) > 70:
                summary = " ".join(words[:70]) + "."

            if len(words) < 40:
                summary = self._expand_summary_gemini(title, content, summary)

            return summary
        except Exception as e:
            print(f"  ⚠ Summary generation error: {e}, using fallback")
            words = content.split()
            return " ".join(words[:60]) + "." if words else title

    def _expand_summary_gemini(
        self, title: str, content: str, short_summary: str
    ) -> str:
        """If initial summary is too short, expand via NVIDIA / DeepSeek.

        Name retained for backward compatibility. No Gemini dependency.
        """
        prompt = f"""This summary is too short. Expand it to exactly 60 words.

Title: {title}
Original article: {content[:1000]}
Short draft: {short_summary}

Rewrite as a full 60-word music news brief. Count each word. Return only the summary text."""

        try:
            expanded = self._generate_text_response(
                prompt,
                system_prompt="Rewrite to a complete 60-word music news brief. Return only the summary.",
                max_tokens=360,
                temperature=0.6,
            )
            if expanded and len(expanded.split()) >= 40:
                words = expanded.split()
                return " ".join(words[:70]) + (
                    "." if not expanded.rstrip().endswith(".") else ""
                )
        except Exception:
            pass
        return short_summary

    def _fetch_article_text(self, url: str) -> str:
        """Lightly fetch an article URL to get more text when Exa only returned a snippet."""
        try:
            resp = self.session.get(
                url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code != 200:
                return ""
            # Strip HTML tags and return first 1500 chars of body text
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:1500]
        except Exception:
            return ""

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
        """Generate high-converting CTA headline using Perplexity, with Gemini fallback."""
        # Strip source suffixes from original title before rewriting
        clean_title = re.sub(
            r"\s*[|\-–]\s*[A-Z][^|]{3,40}$", "", original_title
        ).strip()
        clean_title = (
            re.sub(r"\s*\([^)]{3,40}\)\s*$", "", clean_title).strip() or clean_title
        )

        if _perplexity_client and not self.perplexity_disabled:
            prompt = f"""Create an engaging, click-worthy headline for this music news story.

Original Title: {clean_title}
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

                if not self._is_refusal(headline):
                    if len(headline) > 100:
                        headline = headline[:97] + "..."
                    return headline
                print("  ⚠ Perplexity refused headline, trying NVIDIA fallback...")
            except Exception as e:
                self._disable_perplexity_if_needed(e, "cta_headline")
                print(
                    f"  ⚠ CTA headline error: {self._trim_error(e)}, trying NVIDIA fallback..."
                )

        # Fallback path: NVIDIA / DeepSeek via _generate_text_response
        return self._generate_cta_headline_gemini(clean_title, content, artist)

    def _generate_cta_headline_gemini(
        self, title: str, content: str, artist: str
    ) -> str:
        """Generate CTA headline via NVIDIA / DeepSeek when Perplexity is unavailable.

        Name retained for backward compatibility. No Gemini dependency.
        """
        prompt = f"""Write a punchy, click-worthy music news headline.

Original: {title}
Artist: {artist or "unknown"}
Context: {content[:400]}

Rules:
- Start with one power word: Breaking / Exclusive / Revealed / Unveiled / Must-See / Inside / Watch
- Keep under 80 characters total
- No source names, no URLs, no quotes around the whole thing
- Return the headline only — no explanation

Headline:"""

        system_prompt = (
            "You are a viral headline writer for a music news app. "
            "Return ONLY one headline, with no explanations."
        )
        headline = self._generate_text_response(
            prompt,
            system_prompt=system_prompt,
            max_tokens=120,
            temperature=0.9,
        )
        if headline and not self._is_refusal(headline):
            return headline[:100]
        return self._transform_title_fallback(title)

    def _transform_title_fallback(self, original_title: str) -> str:
        """Fallback method to transform title without API — strips source names and adds power word."""
        title = original_title
        # Strip trailing " | Source Name" and " - Source Name" patterns
        title = re.sub(r"\s*[|\-–]\s*[A-Z][^|]{3,50}$", "", title).strip()
        title = re.sub(r"\s*\([^)]{3,50}\)\s*$", "", title).strip()
        # Remove publication-style prefixes
        title = re.sub(
            r"^(Premiere:|Exclusive:|Watch:|Listen:|Review:|Interview:)\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = title.strip() or original_title

        # Power words to add
        power_words = [
            "Breaking",
            "Exclusive",
            "Revealed",
            "Unveiled",
            "Must-See",
            "Inside",
        ]
        has_power_word = any(w.lower() in title.lower() for w in power_words)

        if not has_power_word and len(title) < 70:
            import random

            title = f"{random.choice(power_words)}: {title}"

        return title.strip()

    # Music-relevance keywords — at least one must appear for non-RSS articles
    MUSIC_RELEVANCE_KEYWORDS = {
        "music",
        "song",
        "songs",
        "album",
        "albums",
        "artist",
        "artists",
        "band",
        "bands",
        "tour",
        "tours",
        "concert",
        "festival",
        "dj",
        "hip hop",
        "hip-hop",
        "rap",
        "rapper",
        "pop",
        "rock",
        "gospel",
        "electronic",
        "edm",
        "r&b",
        "rnb",
        "singer",
        "vocalist",
        "grammy",
        "billboard",
        "spotify",
        "vinyl",
        "record label",
        "mixtape",
        "ep ",
        "lp ",
        "single",
        "remix",
        "producer",
        "beats",
        "lyrics",
        "verse",
        "chorus",
        "track",
        "tracklist",
        "streaming",
        "playlist",
        "soundcloud",
        "apple music",
        "music video",
        "headliner",
        "genre",
        "indie",
        "punk",
        "metal",
        "jazz",
        "classical",
        "country",
        "reggae",
        "latin",
        "afrobeat",
        "k-pop",
        "idol",
        "boyband",
        "girlband",
    }

    def is_music_relevant(self, title: str, content: str, source_genre: str) -> bool:
        """Gate: reject articles with no music relevance (shared classifier)."""
        try:
            from music_classifier import is_music_relevant as _shared_music
        except ImportError:
            from scraper.music_classifier import is_music_relevant as _shared_music  # type: ignore
        return _shared_music(
            title,
            content or "",
            source_genre=source_genre or "",
            source="",
        )

    def discovery_may_ingest(
        self,
        title: str,
        content: str,
        source_url: str,
        *,
        source: str = "",
        source_genre: str = "discovery",
    ) -> bool:
        """Open-web discovery gate: music classifier + domain allowlist (fail-closed)."""
        try:
            from discovery_allowlist import discovery_may_save
        except ImportError:
            try:
                from scraper.discovery_allowlist import discovery_may_save  # type: ignore
            except ImportError:
                # Fail closed if allowlist module missing
                print("  ⛔ discovery_allowlist unavailable — blocking discovery save")
                return False
        return discovery_may_save(
            title,
            content or "",
            source_url or "",
            source=source,
            source_genre=source_genre,
        )

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
        self.existing_artist_counts.clear()
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
                    # Track artist coverage for saturation check
                    for val in (
                        fields.get("artist_names", {})
                        .get("arrayValue", {})
                        .get("values", [])
                    ):
                        name = val.get("stringValue", "").lower().strip()
                        if name:
                            self.existing_artist_counts[name] = (
                                self.existing_artist_counts.get(name, 0) + 1
                            )

                page_token = data.get("nextPageToken", "")
                if not page_token:
                    break
            except Exception as e:
                print(f"  ⚠ Error warming duplicate index: {e}")
                self._log_event("warm_index_exception", level="warning", error=str(e))
                return

        print(
            f"Loaded duplicate index: {len(self.existing_source_urls)} URLs, "
            f"{len(self.existing_titles)} titles, "
            f"{len(self.existing_artist_counts)} tracked artists"
        )

    def _artist_limit_reached(self, artist_names: List[str]) -> bool:
        """Return True if the primary artist already has MAX_ARTICLES_PER_ARTIST active articles."""
        if not artist_names:
            return False
        primary = artist_names[0].lower().strip()
        return bool(
            primary
            and self.existing_artist_counts.get(primary, 0)
            >= self.MAX_ARTICLES_PER_ARTIST
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

            base_url = f"{FIRESTORE_URL}/articles/{doc_id}"
            payload = {"fields": self.convert_to_firestore_fields(article_dict)}

            sa_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "")
            if sa_b64:
                from google.auth.transport.requests import AuthorizedSession
                from google.oauth2 import service_account

                sa_info = json.loads(base64.b64decode(sa_b64))
                creds = service_account.Credentials.from_service_account_info(
                    sa_info, scopes=["https://www.googleapis.com/auth/datastore"]
                )
                response = AuthorizedSession(creds).patch(
                    base_url, json=payload, timeout=10
                )
            else:
                if not API_KEY:
                    print("  ✗ Failed to save: no Firestore auth (set FIREBASE_SERVICE_ACCOUNT_B64 or FIREBASE_API_KEY)")
                    self._log_event(
                        "save_failed",
                        level="error",
                        reason="missing_firestore_auth",
                        title=article.title,
                    )
                    return False
                response = requests.patch(f"{base_url}?key={API_KEY}", json=payload, timeout=10)

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
                for name in article.artist_names or []:
                    key = name.lower().strip()
                    if key:
                        self.existing_artist_counts[key] = (
                            self.existing_artist_counts.get(key, 0) + 1
                        )
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
                    if sa_b64:
                        compat_resp = AuthorizedSession(creds).patch(base_url, json=compat_payload, timeout=10)
                    else:
                        compat_resp = requests.patch(f"{base_url}?key={API_KEY}", json=compat_payload, timeout=10)
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
                        for name in article.artist_names or []:
                            key = name.lower().strip()
                            if key:
                                self.existing_artist_counts[key] = (
                                    self.existing_artist_counts.get(key, 0) + 1
                                )
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

                if self._artist_limit_reached(artists):
                    print(f"  ⛔ Artist cap reached: {main_artist[:40]}")
                    continue

                # Generate high-CTA headline (not copy-paste)
                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                # Skip if the generated CTA title is already in the feed
                if cta_title.lower().strip() in self.existing_titles:
                    print(f"  ⚠ Duplicate CTA title: {cta_title[:50]}...")
                    continue

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
                    source=source_config.get("display_name") or source_name.replace("_", " ").title(),
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
                    location=item.get("location", ""),
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

    # Each entry: (query, genre_label)
    EXA_QUERIES = [
        ("hip hop rap artist news new album single drop", "hiphop"),
        ("new pop album release review artist announcement", "pop"),
        ("rock alternative indie punk metal band news album", "rock"),
        ("electronic EDM house techno DJ new track festival lineup", "electronic"),
        ("gospel christian worship music artist new release", "gospel"),
    ]

    # Location-focused music news queries — each targets a specific city/region scene
    EXA_LOCATION_QUERIES = [
        (
            "Stockholm Copenhagen Scandinavian music artist new album release",
            "scandinavia",
        ),
        ("Amsterdam Netherlands music scene DJ producer new release", "amsterdam"),
        ("Morocco Moroccan music gnawa fusion artist new release", "morocco"),
        ("New York City NYC music artist new album underground scene release", "nyc"),
        ("Mexico City Mexican music urban Latin artist release", "mexico"),
        ("Medellín Colombia Colombian urban music artist new release", "medellin"),
        ("São Paulo Brazil Brazilian music funk hip hop artist release", "brazil"),
        ("Miami music artist new release Latin urban Florida scene", "miami"),
        ("Dominican Republic dembow bachata merengue artist new release", "caribbean"),
        ("Tokyo Japan J-pop J-rock Japanese hip hop artist release", "tokyo"),
        ("Bali Indonesia Southeast Asian music artist scene release", "bali"),
    ]

    # URL patterns that indicate a list/index page rather than an article
    _EXA_SKIP_URL_PATTERNS = [
        r"^https?://[^/]+/?$",  # bare homepage
        r"/news/?$",
        r"/music/?$",
        r"/articles/?$",  # section index pages
        r"/category/",
        r"/tag/",
        r"/genre/",  # taxonomy pages
        r"/new/?$",
        r"/latest/?$",
        r"/feed/?$",  # feed/listing pages
        r"open\.spotify\.com",
        r"music\.apple\.com",  # streaming platforms
        r"amazon\.com/music",
        r"tidal\.com",
        r"facebook\.com",
        r"instagram\.com",  # social media
        r"twitter\.com",
        r"reddit\.com",
        r"^https?://bit\.ly",
        r"^https?://trib\.al",  # link shorteners
        r"^https?://apple\.co",
        r"^https?://amzn\.",
        r"metacritic\.com/browse",
        r"albumoftheyear\.org/(releases|upcoming|genre)",
        r"popvortex\.com/music/charts",
        r"charts\.apple",
        r"/top-charts",
    ]

    def _discover_perplexity_fallback(self) -> Tuple[int, int]:
        """Fallback discovery using Perplexity when Exa is unavailable."""
        if not _perplexity_client or self.perplexity_disabled:
            print("  ⚠ Perplexity not available for discovery.")
            return 0, 0

        print("\n🔎 Discovering articles via Perplexity...")
        items: List[Dict] = []

        for query, _genre_hint in self.EXA_QUERIES:
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

                if not self.discovery_may_ingest(
                    original_title,
                    content,
                    item.get("link", ""),
                    source="Discovery",
                ):
                    print(f"  ⛔ Discovery rejected: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                if self._artist_limit_reached(artists):
                    print(f"  ⛔ Artist cap reached: {main_artist[:40]}")
                    continue

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                if cta_title.lower().strip() in self.existing_titles:
                    print(f"  ⚠ Duplicate CTA title: {cta_title[:50]}...")
                    continue

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

    def discover_ddgs_articles(self) -> Tuple[int, int]:
        """Discover supplementary music articles via DDGS web search."""
        if not _ddgs_client:
            print("\n⚠ DDGS client unavailable, skipping")
            return 0, 0

        print("\n🔎 Discovering articles via DDGS (supplementary)...")
        items: List[Dict] = []
        seen_urls: Set[str] = set()

        # Keep DDGS broad but bounded; use recent-oriented query phrasing.
        ddgs_queries = list(self.EXA_QUERIES) + list(self.EXA_LOCATION_QUERIES[:6])

        for query, genre_hint in ddgs_queries:
            q = f"{query} latest music news"
            try:
                try:
                    results = list(_ddgs_client.text(q, max_results=8, timelimit="w"))
                except TypeError:
                    # Older ddgs versions may not support timelimit.
                    results = list(_ddgs_client.text(q, max_results=8))

                for r in results:
                    url = (r.get("href") or r.get("url") or "").strip()
                    title = (r.get("title") or "").strip()
                    body = (r.get("body") or r.get("snippet") or "").strip()
                    if not url or not title or not url.startswith("http"):
                        continue
                    normalized = self._normalize_url(url)
                    if normalized in seen_urls:
                        continue
                    if not self._is_article_url(url):
                        continue
                    seen_urls.add(normalized)
                    items.append(
                        {
                            "title": title,
                            "link": url,
                            "description": body[:500],
                            "content": body,
                            "pub_date": "",
                            "image": None,
                            "genre_hint": genre_hint,
                        }
                    )
            except Exception as e:
                print(f"  ? DDGS query error ({query[:40]}...): {e}")

        print(f"  Found {len(items)} DDGS results")
        if not items:
            return 0, 0

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

                if not self.discovery_may_ingest(
                    original_title,
                    content,
                    item.get("link", ""),
                    source="Discovery",
                ):
                    print(f"  ⛔ Discovery rejected: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                if self._artist_limit_reached(artists):
                    continue

                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                if cta_title.lower().strip() in self.existing_titles:
                    continue

                summary = self.summarize_with_gemini(cta_title, content)
                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, item.get("genre_hint", "mixed")
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))
                image_url, image_source = self.resolve_article_image(
                    item,
                    title=cta_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                source_label = self._outlet_name_from_url(item["link"])

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
                print(f"  ? Error processing DDGS item: {e}")
                continue

        print(
            f"  [ddgs_discovery] items={len(items)} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(items)

    def _is_article_url(self, url: str) -> bool:
        """Return False if the URL looks like a homepage, list, or non-article page."""
        for pattern in self._EXA_SKIP_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        # Must have a meaningful path segment (slug) beyond just a domain
        path = urlsplit(url).path.rstrip("/")
        if not path or path.count("/") < 1:
            return False
        return True

    # Known domain → clean outlet name mappings
    _OUTLET_NAMES: Dict[str, str] = {
        "pitchfork.com": "Pitchfork",
        "rollingstone.com": "Rolling Stone",
        "billboard.com": "Billboard",
        "nme.com": "NME",
        "allhiphop.com": "AllHipHop",
        "hotnewhiphop.com": "HotNewHipHop",
        "hiphopdx.com": "HipHopDX",
        "xxlmag.com": "XXL",
        "thefader.com": "The FADER",
        "complex.com": "Complex",
        "rap-up.com": "Rap-Up",
        "okayplayer.com": "OkayPlayer",
        "djmag.com": "DJ Mag",
        "residentadvisor.net": "Resident Advisor",
        "ra.co": "Resident Advisor",
        "edmtunes.com": "EDMTunes",
        "edm.com": "EDM.com",
        "edmidentity.com": "EDM Identity",
        "djbooth.net": "DJBooth",
        "kerrang.com": "Kerrang!",
        "loudwire.com": "Loudwire",
        "altpress.com": "Alternative Press",
        "consequenceofsound.net": "Consequence",
        "consequence.net": "Consequence",
        "stereogum.com": "Stereogum",
        "spin.com": "Spin",
        "npr.org": "NPR Music",
        "theguardian.com": "The Guardian",
        "nytimes.com": "New York Times",
        "variety.com": "Variety",
        "hollywoodreporter.com": "Hollywood Reporter",
        "musicbusinessworldwide.com": "Music Business Worldwide",
        "musicweek.com": "Music Week",
        "thegroove.io": "The Groove",
        "gospel.com": "Gospel.com",
        "gospelflava.com": "GospelFlava",
        "absolutelygospel.com": "Absolutely Gospel",
        "singingnews.com": "Singing News",
        "jesusfreakhideout.com": "JFH",
        "newreleasetoday.com": "New Release Today",
        "rocksound.tv": "Rock Sound",
        "punknews.org": "Punknews",
        "metalinjection.net": "Metal Injection",
        "blabbermouth.net": "Blabbermouth",
        "theprp.com": "The PRP",
        "tmz.com": "TMZ",
        "pagesix.com": "Page Six",
        "hypebeast.com": "Hypebeast",
    }

    def _outlet_name_from_url(self, url: str) -> str:
        """Derive a clean outlet name from the article URL."""
        try:
            host = urlsplit(url).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            # Exact match first
            if host in self._OUTLET_NAMES:
                return self._OUTLET_NAMES[host]
            # Suffix match (e.g. sub.pitchfork.com)
            for domain, name in self._OUTLET_NAMES.items():
                if host.endswith(f".{domain}"):
                    return name
            # Fallback: clean up the domain into a readable name
            # e.g. thehypemagazine.com → The Hype Magazine
            base = host.split(".")[0]
            # CamelCase split and title-case
            base = re.sub(r"([a-z])([A-Z])", r"\1 \2", base)
            base = re.sub(r"[-_]", " ", base)
            return base.title()
        except Exception:
            return "Music News"

    def _discover_brave(self) -> Tuple[int, int]:
        """Discover fresh music news via Brave Search News API."""
        if not BRAVE_API_KEY:
            print("  ⚠ BRAVE_API_KEY not set, skipping Brave discovery")
            return 0, 0

        print("\n🔎 Discovering articles via Brave Search...")
        import urllib.request

        items: List[Dict] = []
        seen_urls: Set[str] = set()

        all_queries = list(self.EXA_QUERIES) + list(self.EXA_LOCATION_QUERIES)

        for query, genre_hint in all_queries:
            try:
                encoded_query = urllib.parse.quote(query)
                url = (
                    f"https://api.search.brave.com/res/v1/news/search"
                    f"?q={encoded_query}&count=5&freshness=pw"
                )
                req = urllib.request.Request(
                    url,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": BRAVE_API_KEY,
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    import gzip as _gzip
                    raw_bytes = resp.read()
                    if resp.info().get("Content-Encoding") == "gzip":
                        raw_bytes = _gzip.decompress(raw_bytes)
                    data = json.loads(raw_bytes.decode("utf-8"))

                for r in data.get("results", []):
                    article_url = (r.get("url") or "").strip()
                    title = (r.get("title") or "").strip()
                    description = (r.get("description") or "").strip()
                    age = r.get("age", "")
                    if not article_url or not title:
                        continue
                    if not article_url.startswith("http"):
                        continue
                    normalized = self._normalize_url(article_url)
                    if normalized in seen_urls:
                        continue
                    if not self._is_article_url(article_url):
                        continue
                    seen_urls.add(normalized)
                    items.append(
                        {
                            "title": title,
                            "link": article_url,
                            "description": description[:500],
                            "content": description,
                            "pub_date": age,
                            "image": None,
                            "genre_hint": genre_hint,
                        }
                    )
            except Exception as e:
                print(f"  ⚠ Brave query error ({query[:40]}...): {e}")
                continue

        print(f"  Found {len(items)} Brave Search discovery results")

        processed = 0
        duplicates = 0
        errors = 0

        for item in items:
            try:
                original_title = item["title"]
                content = item["content"] or item["description"]

                # Skip URL patterns that indicate index/listing pages
                skip = False
                for pat in self._EXA_SKIP_URL_PATTERNS:
                    if re.search(pat, item["link"], re.IGNORECASE):
                        skip = True
                        break
                if skip:
                    continue

                if self.check_duplicate(original_title, item["link"]):
                    duplicates += 1
                    continue

                if not self.discovery_may_ingest(
                    original_title,
                    content,
                    item.get("link", ""),
                    source="Discovery",
                ):
                    print(f"  ⛔ Discovery rejected: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                if self._artist_limit_reached(artists):
                    print(f"  ⛔ Artist cap reached: {main_artist[:40]}")
                    continue

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                if cta_title.lower().strip() in self.existing_titles:
                    print(f"  ⚠ Duplicate CTA title: {cta_title[:50]}...")
                    continue

                summary = self.summarize_with_gemini(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, item.get("genre_hint", "mixed")
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
                    source="Brave Discovery",
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
                print(f"  ✗ Error processing Brave item: {e}")
                continue

        print(
            f"  [brave_discovery] items={len(items)} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(items)

    def _discover_reddit(self) -> Tuple[int, int]:
        """Discover fresh music posts from curated subreddits (Phase C5).

        Thin adapter over reddit_discovery.discover_reddit(): pulls filtered posts,
        runs them through the same dedup / artist-cap / image / save pipeline as
        other discovery paths. Reddit post titles are already curated by the
        community (e.g. [FRESH], [FRESH ALBUM] tags) — we skip the CTA/Gemini
        rewrite pass to preserve that signal.
        """
        try:
            from reddit_discovery import discover_reddit
        except ImportError:
            self._log_event("reddit_import_failed", level="warn")
            return 0, 0

        print("\n🔎 Discovering articles via Reddit...")
        reject_url = lambda u: not self._is_article_url(u)
        reddit_articles = discover_reddit(
            self.session,
            log_fn=self._log_event,
            reject_url_fn=reject_url,
        )

        if not reddit_articles:
            return 0, 0

        print(f"  Found {len(reddit_articles)} Reddit discovery results")

        processed = 0
        duplicates = 0
        errors = 0

        for item in reddit_articles:
            try:
                original_title = item["title"]
                content = item.get("summary") or item.get("title") or ""
                source_url = self._normalize_source_url(item["source_url"])

                if self.check_duplicate(original_title, source_url):
                    duplicates += 1
                    continue

                artists = self.extract_artists(original_title, content)

                if self._artist_limit_reached(artists):
                    continue

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, item.get("genre", "mixed")
                )

                try:
                    published_at = datetime.fromisoformat(
                        item["published_at"].replace("Z", "+00:00")
                    )
                except (KeyError, ValueError, AttributeError):
                    published_at = datetime.now(tz=timezone.utc)

                image_url, image_source = self.resolve_article_image(
                    {"image": None, "link": source_url, "title": original_title},
                    title=original_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                article = Article(
                    id=re.sub(r"[^a-zA-Z0-9]", "-", original_title.lower())[:50],
                    title=original_title,
                    summary=content[:300],
                    full_content=content[:2000],
                    source=item.get("source", "r/unknown"),
                    source_url=source_url,
                    primary_genre=primary_genre,
                    secondary_genres=secondary_genres,
                    artist_names=artists,
                    image_url=image_url,
                    published_at=published_at,
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
                print(f"  ✗ Error processing Reddit item: {e}")
                continue

        print(
            f"  [reddit_discovery] items={len(reddit_articles)} "
            f"saved={processed} duplicates={duplicates} errors={errors}"
        )
        return processed, len(reddit_articles)

    def discover_exa_articles(self) -> Tuple[int, int]:
        """Discover fresh music news via Exa search and process them.
        Falls back to Perplexity-based discovery when Exa is unavailable."""
        if not _exa_client:
            return self._discover_perplexity_fallback()

        print("\n🔎 Discovering articles via Exa...")
        items: List[Dict] = []
        skipped_urls = 0

        # Only look back 72 hours for freshness
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=72)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        for query, genre_hint in self.EXA_QUERIES:
            try:
                result = _exa_client.search(
                    query,
                    type="auto",
                    num_results=8,
                    start_published_date=cutoff,
                    contents={"text": {"max_characters": 3000}},
                )
                for r in result.results:
                    if not r.url or not r.title:
                        continue
                    # Skip index pages by URL pattern OR by missing published_date
                    if not self._is_article_url(r.url) or not getattr(
                        r, "published_date", None
                    ):
                        skipped_urls += 1
                        continue
                    text = re.sub(r"<[^>]+>", "", r.text or "").strip()
                    text = re.sub(r"\s+", " ", text)
                    items.append(
                        {
                            "title": r.title.strip(),
                            "link": r.url,
                            "description": text[:500],
                            "content": text,
                            "pub_date": r.published_date or "",
                            "image": getattr(r, "image", None),
                            "genre_hint": genre_hint,
                        }
                    )
            except Exception as e:
                print(f"  ⚠ Exa query error ({query[:40]}...): {e}")

        # Location-specific music news
        print("  🌍 Running location queries...")
        for query, location_hint in self.EXA_LOCATION_QUERIES:
            try:
                result = _exa_client.search(
                    query,
                    type="auto",
                    num_results=5,
                    start_published_date=cutoff,
                    contents={"text": {"max_characters": 3000}},
                )
                for r in result.results:
                    if not r.url or not r.title:
                        continue
                    if not self._is_article_url(r.url) or not getattr(
                        r, "published_date", None
                    ):
                        skipped_urls += 1
                        continue
                    text = re.sub(r"<[^>]+>", "", r.text or "").strip()
                    text = re.sub(r"\s+", " ", text)
                    items.append(
                        {
                            "title": r.title.strip(),
                            "link": r.url,
                            "description": text[:500],
                            "content": text,
                            "pub_date": r.published_date or "",
                            "image": getattr(r, "image", None),
                            "genre_hint": "mixed",  # Reset genre for location-based articles
                            "location": location_hint,
                        }
                    )
            except Exception as e:
                print(f"  ⚠ Exa location query error ({query[:40]}...): {e}")

        print(
            f"  Found {len(items)} article URLs ({skipped_urls} index/list pages skipped)"
        )

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

                if not self.discovery_may_ingest(
                    original_title,
                    content,
                    item.get("link", ""),
                    source="Discovery",
                ):
                    print(f"  ⛔ Discovery rejected: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                if self._artist_limit_reached(artists):
                    print(f"  ⛔ Artist cap reached: {main_artist[:40]}")
                    continue

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                if cta_title.lower().strip() in self.existing_titles:
                    print(f"  ⚠ Duplicate CTA title: {cta_title[:50]}...")
                    continue

                summary = self.summarize_with_gemini(cta_title, content)

                primary_genre, secondary_genres = self.classify_genre(
                    original_title, content, item.get("genre_hint", "mixed")
                )

                pub_date = self.parse_pub_date(item.get("pub_date", ""))
                image_url, image_source = self.resolve_article_image(
                    item,
                    title=cta_title,
                    artist_names=artists,
                    primary_genre=primary_genre,
                )

                source_label = self._outlet_name_from_url(item["link"])

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

                if not self.discovery_may_ingest(
                    original_title,
                    content,
                    item.get("link", ""),
                    source="Discovery",
                ):
                    print(f"  ⛔ Discovery rejected: {original_title[:60]}...")
                    continue

                artists = self.extract_artists(original_title, content)
                main_artist = artists[0] if artists else ""

                if self._artist_limit_reached(artists):
                    print(f"  ⛔ Artist cap reached: {main_artist[:40]}")
                    continue

                print(f"  📝 Generating CTA headline...")
                cta_title = self.generate_cta_headline(
                    original_title, content, main_artist
                )

                if cta_title.lower().strip() in self.existing_titles:
                    print(f"  ⚠ Duplicate CTA title: {cta_title[:50]}...")
                    continue

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

        if not BRAVE_API_KEY:
            print(
                "⚠️  Warning: BRAVE_API_KEY not set. Brave discovery disabled (Exa removed — credits exhausted)."
            )
            print()

        if not _ddgs_client:
            print("⚠️  Warning: DDGS not available. DDGS discovery disabled.")
            print()

        if librarium_discovery.is_available():
            print("✓ Librarium CLI available for supplementary discovery")
        else:
            print(
                "⚠️  Warning: Librarium CLI not installed. Supplementary discovery disabled."
            )
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

        # 2. Brave Search discovery (primary — replaces Exa)
        try:
            brave_processed, brave_items = self._discover_brave()
            total_processed += brave_processed
            total_fetched_items += brave_items
            source_stats["brave_discovery"] = {
                "saved": brave_processed,
                "items_found": brave_items,
            }
        except Exception as e:
            print(f"  ✗ Error with Brave discovery: {e}")
            self._log_event(
                "source_failed", level="error", source="brave_discovery", error=str(e)
            )

        # 2b. Perplexity fallback discovery
        try:
            perp_processed, perp_items = self._discover_perplexity_fallback()
            total_processed += perp_processed
            total_fetched_items += perp_items
            source_stats["perplexity_discovery"] = {
                "saved": perp_processed,
                "items_found": perp_items,
            }
        except Exception as e:
            print(f"  ✗ Error with Perplexity discovery: {e}")
            self._log_event(
                "source_failed", level="error", source="perplexity_discovery", error=str(e)
            )

        # 2c. Reddit discovery (Phase C5)
        try:
            reddit_processed, reddit_items = self._discover_reddit()
            total_processed += reddit_processed
            total_fetched_items += reddit_items
            source_stats["reddit_discovery"] = {
                "saved": reddit_processed,
                "items_found": reddit_items,
            }
        except Exception as e:
            print(f"  ✗ Error with Reddit discovery: {e}")
            self._log_event(
                "source_failed", level="error", source="reddit_discovery", error=str(e)
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
