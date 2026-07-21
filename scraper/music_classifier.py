"""
Shared music relevance classifier for VEN article cleanup and discovery ingest.

Dual thresholds (see docs/plans/2026-07-21-001-feat-indie-feed-cleanup-plan.md U1):
- mode=delete: high precision — only return non_music when clearly non-music
- mode=ingest: reject non_music; uncertain may be treated as reject by caller

Do not treat source_genre alone as automatic music (legacy is_music_relevant bug).
"""

from __future__ import annotations

from typing import Literal, Optional

Label = Literal["music", "non_music", "uncertain"]
Mode = Literal["delete", "ingest"]

# Strong non-music signals — if present without strong music, prefer non_music.
NON_MUSIC_PHRASES = [
    "earthquake",
    "tsunami",
    "hurricane",
    "medical emergency",
    "blood donation",
    "baseball",
    "basketball",
    "football",
    "soccer",
    "hockey",
    "super regionals",
    "gators demolish",
    "drug trafficking",
    "money laundering",
    "election",
    "political rally",
    "campaign",
    "restaurant review",
    "food guide",
    "travel guide",
    "hotel fire",
    "evacuations",
    "beach hotel",
    "animal cruelty",
    "oregon ducks",
    "tokyo-inspired gear",
    "womans life",
    "woman's life",
]

# Music signals (substring match on lowercased haystack).
MUSIC_KEYWORDS = [
    "music",
    "album",
    "single",
    " ep ",
    "track",
    "song",
    "artist",
    "band",
    "tour",
    "concert",
    "festival",
    "live show",
    "gig",
    " dj ",
    "producer",
    "rapper",
    "singer",
    "guitarist",
    "drummer",
    "label",
    "signing",
    "release",
    "debut",
    "vinyl",
    "streaming",
    "spotify",
    "soundcloud",
    "bandcamp",
    "apple music",
    "tidal",
    "grammy",
    "billboard",
    "chart",
    "playlist",
    "mixtape",
    "venue",
    "setlist",
    "headliner",
    "collaboration",
    "featuring",
    "remix",
    "hip-hop",
    "hiphop",
    "rap ",
    "jazz",
    "electronic",
    "edm",
    "indie",
    "folk",
    "country",
    "gospel",
    "r&b",
    "rnb",
    "soul",
    "metal",
    "punk",
    "classical",
    "k-pop",
    "kpop",
    "reggaeton",
    "coachella",
    "lollapalooza",
    "pitchfork",
    "nme ",
    "under the radar",
]

DISCOVERY_SOURCE_MARKERS = (
    "searxng",
    "brave discovery",
    "ddgs",
    "duckduckgo",
    "perplexity discovery",
    "librarium",
)


def _haystack(title: str, summary: str) -> str:
    return f"{title or ''} {summary or ''}".lower()


def _music_hits(haystack: str) -> int:
    return sum(1 for kw in MUSIC_KEYWORDS if kw in haystack)


def _non_music_hits(haystack: str) -> int:
    return sum(1 for kw in NON_MUSIC_PHRASES if kw in haystack)


def is_discovery_source(source: str) -> bool:
    s = (source or "").lower()
    return any(m in s for m in DISCOVERY_SOURCE_MARKERS)


def classify(
    title: str,
    summary: str = "",
    source: str = "",
    *,
    mode: Mode = "ingest",
    source_genre: Optional[str] = None,
) -> Label:
    """
    Classify an article as music / non_music / uncertain.

    source_genre is ignored for auto-pass (legacy gospel/mixed bypass removed).
    """
    del source_genre  # explicit: no free pass by genre channel
    hay = _haystack(title, summary)
    if not hay.strip():
        return "uncertain"

    m = _music_hits(hay)
    n = _non_music_hits(hay)
    discovery = is_discovery_source(source)

    # Clear non-music: blocklist hits and no solid music signal
    if n >= 1 and m == 0:
        return "non_music"
    if n >= 2 and m <= 1:
        return "non_music"

    # Clear music: multiple music hits, or one strong hit without non-music
    if m >= 2 and n == 0:
        return "music"
    if m >= 1 and n == 0 and not discovery:
        return "music"
    if m >= 1 and n == 0 and discovery:
        # Discovery sources need a bit more signal
        return "music" if m >= 2 else "uncertain"

    if mode == "delete":
        # High precision: only delete when clearly non-music
        if n >= 1 and m == 0:
            return "non_music"
        if discovery and m == 0:
            return "non_music"
        if discovery and n >= 1 and m <= 1:
            return "non_music"
        return "uncertain" if m == 0 else "music"

    # ingest mode: stricter rejection of noise
    if discovery and m == 0:
        return "non_music"
    if m == 0:
        return "non_music"
    if n >= 1 and m <= 1:
        return "non_music"
    return "music" if m >= 1 else "uncertain"


def is_music_relevant(
    title: str,
    content: str = "",
    source_genre: str = "",
    source: str = "",
) -> bool:
    """Drop-in for legacy scraper gate: True if ingest should keep the row."""
    label = classify(
        title,
        content,
        source=source,
        mode="ingest",
        source_genre=source_genre,
    )
    return label == "music"


def is_deletable_non_music(
    title: str,
    summary: str = "",
    source: str = "",
    *,
    curated: bool = False,
) -> bool:
    """True only when hard-delete is allowed (high precision). Curated never auto-delete."""
    if curated:
        return False
    return classify(title, summary, source, mode="delete") == "non_music"
