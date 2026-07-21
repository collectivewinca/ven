"""Unit tests for scraper/music_classifier.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from music_classifier import (  # noqa: E402
    classify,
    is_deletable_non_music,
    is_music_relevant,
)


def test_music_album_is_music():
    assert classify("Sleater-Kinney announce new album tour", "Indie rock legends") == "music"
    assert is_music_relevant("Sleater-Kinney announce new album tour", "Indie rock legends")


def test_hotel_fire_is_non_music():
    label = classify(
        "Breaking: Dominican Republic Beach Hotel Fire Claims Woman's Life",
        "Forces 1,700 Evacuations",
        "SearXNG Discovery",
        mode="delete",
    )
    assert label == "non_music"
    assert is_deletable_non_music(
        "Breaking: Dominican Republic Beach Hotel Fire Claims Woman's Life",
        "Forces 1,700 Evacuations",
        "SearXNG Discovery",
    )


def test_animal_cruelty_discovery_delete():
    assert (
        classify(
            "World's First Summit Targets Animal Cruelty Online Content",
            "",
            "SearXNG Discovery",
            mode="delete",
        )
        == "non_music"
    )


def test_apple_music_pricing_kept_as_music():
    # music product / industry — should not hard-delete
    label = classify(
        "Apple Music Prices Going Up",
        "Streaming subscription costs rise",
        "NME",
        mode="delete",
    )
    assert label in ("music", "uncertain")
    assert not is_deletable_non_music(
        "Apple Music Prices Going Up",
        "Streaming subscription costs rise",
        "NME",
    )


def test_curated_never_auto_delete():
    assert not is_deletable_non_music(
        "Random non music hotel fire",
        "evacuations",
        "SearXNG Discovery",
        curated=True,
    )


def test_gospel_source_genre_no_free_pass():
    # Legacy bug: gospel/mixed always True — must still inspect content
    assert not is_music_relevant(
        "Local election results",
        "Candidates win primary",
        source_genre="gospel",
        source="Random",
    )


def test_discovery_needs_stronger_signal_for_music():
    # single weak hit on discovery → uncertain/non for ingest
    label = classify("Team announce return", "", "Brave Discovery", mode="ingest")
    assert label in ("non_music", "uncertain")
