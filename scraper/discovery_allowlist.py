"""
Music/indie domain allowlist for open-web discovery writers (phase 1).

Fail-closed: missing or empty list means discovery should not accept new rows.
See scraper/config/music_domain_allowlist.txt
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

DEFAULT_PATH = Path(__file__).resolve().parent / "config" / "music_domain_allowlist.txt"


@lru_cache(maxsize=4)
def load_allowlist(path: Optional[str] = None) -> frozenset[str]:
    p = Path(path or os.environ.get("MUSIC_DOMAIN_ALLOWLIST", str(DEFAULT_PATH)))
    if not p.exists():
        return frozenset()
    hosts = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        hosts.append(line.lstrip("."))
    return frozenset(hosts)


def hostname_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return ""
    return host.lower().removeprefix("www.")


def is_domain_allowed(url: str, *, path: Optional[str] = None) -> bool:
    """True if URL host is on the allowlist (exact or parent suffix match)."""
    allow = load_allowlist(path)
    if not allow:
        return False  # fail-closed
    host = hostname_from_url(url)
    if not host:
        return False
    if host in allow:
        return True
    return any(host.endswith("." + a) for a in allow)


def discovery_may_save(
    title: str,
    content: str,
    source_url: str,
    *,
    source: str = "",
    source_genre: str = "",
) -> bool:
    """Combined music classifier + domain allowlist for discovery writers."""
    from music_classifier import is_music_relevant

    if not is_domain_allowed(source_url):
        return False
    return is_music_relevant(title, content, source_genre=source_genre, source=source)
