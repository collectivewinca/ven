import unittest
from datetime import datetime, timezone

from reddit_scraper import RedditScraper
from rss_scraper import Article, RSSScraper


class TestRSSScraperReliabilityHelpers(unittest.TestCase):
    def setUp(self):
        self.scraper = RSSScraper()

    def test_normalize_source_url_upgrades_http(self):
        self.assertEqual(
            self.scraper._normalize_source_url("http://example.com/news?id=1"),
            "https://example.com/news?id=1",
        )

    def test_normalize_source_url_keeps_https(self):
        self.assertEqual(
            self.scraper._normalize_source_url("https://example.com/news"),
            "https://example.com/news",
        )

    def test_build_doc_id_is_deterministic(self):
        article = Article(
            id="a",
            title="Breaking: Artist Drops New Album",
            summary="summary",
            full_content="content",
            source="Pitchfork News",
            source_url="https://example.com/story",
            primary_genre="pop",
            secondary_genres=[],
            artist_names=["Artist"],
            image_url=None,
            published_at=datetime(2026, 2, 17, 12, 0, 0, tzinfo=timezone.utc),
            read_time=60,
            share_count=0,
            email_count=0,
            bookmark_count=0,
            view_count=0,
            fetched_at=datetime(2026, 2, 17, 12, 5, 0, tzinfo=timezone.utc),
        )
        first = self.scraper._build_doc_id(article)
        second = self.scraper._build_doc_id(article)
        self.assertEqual(first, second)

    def test_build_doc_id_changes_with_source_url(self):
        base = Article(
            id="a",
            title="Breaking: Artist Drops New Album",
            summary="summary",
            full_content="content",
            source="Pitchfork News",
            source_url="https://example.com/story-a",
            primary_genre="pop",
            secondary_genres=[],
            artist_names=["Artist"],
            image_url=None,
            published_at=datetime(2026, 2, 17, 12, 0, 0, tzinfo=timezone.utc),
            read_time=60,
            share_count=0,
            email_count=0,
            bookmark_count=0,
            view_count=0,
            fetched_at=datetime(2026, 2, 17, 12, 5, 0, tzinfo=timezone.utc),
        )
        changed = Article(
            **{
                **base.__dict__,
                "source_url": "https://example.com/story-b",
            }
        )
        self.assertNotEqual(
            self.scraper._build_doc_id(base),
            self.scraper._build_doc_id(changed),
        )


class TestRedditScraperReliabilityHelpers(unittest.TestCase):
    def setUp(self):
        self.scraper = RedditScraper()

    def test_normalize_https_url_upgrades_http(self):
        self.assertEqual(
            self.scraper._normalize_https_url("http://reddit.com/r/music"),
            "https://reddit.com/r/music",
        )

    def test_normalize_https_url_keeps_https(self):
        self.assertEqual(
            self.scraper._normalize_https_url("https://reddit.com/r/music"),
            "https://reddit.com/r/music",
        )

    def test_build_doc_id_is_deterministic(self):
        first = self.scraper._build_doc_id(
            "Reddit Trending: Artist",
            "https://reddit.com/post/1",
            "2026-02-17T12:00:00Z",
        )
        second = self.scraper._build_doc_id(
            "Reddit Trending: Artist",
            "https://reddit.com/post/1",
            "2026-02-17T12:00:00Z",
        )
        self.assertEqual(first, second)

    def test_build_doc_id_changes_when_published_changes(self):
        first = self.scraper._build_doc_id(
            "Reddit Trending: Artist",
            "https://reddit.com/post/1",
            "2026-02-17T12:00:00Z",
        )
        second = self.scraper._build_doc_id(
            "Reddit Trending: Artist",
            "https://reddit.com/post/1",
            "2026-02-17T12:01:00Z",
        )
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
