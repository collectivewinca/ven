#!/usr/bin/env python3
"""
Reddit Artist Discovery Demo
Shows what artists would be discovered without Firebase save
"""

import subprocess
import re
import json
from datetime import datetime
from typing import List, Dict, Any, Set


def discover_artists_from_reddit():
    """Discover trending artists from Reddit music subreddits"""
    print("🎵 Reddit Artist Discovery Demo")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Music subreddits to check
    subreddits = ["hiphopheads", "Music", "indieheads", "popheads", "electronicmusic"]

    all_discoveries = []

    for subreddit in subreddits:
        print(f"🔍 Scanning r/{subreddit}...")

        try:
            # Run hf CLI command
            result = subprocess.run(
                ["hf", "reddit", "-t", subreddit],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"  ⚠ Error: {result.stderr[:100]}")
                continue

            # Parse posts
            posts = parse_hf_output(result.stdout, subreddit)
            print(f"  📊 Found {len(posts)} posts")

            # Extract artists
            artists = extract_artists_from_posts(posts, subreddit)
            print(f"  🎤 Discovered {len(artists)} artists")

            # Show top artists
            for i, artist in enumerate(artists[:5], 1):
                print(f"    {i}. {artist['name']} ({artist['votes']} votes)")
                if artist.get("release_type"):
                    print(f"       Release: {artist['release_type']}")

            all_discoveries.extend(artists)

        except Exception as e:
            print(f"  ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("📈 DISCOVERY SUMMARY")
    print("=" * 60)

    # Group by genre/subreddit
    by_subreddit = {}
    for artist in all_discoveries:
        sub = artist["subreddit"]
        if sub not in by_subreddit:
            by_subreddit[sub] = []
        by_subreddit[sub].append(artist)

    for subreddit, artists in by_subreddit.items():
        print(f"\n🎵 r/{subreddit} ({len(artists)} artists):")
        artists_sorted = sorted(artists, key=lambda x: x["votes"], reverse=True)
        for artist in artists_sorted[:10]:
            release_info = (
                f" - {artist.get('release_type', 'trending')}"
                if artist.get("release_type")
                else ""
            )
            print(f"  • {artist['name']} ({artist['votes']} votes{release_info})")

    # Top 10 overall
    print("\n🏆 TOP 10 TRENDING ARTISTS OVERALL:")
    print("-" * 40)
    all_sorted = sorted(all_discoveries, key=lambda x: x["votes"], reverse=True)
    for i, artist in enumerate(all_sorted[:10], 1):
        sub = artist["subreddit"]
        release = artist.get("release_type", "trending")
        print(
            f"{i:2}. {artist['name']:30} {artist['votes']:5} votes (r/{sub}, {release})"
        )

    # Generate article examples
    print("\n" + "=" * 60)
    print("📝 EXAMPLE MINY-VEN ARTICLES")
    print("=" * 60)

    for i, artist in enumerate(all_sorted[:5], 1):
        print(f"\n{i}. Reddit Trending: {artist['name']}")
        print(f"   Genre: {artist.get('genre', 'mixed')}")
        print(f"   Source: r/{artist['subreddit']}")
        print(f"   Summary: {generate_summary(artist)}")
        print(f"   Link: {artist.get('url', 'https://reddit.com')}")

    print(f"\n🎉 Total artists discovered: {len(all_discoveries)}")
    print(f"📅 Next steps: Configure Firebase permissions to save these articles")


def parse_hf_output(output: str, subreddit: str) -> List[Dict[str, Any]]:
    """Parse hf CLI output"""
    posts = []
    current_post = {}
    in_content = False
    content_lines = []

    for line in output.strip().split("\n"):
        line = line.strip()

        if line.startswith("Title :"):
            if current_post:
                current_post["content"] = "\n".join(content_lines).strip()
                posts.append(current_post.copy())

            current_post = {"title": line.replace("Title :", "").strip()}
            content_lines = []
            in_content = False

        elif line.startswith("Link :"):
            current_post["url"] = line.replace("Link :", "").strip()
        elif line.startswith("Comment:"):
            parts = line.replace("Comment:", "").strip().split("|")
            if len(parts) >= 2:
                current_post["comments"] = int(parts[0].strip())
                votes_part = parts[1].replace("Votes:", "").strip()
                current_post["votes"] = int(votes_part) if votes_part.isdigit() else 0
        elif line.startswith("Content :"):
            in_content = True
            content_text = line.replace("Content :", "").strip()
            if content_text:
                content_lines.append(content_text)
        elif in_content and line and not line.startswith("---"):
            content_lines.append(line)

    # Add last post
    if current_post:
        current_post["content"] = "\n".join(content_lines).strip()
        posts.append(current_post)

    return posts


def extract_artists_from_posts(
    posts: List[Dict[str, Any]], subreddit: str
) -> List[Dict[str, Any]]:
    """Extract artist information from posts"""
    artists = []
    seen_names = set()

    # Map subreddits to genres
    genre_map = {
        "hiphopheads": "hiphop",
        "Music": "mixed",
        "indieheads": "rock",
        "popheads": "pop",
        "electronicmusic": "electronic",
        "gospelmusic": "gospel",
        "rock": "rock",
    }

    for post in posts:
        title = post.get("title", "")
        votes = post.get("votes", 0)

        # Skip low-vote posts
        if votes < 10:
            continue

        # Extract artist
        artist_info = extract_artist_from_title(title)
        if not artist_info:
            continue

        artist_name, release_type = artist_info

        # Skip if already seen
        if artist_name.lower() in seen_names:
            continue

        seen_names.add(artist_name.lower())

        artist = {
            "name": artist_name,
            "subreddit": subreddit,
            "genre": genre_map.get(subreddit, "mixed"),
            "votes": votes,
            "comments": post.get("comments", 0),
            "url": post.get("url", ""),
            "release_type": release_type,
            "source_title": title[:80] + "..." if len(title) > 80 else title,
            "discovered_at": datetime.now().isoformat(),
        }

        artists.append(artist)

    return artists


def extract_artist_from_title(title: str):
    """Extract artist name and release type from title"""
    # Clean title
    clean_title = title

    # Check for release types
    release_type = None
    release_patterns = [
        (r"\[FRESH\s+ALBUM\]", "new album"),
        (r"\[FRESH\s+EP\]", "new EP"),
        (r"\[FRESH\s+VIDEO\]", "new video"),
        (r"\[FRESH\s+SINGLE\]", "new single"),
        (r"\[FRESH\s+TRACK\]", "new track"),
        (r"\[FRESH\]", "new release"),
        (r"\[DISCUSSION\]", "discussion"),
        (r"\[ALBUM\]", "album"),
        (r"\[EP\]", "EP"),
    ]

    for pattern, rtype in release_patterns:
        if re.search(pattern, clean_title, re.IGNORECASE):
            release_type = rtype
            clean_title = re.sub(pattern, "", clean_title, flags=re.IGNORECASE)
            break

    # Try to extract artist name (text before first dash)
    if " - " in clean_title:
        parts = clean_title.split(" - ", 1)
        artist = parts[0].strip()

        # Clean up brackets and common prefixes
        artist = re.sub(r"^\s*\[.*?\]\s*", "", artist)
        artist = re.sub(r"\s*\(.*?\)\s*$", "", artist)

        if artist and len(artist) > 1:
            return artist, release_type

    # Try other patterns
    patterns = [
        r"([A-Z][a-zA-Z\s&]+)\s+drops?\s+(?:new|latest)",
        r"([A-Z][a-zA-Z\s&]+)\s+announces?\s+(?:new|upcoming)",
        r"([A-Z][a-zA-Z\s&]+)\s+releases?\s+(?:new|latest)",
    ]

    for pattern in patterns:
        match = re.search(pattern, clean_title, re.IGNORECASE)
        if match:
            artist = match.group(1).strip()
            if artist and len(artist) > 1:
                return artist, release_type or "announcement"

    return None


def generate_summary(artist: Dict[str, Any]) -> str:
    """Generate a 60-word summary for miny-ven article"""
    name = artist["name"]
    subreddit = artist["subreddit"]
    votes = artist["votes"]
    release_type = artist.get("release_type", "trending")

    if release_type != "trending":
        summary = f"{name} is making waves on r/{subreddit} with {votes} votes. The community is buzzing about their {release_type}. Fans are sharing reactions and discussing what this means for the artist's career. Check out the Reddit thread to join the conversation and see what makes this release special."
    else:
        summary = f"{name} is trending on r/{subreddit} with {votes} votes. The music community is actively discussing their work, sharing insights, and debating their impact. Whether it's new releases, career moves, or industry news, Reddit users are engaged. See what the buzz is about and join the discussion."

    # Trim to ~60 words
    words = summary.split()
    if len(words) > 60:
        summary = " ".join(words[:60]) + "..."

    return summary


if __name__ == "__main__":
    discover_artists_from_reddit()
