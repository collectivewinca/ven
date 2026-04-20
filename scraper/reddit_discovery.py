"""Reddit discovery for the y0-minynet scraper pipeline (Phase C5).

Standalone module. Import from rss_scraper.py and call discover_reddit() after
the RSS discovery pass. Returns article-shaped dicts that flow through the same
canonicalization / dedup / entity-extraction / Firestore persistence paths that
RSS articles already use.

Two fetch paths:

1. **OAuth** (preferred, used when REDDIT_CLIENT_ID+REDDIT_CLIENT_SECRET env
   vars are set). Hits `oauth.reddit.com` which is NOT subject to the ASN block
   on `www.reddit.com/*.json` that originally forced this pipeline onto RSS.
   Exposes `score`, `num_comments`, `stickied`, `over_18`, `is_self` — so we
   filter on native fields instead of title-regex heuristics.
2. **RSS** (fallback, for backward compat). Uses Reddit's Atom feeds with the
   existing content-HTML-regex + title-blocklist approach. Active when OAuth
   creds absent or token fetch fails.

Filter strategy (OAuth path):
- Skip stickied, over_18, is_self, hidden.
- Skip if score < _SUB_SCORE_FLOOR[subreddit] (per-sub empirical thresholds,
  since r/Music at 100 pts ≠ r/jazz at 10 pts).
- Skip if external URL is a streaming service / social / reddit-internal
  (same reject_url_fn as RSS path — provided by rss_scraper.py).
- Belt-and-suspenders: still apply TITLE_BLOCKLIST + _TITLE_REJECT_PATTERNS
  from the RSS era for edge cases the stickied flag misses.
"""
from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Callable, Optional

REDDIT_USER_AGENT = "ve-mor-scraper/1.0 (contact hello@collectivewin.ca)"
DEFAULT_TIMEOUT_SECONDS = 15
# RSS fallback: top.rss?t=day — community-validated, naturally noise-filtered.
_DEFAULT_FEED_PATH = "top.rss?t=day&limit=50"

# OAuth: read creds from env so they can be rotated without a code change.
_REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
_REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()

# Per-sub score floor for the OAuth path. Tuned from empirical top-of-day
# distributions captured 2026-04-20. Low-activity subs (jazz, metal) get low
# floors; high-activity subs (Music, popheads) get high floors to cut noise.
# Default _DEFAULT_SCORE_FLOOR is used for any sub not in the map.
_SUB_SCORE_FLOOR = {
    "hiphopheads":    25,
    "indieheads":     20,
    "electronicmusic": 20,
    "popheads":       40,
    "metal":           5,
    "jazz":            5,
    "classicalmusic":  5,
    "rnb":            10,
    "kpop":           20,
    "LatinMusic":      5,
    "listentothis":   10,
    "Music":          75,
}
_DEFAULT_SCORE_FLOOR = 10

REDDIT_SOURCES: dict[str, dict] = {
    "hiphopheads":     {"subreddit": "hiphopheads",     "genre": "hip-hop",    "priority": 2},
    "indieheads":      {"subreddit": "indieheads",      "genre": "indie",      "priority": 2},
    "electronicmusic": {"subreddit": "electronicmusic", "genre": "electronic", "priority": 2},
    "popheads":        {"subreddit": "popheads",        "genre": "pop",        "priority": 2},
    "metal":           {"subreddit": "metal",           "genre": "metal",      "priority": 2},
    "jazz":            {"subreddit": "jazz",            "genre": "jazz",       "priority": 2},
    "classicalmusic":  {"subreddit": "classicalmusic",  "genre": "classical",  "priority": 2},
    "rnb":             {"subreddit": "rnb",             "genre": "r&b",        "priority": 2},
    "kpop":            {"subreddit": "kpop",            "genre": "k-pop",      "priority": 2},
    "LatinMusic":      {"subreddit": "LatinMusic",      "genre": "latin",      "priority": 2},
    "listentothis":    {"subreddit": "listentothis",    "genre": "mixed",      "priority": 2},
    "Music":           {"subreddit": "Music",           "genre": "mixed",      "priority": 2},
}

# Ported from the dead reddit_scraper.py, plus a few additions caught in dry-runs.
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
    "megathread",
    "fresh album friday",
    "new music friday discussion",
    "top ten tuesday",
}

_TITLE_REJECT_PATTERNS = [
    re.compile(r"^\s*meta:?\s", re.I),
    re.compile(r"\brules\b.*\bupdate\b", re.I),
    re.compile(r"^\s*\[mod\]", re.I),
    re.compile(r"\bmegathread\b", re.I),
    re.compile(r"\bdaily discussion\b", re.I),
    re.compile(r"\btop ten tuesday\b", re.I),
]

_DISCUSSION_THREAD_SUBSTRINGS = (
    "daily discussion thread",
    "weekly discussion thread",
    "monthly discussion thread",
)

# Baseline URL-reject patterns. rss_scraper.py's full filter is more comprehensive —
# pass it in via `reject_url_fn` for production. This default is used by the CLI
# smoke test so running the module directly shows what production would ingest.
_DEFAULT_URL_REJECT_PATTERNS = [
    re.compile(r"^https?://(open\.|play\.|)spotify\.com/", re.I),
    re.compile(r"^https?://music\.apple\.com/", re.I),
    re.compile(r"^https?://(www\.)?tidal\.com/", re.I),
    re.compile(r"^https?://(www\.)?deezer\.com/", re.I),
    re.compile(r"^https?://(www\.)?instagram\.com/", re.I),
    re.compile(r"^https?://(www\.)?tiktok\.com/", re.I),
    re.compile(r"^https?://(www\.|m\.)?facebook\.com/", re.I),
    re.compile(r"^https?://(www\.|mobile\.)?twitter\.com/", re.I),
    re.compile(r"^https?://(www\.)?x\.com/", re.I),
    re.compile(r"^https?://(bit\.ly|tinyurl\.com|t\.co|ow\.ly|buff\.ly)/", re.I),
    re.compile(r"^https?://(www\.)?reddit\.com/r/", re.I),
    re.compile(r"^https?://i\.redd\.it/", re.I),
    re.compile(r"^https?://v\.redd\.it/", re.I),
]


def _default_url_rejects(url: str) -> bool:
    return any(p.match(url) for p in _DEFAULT_URL_REJECT_PATTERNS)


def _reject_title(title: str) -> bool:
    if not title:
        return True
    t = title.strip().lower()
    if t in TITLE_BLOCKLIST:
        return True
    if any(s in t for s in _DISCUSSION_THREAD_SUBSTRINGS):
        return True
    for pat in _TITLE_REJECT_PATTERNS:
        if pat.search(title):
            return True
    return False


# ---------------------------------------------------------------------------
# OAuth path (preferred) — uses oauth.reddit.com, returns native JSON
# ---------------------------------------------------------------------------

def _get_oauth_token(session, log_fn=None) -> Optional[str]:
    """Exchange client_id+client_secret for a bearer token via client_credentials.

    Returns None if creds missing or token request fails; caller should fall
    back to RSS.
    """
    if not (_REDDIT_CLIENT_ID and _REDDIT_CLIENT_SECRET):
        return None
    try:
        resp = session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(_REDDIT_CLIENT_ID, _REDDIT_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            if log_fn:
                log_fn("reddit_oauth_token_failed", status=resp.status_code)
            return None
        return resp.json().get("access_token")
    except Exception as e:
        if log_fn:
            log_fn("reddit_oauth_token_error", err=str(e))
        return None


def _fetch_oauth(session, token: str, subreddit: str,
                 time_filter: str = "day", limit: int = 50) -> list[dict]:
    """Fetch top posts for one subreddit via oauth.reddit.com. Returns the
    `data.children` list from Reddit's JSON response (empty list on error)."""
    url = f"https://oauth.reddit.com/r/{subreddit}/top"
    params = {"t": time_filter, "limit": limit, "raw_json": 1}
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": REDDIT_USER_AGENT,
    }
    resp = session.get(url, headers=headers, params=params,
                       timeout=DEFAULT_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("children", [])


def _normalize_oauth(post: dict, source_key: str, cfg: dict,
                     reject_url_fn: Optional[Callable[[str], bool]]) -> Optional[dict]:
    """Convert one OAuth post dict into the article shape the pipeline expects.

    Returns None to skip. Filters:
      - stickied / over_18 / is_self / hidden
      - score below per-sub floor
      - title matches legacy reject patterns (belt-and-suspenders)
      - external URL missing or rejected by reject_url_fn
    """
    d = post.get("data") or {}

    if d.get("stickied") or d.get("over_18") or d.get("is_self") or d.get("hidden"):
        return None

    score = int(d.get("score") or 0)
    floor = _SUB_SCORE_FLOOR.get(source_key, _DEFAULT_SCORE_FLOOR)
    if score < floor:
        return None

    title = (d.get("title") or "").strip()
    if _reject_title(title):
        return None

    external_url = (d.get("url") or "").strip()
    if not external_url:
        return None
    if reject_url_fn is not None and reject_url_fn(external_url):
        return None

    permalink = d.get("permalink") or ""
    full_permalink = f"https://www.reddit.com{permalink}" if permalink else None

    body = (d.get("selftext") or "").strip()
    summary = (body[:500] if body else title) or title

    created_utc = d.get("created_utc")
    if created_utc:
        try:
            published_iso = datetime.fromtimestamp(
                float(created_utc), tz=timezone.utc
            ).isoformat().replace("+00:00", "Z")
        except (ValueError, OSError, OverflowError):
            published_iso = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        published_iso = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")

    thumb = d.get("thumbnail") or ""
    image_url = thumb if thumb.startswith("http") else None

    return {
        "title": title,
        "summary": summary,
        "source_url": external_url,
        "source": f"r/{source_key}",
        "genre": cfg.get("genre", "mixed"),
        "published_at": published_iso,
        "image_url": image_url,
        "reddit_permalink": full_permalink,
        "reddit_post_id": d.get("id"),
        "reddit_author": d.get("author"),
        "reddit_score": score,
        "reddit_num_comments": int(d.get("num_comments") or 0),
        "share_count": 0,
        "email_count": 0,
        "bookmark_count": 0,
        "view_count": 0,
    }


def _discover_reddit_oauth(session, token: str, sources: dict,
                           reject_url_fn, log_fn) -> list[dict]:
    out: list[dict] = []
    for source_key, cfg in sources.items():
        subreddit = cfg.get("subreddit", source_key)
        try:
            posts = _fetch_oauth(session, token, subreddit)
        except Exception as e:
            if log_fn:
                log_fn("reddit_fetch_error", subreddit=source_key,
                       err=str(e), mode="oauth")
            continue

        kept = 0
        for post in posts:
            article = _normalize_oauth(post, source_key, cfg, reject_url_fn)
            if article is not None:
                out.append(article)
                kept += 1

        if log_fn:
            log_fn("reddit_subreddit_summary", subreddit=source_key,
                   fetched=len(posts), kept=kept, mode="oauth")
    return out


# ---------------------------------------------------------------------------
# RSS path (fallback) — unchanged from Phase C5 original
# ---------------------------------------------------------------------------

_ATOM_NS = "{http://www.w3.org/2005/Atom}"

# Extract the first external link from an Atom entry's <content> HTML. The
# entry's top-level <link href> points to the Reddit comment thread, not the
# submission's external target. The HTML-encoded <content> contains an anchor
# like <a href="https://...">[link]</a> pointing at the external URL.
_CONTENT_EXT_LINK = re.compile(
    r'<a\s+href="(https?://[^"]+)"[^>]*>\s*\[link\]', re.I
)

# Fallback: any https URL that isn't reddit.com internal. Used if the [link]
# anchor isn't present (e.g. some self-posts include a single external URL in
# the body even though they're flagged as self).
_CONTENT_ANY_HTTPS = re.compile(r'href="(https?://(?!www\.reddit\.com|old\.reddit\.com|reddit\.com)[^"]+)"', re.I)


def _extract_external_url(content_html: str) -> Optional[str]:
    if not content_html:
        return None
    m = _CONTENT_EXT_LINK.search(content_html)
    if m:
        return m.group(1).strip()
    return None


def _strip_html(s: str) -> str:
    """Very light HTML → text. Enough for the summary field."""
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&#32;", " ").replace("&#39;", "'").replace("&quot;", '"')
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_feed(xml_bytes: bytes) -> list[dict]:
    """Parse an Atom feed into a list of entry dicts. Never raises on malformed
    — returns [] on parse error."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out: list[dict] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        title_el = entry.find(f"{_ATOM_NS}title")
        content_el = entry.find(f"{_ATOM_NS}content")
        link_el = entry.find(f"{_ATOM_NS}link")
        published_el = entry.find(f"{_ATOM_NS}published")
        author_el = entry.find(f"{_ATOM_NS}author/{_ATOM_NS}name")
        id_el = entry.find(f"{_ATOM_NS}id")

        out.append({
            "title": (title_el.text or "").strip() if title_el is not None else "",
            "content_html": content_el.text or "" if content_el is not None else "",
            "reddit_permalink": (link_el.get("href") if link_el is not None else None),
            "published": (published_el.text or "").strip() if published_el is not None else "",
            "author": (author_el.text or "").strip() if author_el is not None else "",
            "reddit_post_id": (id_el.text or "").strip() if id_el is not None else "",
        })
    return out


def _normalize_published(ts: str) -> str:
    if not ts:
        return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        return (datetime.fromisoformat(ts.replace("Z", "+00:00"))
                .astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
    except ValueError:
        return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize(
    entry: dict,
    source_key: str,
    cfg: dict,
    reject_url_fn: Optional[Callable[[str], bool]],
) -> Optional[dict]:
    """Filter + shape one Atom entry into an article-shaped dict. None to skip."""
    try:
        title = entry.get("title", "").strip()
        if _reject_title(title):
            return None

        external_url = _extract_external_url(entry.get("content_html", ""))
        if not external_url:
            return None

        if reject_url_fn is not None and reject_url_fn(external_url):
            return None

        body = _strip_html(entry.get("content_html", ""))
        body = re.sub(r"submitted by.*?(\[link\])?.*?(\[comments\])?.*$", "", body, flags=re.I | re.S).strip()
        summary = (body[:500] if body else title).strip() or title

        return {
            "title": title,
            "summary": summary,
            "source_url": external_url,
            "source": f"r/{source_key}",
            "genre": cfg.get("genre", "mixed"),
            "published_at": _normalize_published(entry.get("published", "")),
            "image_url": None,
            "reddit_permalink": entry.get("reddit_permalink"),
            "reddit_post_id": entry.get("reddit_post_id"),
            "reddit_author": entry.get("author"),
            "share_count": 0,
            "email_count": 0,
            "bookmark_count": 0,
            "view_count": 0,
        }
    except (ValueError, TypeError, KeyError):
        return None


def _discover_reddit_rss(session, sources: dict, reject_url_fn, log_fn,
                         feed_path: str) -> list[dict]:
    out: list[dict] = []
    headers = {"User-Agent": REDDIT_USER_AGENT}

    for source_key, cfg in sources.items():
        subreddit = cfg.get("subreddit", source_key)
        url = f"https://www.reddit.com/r/{subreddit}/{feed_path}"
        try:
            resp = session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT_SECONDS)
        except Exception as e:
            if log_fn:
                log_fn("reddit_fetch_error", subreddit=source_key, err=str(e), mode="rss")
            continue

        if resp.status_code != 200:
            if log_fn:
                log_fn("reddit_fetch_failed", subreddit=source_key,
                       status=resp.status_code, mode="rss")
            continue

        entries = _parse_feed(resp.content)
        if not entries and log_fn:
            log_fn("reddit_empty_feed", subreddit=source_key, mode="rss")

        kept = 0
        for entry in entries:
            article = _normalize(entry, source_key, cfg, reject_url_fn)
            if article is not None:
                out.append(article)
                kept += 1

        if log_fn:
            log_fn("reddit_subreddit_summary",
                   subreddit=source_key, fetched=len(entries), kept=kept, mode="rss")
    return out


# ---------------------------------------------------------------------------
# Public entry point — OAuth-first, RSS fallback
# ---------------------------------------------------------------------------

def discover_reddit(
    session,
    log_fn: Optional[Callable] = None,
    reject_url_fn: Optional[Callable[[str], bool]] = None,
    sources: Optional[dict] = None,
    feed_path: str = _DEFAULT_FEED_PATH,
) -> list[dict]:
    """Fetch, filter, normalize Reddit posts across configured subreddits.

    Routing: if REDDIT_CLIENT_ID+REDDIT_CLIENT_SECRET are set in env and the
    token exchange succeeds, uses oauth.reddit.com. Otherwise falls back to
    the RSS path (original behaviour, still works from cloud VMs).

    Parameters unchanged from original — `feed_path` only applies to RSS
    fallback; OAuth path uses `/top?t=day&limit=50`.
    """
    sources = sources if sources is not None else REDDIT_SOURCES
    token = _get_oauth_token(session, log_fn=log_fn)

    if token:
        if log_fn:
            log_fn("reddit_mode", mode="oauth")
        out = _discover_reddit_oauth(session, token, sources, reject_url_fn, log_fn)
    else:
        if log_fn:
            log_fn("reddit_mode", mode="rss",
                   reason="no_oauth_creds" if not _REDDIT_CLIENT_ID
                          else "token_exchange_failed")
        out = _discover_reddit_rss(session, sources, reject_url_fn, log_fn, feed_path)

    if log_fn:
        log_fn("reddit_discovery_summary",
               total_kept=len(out), subreddits=len(sources),
               mode="oauth" if token else "rss")
    return out


# ---------------------------------------------------------------------------
# CLI smoke test
#   python3 reddit_discovery.py                # 2 subs, auto-select OAuth/RSS
#   python3 reddit_discovery.py hiphopheads    # one sub
#   python3 reddit_discovery.py --new          # force RSS new.rss path
#   python3 reddit_discovery.py --rss          # force RSS even if OAuth creds set
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import requests

    argv = sys.argv[1:]
    feed = _DEFAULT_FEED_PATH
    force_rss = False
    if "--new" in argv:
        argv.remove("--new")
        feed = "new.rss?limit=50"
        force_rss = True
    if "--rss" in argv:
        argv.remove("--rss")
        force_rss = True

    if force_rss:
        # Clear creds in this process so the OAuth branch doesn't trigger
        _REDDIT_CLIENT_ID = ""
        _REDDIT_CLIENT_SECRET = ""

    sess = requests.Session()
    subs_arg = argv or list(REDDIT_SOURCES.keys())[:2]
    smoke_sources = {k: REDDIT_SOURCES[k] for k in subs_arg if k in REDDIT_SOURCES}

    def _log(event: str, **kw):
        print(f"[{event}] {kw}", file=sys.stderr)

    results = discover_reddit(sess, log_fn=_log,
                              reject_url_fn=_default_url_rejects,
                              sources=smoke_sources,
                              feed_path=feed)
    for r in results[:3]:
        print(json.dumps(r, indent=2, default=str))
    print(f"\nTotal articles returned: {len(results)}", file=sys.stderr)
