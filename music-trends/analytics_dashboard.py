#!/usr/bin/env python3
"""
Analytics Dashboard for MINY y0 Music Trends Monitor
Generates insights and reports for the MINY y0 team
"""

import os
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter


def parse_reddit_file(filepath):
    """Parse Reddit data from hf CLI output format"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    posts = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("Title :"):
            title = line.replace("Title :", "").strip()
            post = {"title": title}

            j = i + 1
            while (
                j < len(lines)
                and not lines[j].strip().startswith("Title :")
                and not lines[j].strip().startswith("---")
            ):
                subline = lines[j].strip()

                if subline.startswith("Comment:"):
                    match = re.search(
                        r"Comment:\s*(\d+)\s*\|\s*Votes:\s*(\d+)", subline
                    )
                    if match:
                        post["comments"] = int(match.group(1))
                        post["votes"] = int(match.group(2))

                elif subline.startswith("Link :"):
                    post["link"] = subline.replace("Link :", "").strip()

                elif subline.startswith("Content :"):
                    content_text = subline.replace("Content :", "").strip()
                    k = j + 1
                    while k < len(lines) and not lines[k].strip().startswith("---"):
                        content_text += " " + lines[k].strip()
                        k += 1
                    post["content"] = content_text
                    j = k - 1

                j += 1

            if "link" in post:
                posts.append(post)

            i = j
        else:
            i += 1

    return posts


def analyze_data(data_dir="data"):
    """Analyze all fetched data and generate insights"""
    data_dir = Path(data_dir)
    all_posts = []
    subreddit_stats = {}

    # Parse all data files
    for filepath in data_dir.glob("*.txt"):
        subreddit_name = filepath.stem
        posts = parse_reddit_file(filepath)

        if posts:
            subreddit_stats[subreddit_name] = {
                "post_count": len(posts),
                "total_votes": sum(p.get("votes", 0) for p in posts),
                "total_comments": sum(p.get("comments", 0) for p in posts),
                "avg_votes": sum(p.get("votes", 0) for p in posts) / len(posts)
                if posts
                else 0,
                "avg_comments": sum(p.get("comments", 0) for p in posts) / len(posts)
                if posts
                else 0,
                "top_posts": sorted(
                    posts, key=lambda x: x.get("votes", 0), reverse=True
                )[:3],
            }

            for post in posts:
                post["subreddit"] = subreddit_name
                all_posts.append(post)

    # Overall statistics
    total_posts = len(all_posts)
    total_votes = sum(p.get("votes", 0) for p in all_posts)
    total_comments = sum(p.get("comments", 0) for p in all_posts)

    # Top performing subreddits
    top_subreddits_by_votes = sorted(
        subreddit_stats.items(), key=lambda x: x[1]["total_votes"], reverse=True
    )[:10]

    top_subreddits_by_engagement = sorted(
        subreddit_stats.items(),
        key=lambda x: x[1]["avg_votes"] + x[1]["avg_comments"],
        reverse=True,
    )[:10]

    # Top posts overall
    top_posts_overall = sorted(
        all_posts, key=lambda x: x.get("votes", 0), reverse=True
    )[:20]

    # Extract keywords from titles
    keywords = Counter()
    for post in all_posts:
        title = post.get("title", "").lower()
        # Common music-related keywords to track
        music_keywords = [
            "album",
            "single",
            "track",
            "song",
            "release",
            "new",
            "music",
            "artist",
            "producer",
            "beat",
            "remix",
            "collab",
            "feature",
            "tour",
            "concert",
            "festival",
            "live",
            "performance",
            "video",
            "visual",
            "lyric",
            "mv",
            "teaser",
        ]

        for keyword in music_keywords:
            if keyword in title:
                keywords[keyword] += 1

    # Region mapping
    region_mapping = {
        "Latin America": [
            "reggaeton",
            "bachata",
            "cumbia",
            "salsa",
            "merengue",
            "latinrap",
            "brazilianmusic",
            "mexicanmusic",
        ],
        "Nordic/Europe": [
            "nordicmusic",
            "electronicmusic",
            "dutchmusic",
            "swedishhouse",
            "techno",
            "deephouse",
        ],
        "Africa/Middle East": ["arabicmusic", "afrobeats", "soukous"],
        "Asia": ["citypop", "kpop", "jpop", "jrock", "cpop", "indianmusic"],
        "Global/Indie": [
            "bedroompop",
            "indieheads",
            "folk",
            "worldmusic",
            "hiphopheads",
            "rnb",
            "jazz",
        ],
    }

    # Calculate region statistics
    region_stats = {}
    for region_name, subreddits in region_mapping.items():
        region_posts = [p for p in all_posts if p["subreddit"] in subreddits]
        if region_posts:
            region_stats[region_name] = {
                "post_count": len(region_posts),
                "total_votes": sum(p.get("votes", 0) for p in region_posts),
                "total_comments": sum(p.get("comments", 0) for p in region_posts),
                "avg_engagement": (
                    sum(p.get("votes", 0) for p in region_posts)
                    + sum(p.get("comments", 0) for p in region_posts)
                )
                / len(region_posts),
            }

    return {
        "timestamp": datetime.now().isoformat(),
        "overall": {
            "total_posts": total_posts,
            "total_votes": total_votes,
            "total_comments": total_comments,
            "avg_votes_per_post": total_votes / total_posts if total_posts else 0,
            "avg_comments_per_post": total_comments / total_posts if total_posts else 0,
            "total_subreddits": len(subreddit_stats),
        },
        "subreddit_stats": subreddit_stats,
        "top_subreddits_by_votes": top_subreddits_by_votes,
        "top_subreddits_by_engagement": top_subreddits_by_engagement,
        "top_posts_overall": top_posts_overall[:10],  # Top 10 only for report
        "keywords": dict(keywords.most_common(20)),
        "region_stats": region_stats,
        "region_mapping": region_mapping,
    }


def generate_html_report(analytics_data, output_path="analytics_dashboard.html"):
    """Generate HTML analytics dashboard"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MINY y0 Music Trends Analytics Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        :root {{
            --miny-primary: #4a6fa5;
            --miny-secondary: #166088;
            --miny-accent: #ff6b6b;
            --miny-light: #f8f9fa;
            --miny-dark: #343a40;
            --miny-success: #28a745;
            --miny-warning: #ffc107;
            --miny-info: #17a2b8;
        }}
        
        body {{
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        }}
        
        .dashboard-header {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            margin: 30px 0;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            border-left: 8px solid var(--miny-primary);
        }}
        
        .stat-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.08);
            transition: transform 0.3s ease;
            border-top: 4px solid var(--miny-primary);
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0,0,0,0.15);
        }}
        
        .stat-number {{
            font-size: 2.8rem;
            font-weight: 800;
            color: var(--miny-primary);
            line-height: 1;
            margin-bottom: 10px;
        }}
        
        .stat-label {{
            font-size: 1rem;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
        }}
        
        .region-badge {{
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
        }}
        
        .region-latin {{ background: #e3f2fd; color: #1565c0; }}
        .region-nordic {{ background: #f3e5f5; color: #7b1fa2; }}
        .region-africa {{ background: #e8f5e9; color: #2e7d32; }}
        .region-asia {{ background: #fff3e0; color: #ef6c00; }}
        .region-global {{ background: #fce4ec; color: #c2185b; }}
        
        .post-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid var(--miny-accent);
            transition: all 0.3s ease;
        }}
        
        .post-card:hover {{
            background: #f8f9fa;
            transform: translateX(5px);
        }}
        
        .keyword-badge {{
            background: var(--miny-info);
            color: white;
            padding: 5px 12px;
            border-radius: 15px;
            font-size: 0.85rem;
            margin: 3px;
            display: inline-block;
        }}
        
        .chart-container {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.08);
        }}
        
        .miny-gradient {{
            background: linear-gradient(135deg, var(--miny-primary), var(--miny-secondary));
            color: white;
            border: none;
        }}
        
        .last-updated {{
            background: var(--miny-light);
            padding: 10px 20px;
            border-radius: 20px;
            font-size: 0.9rem;
            color: #6c757d;
            display: inline-block;
            border: 1px solid #dee2e6;
        }}
    </style>
</head>
<body>
    <div class="container-fluid py-4">
        <div class="dashboard-header text-center">
            <div class="mb-4">
                <i class="fas fa-chart-line fa-3x" style="color: var(--miny-primary);"></i>
            </div>
            <h1 class="display-4 fw-bold mb-3" style="color: var(--miny-secondary);">
                MINY y0 Music Trends Analytics
            </h1>
            <p class="lead mb-4" style="color: #6c757d;">
                Data-driven insights from music communities across 13 cities, 6 continents
            </p>
            <div class="last-updated">
                <i class="fas fa-sync-alt me-2"></i>
                Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            </div>
        </div>
        
        <!-- Overview Stats -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <div class="stat-number">{analytics_data["overall"]["total_posts"]:,}</div>
                    <div class="stat-label">Total Posts</div>
                    <div class="mt-3">
                        <i class="fas fa-newspaper fa-2x" style="color: var(--miny-primary); opacity: 0.7;"></i>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <div class="stat-number">{analytics_data["overall"]["total_votes"]:,}</div>
                    <div class="stat-label">Total Votes</div>
                    <div class="mt-3">
                        <i class="fas fa-arrow-up fa-2x" style="color: var(--miny-success); opacity: 0.7;"></i>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <div class="stat-number">{analytics_data["overall"]["total_comments"]:,}</div>
                    <div class="stat-label">Total Comments</div>
                    <div class="mt-3">
                        <i class="fas fa-comments fa-2x" style="color: var(--miny-info); opacity: 0.7;"></i>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card text-center">
                    <div class="stat-number">{analytics_data["overall"]["total_subreddits"]}</div>
                    <div class="stat-label">Subreddits Monitored</div>
                    <div class="mt-3">
                        <i class="fas fa-globe-americas fa-2x" style="color: var(--miny-warning); opacity: 0.7;"></i>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Region Analysis -->
        <div class="row mb-4">
            <div class="col-md-8">
                <div class="chart-container">
                    <h3 class="mb-4" style="color: var(--miny-secondary);">
                        <i class="fas fa-globe-americas me-2"></i>Regional Engagement Analysis
                    </h3>
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead class="miny-gradient">
                                <tr>
                                    <th style="color: white;">Region</th>
                                    <th style="color: white;">Posts</th>
                                    <th style="color: white;">Total Votes</th>
                                    <th style="color: white;">Total Comments</th>
                                    <th style="color: white;">Avg Engagement</th>
                                </tr>
                            </thead>
                            <tbody>
"""

    # Add region stats
    for region_name, stats in analytics_data["region_stats"].items():
        region_class = region_name.lower().replace("/", "-").split()[0]
        html += f"""
                                <tr>
                                    <td><span class="region-badge region-{region_class}">{region_name}</span></td>
                                    <td><strong>{stats["post_count"]}</strong></td>
                                    <td><span class="text-success">{stats["total_votes"]:,}</span></td>
                                    <td><span class="text-info">{stats["total_comments"]:,}</span></td>
                                    <td><span class="text-warning fw-bold">{stats["avg_engagement"]:.1f}</span></td>
                                </tr>
"""

    html += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <div class="col-md-4">
                <div class="chart-container">
                    <h3 class="mb-4" style="color: var(--miny-secondary);">
                        <i class="fas fa-fire me-2"></i>Top Keywords
                    </h3>
                    <div class="mb-4">
"""

    # Add keywords
    for keyword, count in analytics_data["keywords"].items():
        html += f"""
                        <span class="keyword-badge">{keyword} <span class="badge bg-light text-dark">{count}</span></span>
"""

    html += """
                    </div>
                    <div class="alert alert-info">
                        <i class="fas fa-lightbulb me-2"></i>
                        <strong>Insight:</strong> These keywords show what music communities are discussing most frequently.
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Top Subreddits -->
        <div class="row mb-4">
            <div class="col-md-6">
                <div class="chart-container">
                    <h3 class="mb-4" style="color: var(--miny-secondary);">
                        <i class="fas fa-trophy me-2"></i>Top Subreddits by Votes
                    </h3>
                    <div class="table-responsive">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Subreddit</th>
                                    <th>Posts</th>
                                    <th>Total Votes</th>
                                    <th>Avg Votes</th>
                                </tr>
                            </thead>
                            <tbody>
"""

    # Add top subreddits by votes
    for subreddit, stats in analytics_data["top_subreddits_by_votes"]:
        html += f"""
                                <tr>
                                    <td><strong>r/{subreddit}</strong></td>
                                    <td>{stats["post_count"]}</td>
                                    <td><span class="text-success">{stats["total_votes"]:,}</span></td>
                                    <td><span class="text-warning">{stats["avg_votes"]:.1f}</span></td>
                                </tr>
"""

    html += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="chart-container">
                    <h3 class="mb-4" style="color: var(--miny-secondary);">
                        <i class="fas fa-comments me-2"></i>Top Subreddits by Engagement
                    </h3>
                    <div class="table-responsive">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Subreddit</th>
                                    <th>Avg Votes</th>
                                    <th>Avg Comments</th>
                                    <th>Total Engagement</th>
                                </tr>
                            </thead>
                            <tbody>
"""

    # Add top subreddits by engagement
    for subreddit, stats in analytics_data["top_subreddits_by_engagement"]:
        total_engagement = stats["avg_votes"] + stats["avg_comments"]
        html += f"""
                                <tr>
                                    <td><strong>r/{subreddit}</strong></td>
                                    <td><span class="text-success">{stats["avg_votes"]:.1f}</span></td>
                                    <td><span class="text-info">{stats["avg_comments"]:.1f}</span></td>
                                    <td><span class="text-primary fw-bold">{total_engagement:.1f}</span></td>
                                </tr>
"""

    html += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Top Posts -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="chart-container">
                    <h3 class="mb-4" style="color: var(--miny-secondary);">
                        <i class="fas fa-star me-2"></i>Top Performing Posts
                    </h3>
                    <div class="row">
"""

    # Add top posts
    for i, post in enumerate(analytics_data["top_posts_overall"][:6], 1):
        html += f"""
                        <div class="col-md-6 mb-3">
                            <div class="post-card">
                                <div class="d-flex justify-content-between align-items-start mb-2">
                                    <span class="badge bg-primary">#{i}</span>
                                    <span class="badge bg-secondary">r/{post["subreddit"]}</span>
                                </div>
                                <h6 class="fw-bold mb-2">{post["title"]}</h6>
                                <div class="d-flex justify-content-between text-muted small">
                                    <span><i class="fas fa-arrow-up text-success"></i> {post.get("votes", 0)} votes</span>
                                    <span><i class="fas fa-comment text-info"></i> {post.get("comments", 0)} comments</span>
                                </div>
                            </div>
                        </div>
"""

    html += """
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Insights & Recommendations -->
        <div class="row">
            <div class="col-12">
                <div class="chart-container">
                    <h3 class="mb-4" style="color: var(--miny-secondary);">
                        <i class="fas fa-chart-bar me-2"></i>Insights & Recommendations for MINY y0
                    </h3>
                    <div class="row">
                        <div class="col-md-4">
                            <div class="alert alert-success">
                                <h5><i class="fas fa-bullseye me-2"></i>Focus Areas</h5>
                                <p class="mb-0">
"""

    # Add focus areas based on data
    top_region = max(
        analytics_data["region_stats"].items(),
        key=lambda x: x[1]["avg_engagement"],
        default=(None, None),
    )
    if top_region[0]:
        html += f"""<strong>{top_region[0]}</strong> shows highest engagement. Consider targeting artists from this region."""

    html += """
                                </p>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="alert alert-info">
                                <h5><i class="fas fa-users me-2"></i>Community Insights</h5>
                                <p class="mb-0">
                                    Most active communities: 
"""

    top_subs = [s[0] for s in analytics_data["top_subreddits_by_engagement"][:3]]
    html += f"""<strong>{", ".join(f"r/{sub}" for sub in top_subs)}</strong>"""

    html += """
                                </p>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="alert alert-warning">
                                <h5><i class="fas fa-calendar-alt me-2"></i>Content Strategy</h5>
                                <p class="mb-0">
                                    Keywords like <strong>"""

    top_keywords = list(analytics_data["keywords"].keys())[:3]
    html += f"""{", ".join(top_keywords)}</strong> are trending. Align MINY y0 content with these themes."""

    html += """
                                </p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="mt-4 text-center">
                        <a href="https://y0.minyvinyl.com" target="_blank" class="btn btn-lg miny-gradient">
                            <i class="fas fa-external-link-alt me-2"></i> Visit MINY y0 Website
                        </a>
                        <a href="trends_dynamic.html" target="_blank" class="btn btn-lg btn-outline-primary ms-3">
                            <i class="fas fa-chart-line me-2"></i> View Live Trends
                        </a>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <footer class="text-center mt-5 mb-4">
            <div class="last-updated">
                <i class="fas fa-robot me-2"></i>
                Auto-generated analytics • Updates every 48 hours
            </div>
            <p class="mt-3 text-muted">
                MINY y0 Music Trends Analytics Dashboard • 
                <a href="https://minyvinyl.com" style="color: var(--miny-primary); text-decoration: none;">
                    minyvinyl.com
                </a>
            </p>
        </footer>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Simple animations
        document.addEventListener('DOMContentLoaded', function() {{
            const cards = document.querySelectorAll('.stat-card, .post-card, .chart-container');
            
            cards.forEach((card, index) => {{
                card.style.opacity = '0';
                card.style.transform = 'translateY(20px)';
                card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                
                setTimeout(() => {{
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                }}, index * 100);
            }});
        }});
    </script>
</body>
</html>
"""

    # Write HTML file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Generated analytics dashboard: {output_path}")
    return output_path


def main():
    print("📊 Generating MINY y0 Music Trends Analytics Dashboard...")

    # Analyze data
    analytics_data = analyze_data("data")

    # Generate HTML report
    output_file = generate_html_report(analytics_data)

    # Print summary
    print(f"\n📈 Analytics Summary:")
    print(f"   Total posts analyzed: {analytics_data['overall']['total_posts']:,}")
    print(
        f"   Total engagement: {analytics_data['overall']['total_votes'] + analytics_data['overall']['total_comments']:,}"
    )
    print(f"   Subreddits monitored: {analytics_data['overall']['total_subreddits']}")
    print(f"   Dashboard generated: {output_file}")

    # Print top insights
    print(f"\n🔍 Top Insights:")

    # Top region
    if analytics_data["region_stats"]:
        top_region = max(
            analytics_data["region_stats"].items(), key=lambda x: x[1]["avg_engagement"]
        )
        print(
            f"   • Highest engagement: {top_region[0]} (avg: {top_region[1]['avg_engagement']:.1f})"
        )

    # Top subreddit
    if analytics_data["top_subreddits_by_engagement"]:
        top_sub = analytics_data["top_subreddits_by_engagement"][0]
        print(
            f"   • Most engaged community: r/{top_sub[0]} (avg: {top_sub[1]['avg_votes'] + top_sub[1]['avg_comments']:.1f})"
        )

    # Top keywords
    if analytics_data["keywords"]:
        top_keywords = list(analytics_data["keywords"].items())[:3]
        print(f"   • Trending keywords: {', '.join(k[0] for k in top_keywords)}")


if __name__ == "__main__":
    main()
