#!/usr/bin/env python3
"""
Generate dynamic trends HTML from fetched Reddit data
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path


def parse_reddit_file(filepath):
    """Parse Reddit data from hf CLI output format"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse the structured format
    posts = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for title lines
        if line.startswith("Title :"):
            title = line.replace("Title :", "").strip()
            post = {"title": title}

            # Look for next lines
            j = i + 1
            while (
                j < len(lines)
                and not lines[j].strip().startswith("Title :")
                and not lines[j].strip().startswith("---")
            ):
                subline = lines[j].strip()

                if subline.startswith("Comment:"):
                    # Extract comment count and votes
                    match = re.search(
                        r"Comment:\s*(\d+)\s*\|\s*Votes:\s*(\d+)", subline
                    )
                    if match:
                        post["comments"] = int(match.group(1))
                        post["votes"] = int(match.group(2))

                elif subline.startswith("Link :"):
                    post["link"] = subline.replace("Link :", "").strip()

                elif subline.startswith("Content :"):
                    # Content might span multiple lines
                    content_text = subline.replace("Content :", "").strip()
                    k = j + 1
                    while k < len(lines) and not lines[k].strip().startswith("---"):
                        content_text += " " + lines[k].strip()
                        k += 1
                    post["content"] = (
                        content_text[:200] + "..."
                        if len(content_text) > 200
                        else content_text
                    )
                    j = k - 1

                j += 1

            # Only add if we have a link
            if "link" in post:
                posts.append(post)

            i = j
        else:
            i += 1

    return posts


def get_top_posts_by_votes(posts, limit=5):
    """Get top posts by vote count"""
    return sorted(posts, key=lambda x: x.get("votes", 0), reverse=True)[:limit]


def get_trending_topics(posts_by_subreddit):
    """Extract trending topics across all subreddits"""
    all_posts = []
    for subreddit, posts in posts_by_subreddit.items():
        for post in posts[:3]:  # Take top 3 from each
            all_posts.append({"subreddit": subreddit, **post})

    # Sort by votes
    return sorted(all_posts, key=lambda x: x.get("votes", 0), reverse=True)[:10]


def generate_html(posts_by_subreddit, output_path="trends_dynamic.html"):
    """Generate HTML from parsed data"""

    # Get trending topics
    trending_topics = get_trending_topics(posts_by_subreddit)

    # Get top posts for each region
    regions = {
        "Latin America": ["reggaeton", "bachata", "cumbia", "salsa"],
        "Nordic/Europe": ["nordicmusic", "electronicmusic", "dutchmusic"],
        "Global": [
            "citypop",
            "kpop",
            "bedroompop",
            "indieheads",
            "folk",
            "worldmusic",
            "arabicmusic",
        ],
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MINY y0 Music Trends Monitor</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --primary: #4a6fa5;
            --secondary: #166088;
            --accent: #ff6b6b;
            --light: #f8f9fa;
            --dark: #343a40;
            --gray: #6c757d;
            --success: #28a745;
            --warning: #ffc107;
            --info: #17a2b8;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: var(--dark);
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        header {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            text-align: center;
            border-left: 5px solid var(--primary);
        }}
        
        .logo {{
            font-size: 2.5rem;
            color: var(--primary);
            margin-bottom: 10px;
        }}
        
        h1 {{
            color: var(--secondary);
            margin-bottom: 10px;
            font-size: 2.2rem;
        }}
        
        .subtitle {{
            color: var(--gray);
            font-size: 1.1rem;
            margin-bottom: 20px;
        }}
        
        .timestamp {{
            background: var(--light);
            padding: 10px 20px;
            border-radius: 25px;
            display: inline-block;
            font-size: 0.9rem;
            color: var(--gray);
            border: 1px solid #e9ecef;
        }}
        
        .stats {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        
        .stat {{
            background: white;
            padding: 15px 25px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.05);
            text-align: center;
            min-width: 150px;
            border-top: 3px solid var(--primary);
        }}
        
        .stat-number {{
            font-size: 2rem;
            font-weight: bold;
            color: var(--primary);
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            font-size: 0.9rem;
            color: var(--gray);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .section {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}
        
        .section-title {{
            color: var(--secondary);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--light);
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .section-title i {{
            color: var(--primary);
        }}
        
        .trending-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        
        .trend-card {{
            background: var(--light);
            border-radius: 10px;
            padding: 20px;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border-left: 4px solid var(--accent);
        }}
        
        .trend-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 30px rgba(0,0,0,0.1);
        }}
        
        .trend-title {{
            font-size: 1.1rem;
            font-weight: 600;
            margin-bottom: 10px;
            color: var(--dark);
        }}
        
        .trend-meta {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 0.9rem;
            color: var(--gray);
        }}
        
        .trend-votes {{
            color: var(--success);
            font-weight: bold;
        }}
        
        .trend-comments {{
            color: var(--info);
        }}
        
        .trend-subreddit {{
            background: var(--primary);
            color: white;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
            display: inline-block;
            margin-bottom: 10px;
        }}
        
        .region-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 25px;
            margin-top: 20px;
        }}
        
        .region-card {{
            background: var(--light);
            border-radius: 10px;
            padding: 25px;
            border-top: 4px solid var(--secondary);
        }}
        
        .region-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #dee2e6;
        }}
        
        .region-name {{
            font-size: 1.3rem;
            font-weight: 600;
            color: var(--secondary);
        }}
        
        .post-list {{
            list-style: none;
        }}
        
        .post-item {{
            padding: 12px 0;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .post-item:last-child {{
            border-bottom: none;
        }}
        
        .post-title {{
            font-size: 1rem;
            margin-bottom: 5px;
            color: var(--dark);
        }}
        
        .post-meta {{
            display: flex;
            gap: 15px;
            font-size: 0.85rem;
            color: var(--gray);
        }}
        
        .cta-section {{
            text-align: center;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
            border-radius: 15px;
            padding: 40px;
            margin-top: 40px;
        }}
        
        .cta-title {{
            font-size: 2rem;
            margin-bottom: 15px;
        }}
        
        .cta-button {{
            display: inline-block;
            background: white;
            color: var(--primary);
            padding: 15px 40px;
            border-radius: 30px;
            text-decoration: none;
            font-weight: 600;
            font-size: 1.1rem;
            margin-top: 20px;
            transition: all 0.3s ease;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }}
        
        .cta-button:hover {{
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.3);
            background: var(--light);
        }}
        
        footer {{
            text-align: center;
            padding: 30px;
            color: var(--gray);
            font-size: 0.9rem;
            margin-top: 40px;
        }}
        
        .automation-badge {{
            background: var(--success);
            color: white;
            padding: 5px 15px;
            border-radius: 15px;
            font-size: 0.8rem;
            display: inline-block;
            margin-top: 10px;
        }}
        
        @media (max-width: 768px) {{
            .trending-grid, .region-grid {{
                grid-template-columns: 1fr;
            }}
            
            .stats {{
                flex-direction: column;
                align-items: center;
            }}
            
            .stat {{
                width: 100%;
                max-width: 250px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <i class="fas fa-music"></i>
            </div>
            <h1>MINY y0 Music Trends Monitor</h1>
            <p class="subtitle">Tracking music trends across 13 cities, 6 continents for MINY y0 residency artists</p>
            <div class="timestamp">
                <i class="fas fa-sync-alt"></i> Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            </div>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">{len(posts_by_subreddit)}</div>
                    <div class="stat-label">Subreddits</div>
                </div>
                <div class="stat">
                    <div class="stat-number">{sum(len(posts) for posts in posts_by_subreddit.values())}</div>
                    <div class="stat-label">Total Posts</div>
                </div>
                <div class="stat">
                    <div class="stat-number">{len(trending_topics)}</div>
                    <div class="stat-label">Trending Topics</div>
                </div>
                <div class="stat">
                    <div class="stat-number">48h</div>
                    <div class="stat-label">Update Cycle</div>
                </div>
            </div>
        </header>
        
        <section class="section">
            <h2 class="section-title">
                <i class="fas fa-fire"></i> Top Trending Topics
            </h2>
            <p>Most discussed music topics across all monitored communities</p>
            
            <div class="trending-grid">
"""

    # Add trending topics
    for i, topic in enumerate(trending_topics[:6], 1):
        html += f'''
                <div class="trend-card">
                    <div class="trend-subreddit">r/{topic["subreddit"]}</div>
                    <h3 class="trend-title">{topic["title"]}</h3>
                    <div class="trend-meta">
                        <span class="trend-votes"><i class="fas fa-arrow-up"></i> {topic.get("votes", 0)} votes</span>
                        <span class="trend-comments"><i class="fas fa-comment"></i> {topic.get("comments", 0)} comments</span>
                    </div>
                    {f"<p>{topic.get('content', '')}</p>" if topic.get("content") else ""}
                    <a href="{topic["link"]}" target="_blank" style="color: var(--primary); font-size: 0.9rem; display: inline-block; margin-top: 10px;">
                        <i class="fas fa-external-link-alt"></i> View on Reddit
                    </a>
                </div>
'''

    html += """
            </div>
        </section>
        
        <section class="section">
            <h2 class="section-title">
                <i class="fas fa-globe-americas"></i> Regional Breakdown
            </h2>
            <p>Music trends by region relevant to MINY y0 cities</p>
            
            <div class="region-grid">
"""

    # Add regional breakdown
    for region_name, subreddits in regions.items():
        html += f"""
                <div class="region-card">
                    <div class="region-header">
                        <h3 class="region-name">{region_name}</h3>
                        <span style="color: var(--gray); font-size: 0.9rem;">
                            {len(subreddits)} subreddits
                        </span>
                    </div>
                    <ul class="post-list">
"""

        # Get top posts for this region
        region_posts = []
        for subreddit in subreddits:
            if subreddit in posts_by_subreddit:
                top_posts = get_top_posts_by_votes(posts_by_subreddit[subreddit], 2)
                for post in top_posts:
                    region_posts.append({"subreddit": subreddit, **post})

        # Display top 4 posts for this region
        for post in region_posts[:4]:
            html += f"""
                        <li class="post-item">
                            <div class="post-title">{post["title"]}</div>
                            <div class="post-meta">
                                <span>r/{post["subreddit"]}</span>
                                <span><i class="fas fa-arrow-up"></i> {post.get("votes", 0)}</span>
                                <span><i class="fas fa-comment"></i> {post.get("comments", 0)}</span>
                            </div>
                        </li>
"""

        html += """
                    </ul>
                </div>
"""

    html += """
            </div>
        </section>
        
        <div class="cta-section">
            <h2 class="cta-title">Apply for MINY y0 Artist Residency</h2>
            <p>Selected artists receive studio time, mentorship, and global exposure across our 13-city network</p>
            <a href="https://y0.minyvinyl.com" target="_blank" class="cta-button">
                <i class="fas fa-arrow-right"></i> Apply Now at y0.minyvinyl.com
            </a>
            <div style="margin-top: 20px;">
                <div class="automation-badge">
                    <i class="fas fa-robot"></i> Auto-updated every 48 hours
                </div>
            </div>
        </div>
        
        <footer>
            <p>MINY y0 Music Trends Monitor • Tracking music communities across 6 continents</p>
            <p>This page automatically updates with trending music discussions from Reddit communities</p>
            <p>© 2026 MINY y0 • <a href="https://minyvinyl.com" style="color: var(--primary);">minyvinyl.com</a></p>
        </footer>
    </div>
    
    <script>
        // Simple animation for cards on scroll
        document.addEventListener('DOMContentLoaded', function() {{
            const cards = document.querySelectorAll('.trend-card, .region-card');
            
            const observer = new IntersectionObserver((entries) => {{
                entries.forEach(entry => {{
                    if (entry.isIntersecting) {{
                        entry.target.style.opacity = '1';
                        entry.target.style.transform = 'translateY(0)';
                    }}
                }});
            }}, {{ threshold: 0.1 }});
            
            cards.forEach(card => {{
                card.style.opacity = '0';
                card.style.transform = 'translateY(20px)';
                card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                observer.observe(card);
            }});
            
            // Update timestamp every minute
            function updateTimestamp() {{
                const now = new Date();
                const timestampEl = document.querySelector('.timestamp');
                if (timestampEl) {{
                    timestampEl.innerHTML = `<i class="fas fa-sync-alt"></i> Last updated: ${{now.toLocaleDateString()}} ${{now.toLocaleTimeString()}}`;
                }}
            }}
            
            setInterval(updateTimestamp, 60000);
        }});
    </script>
</body>
</html>
"""

    # Write HTML file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Generated dynamic trends page: {output_path}")
    return output_path


def main():
    data_dir = Path("data")
    posts_by_subreddit = {}

    # Parse all data files
    for filepath in data_dir.glob("*.txt"):
        subreddit_name = filepath.stem
        posts = parse_reddit_file(filepath)
        if posts:
            posts_by_subreddit[subreddit_name] = posts
            print(f"📊 Parsed {len(posts)} posts from r/{subreddit_name}")

    if not posts_by_subreddit:
        print("❌ No data files found or could not parse any data")
        return

    # Generate HTML
    output_file = generate_html(posts_by_subreddit)

    # Summary
    total_posts = sum(len(posts) for posts in posts_by_subreddit.values())
    print(f"\n📈 Summary:")
    print(f"   Subreddits: {len(posts_by_subreddit)}")
    print(f"   Total posts: {total_posts}")
    print(f"   Generated: {output_file}")


if __name__ == "__main__":
    main()
