"""Unit tests for archive selection + allowlist (no live PB required)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archive_articles import selection_reason  # noqa: E402
from discovery_allowlist import is_domain_allowed, load_allowlist  # noqa: E402
from music_classifier import is_deletable_non_music  # noqa: E402


class TestSelection(unittest.TestCase):
    def test_hotel_fire_selected(self):
        rec = {
            "id": "x1",
            "title": "Breaking: Dominican Republic Beach Hotel Fire Claims Woman's Life",
            "summary": "Forces 1,700 Evacuations",
            "source": "SearXNG Discovery",
            "curated": False,
        }
        reason = selection_reason(rec)
        self.assertIsNotNone(reason)
        self.assertTrue(reason.startswith("delete:"))

    def test_music_album_not_selected(self):
        rec = {
            "id": "x2",
            "title": "Sleater-Kinney announce new album and tour",
            "summary": "Indie rock band releases LP",
            "source": "Pitchfork News",
            "curated": False,
        }
        self.assertIsNone(selection_reason(rec))

    def test_curated_non_music_holdback(self):
        rec = {
            "id": "x3",
            "title": "Hotel fire forces evacuations",
            "summary": "Beach hotel fire",
            "source": "SearXNG Discovery",
            "curated": True,
        }
        reason = selection_reason(rec)
        self.assertEqual(reason, "curated_holdback_non_music")
        self.assertFalse(
            is_deletable_non_music(
                rec["title"], rec["summary"], rec["source"], curated=True
            )
        )


class TestAllowlist(unittest.TestCase):
    def test_seed_loaded(self):
        self.assertGreater(len(load_allowlist()), 10)

    def test_pitchfork_ok_cnn_blocked(self):
        self.assertTrue(is_domain_allowed("https://pitchfork.com/news/foo"))
        self.assertFalse(is_domain_allowed("https://cnn.com/world/foo"))


class TestArchiveManifestRoundtrip(unittest.TestCase):
    def test_jsonl_sha_stable(self):
        import hashlib

        rows = [
            {
                "archived_at": "t",
                "reason": "delete:non_music",
                "record": {"id": "a1", "title": "Hotel fire", "source": "SearXNG Discovery"},
            }
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "articles.jsonl"
            h = hashlib.sha256()
            with p.open("w", encoding="utf-8") as fh:
                for r in rows:
                    line = json.dumps(r, ensure_ascii=False) + "\n"
                    fh.write(line)
                    h.update(line.encode("utf-8"))
            digest = h.hexdigest()
            # re-read
            h2 = hashlib.sha256()
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024), b""):
                    h2.update(chunk)
            self.assertEqual(digest, h2.hexdigest())


if __name__ == "__main__":
    unittest.main()
