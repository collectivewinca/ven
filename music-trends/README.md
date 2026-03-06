# MINY y0 Music Trends Monitoring System

An automated system that tracks music trends across Reddit communities relevant to MINY y0's 13 cities across 6 continents. The system automatically fetches data, generates insights, and publishes updates every 48 hours.

## 🎯 Purpose

Monitor music discussions and trends in communities relevant to MINY y0 residency cities:
- **Stockholm, Copenhagen, Amsterdam** (Nordic/Europe)
- **Morocco** (Africa/Middle East)  
- **NYC, Miami, Ithaca** (North America)
- **Mexico City, Medellín, São Paulo** (Latin America)
- **Dominican Republic** (Caribbean)
- **Tokyo, Bali** (Asia)

## 📊 System Components

### 1. **Data Collection** (`update_trends.sh`)
- Fetches trending posts from 30+ music subreddits
- Covers genres from all MINY y0 regions
- Runs automatically every 48 hours via cron job
- Logs all activities to `cron.log`

### 2. **Dynamic Trends Page** (`trends_dynamic.html`)
- Live dashboard showing current music trends
- Features:
  - Top trending topics across all communities
  - Regional breakdown by MINY y0 cities
  - Real-time engagement metrics (votes, comments)
  - Direct links to Reddit discussions
  - Auto-updating timestamp
- Published to: `https://[unique-id].here.now/`

### 3. **Analytics Dashboard** (`analytics_dashboard.html`)
- Data-driven insights for MINY y0 team
- Features:
  - Regional engagement analysis
  - Top performing communities
  - Trending keywords analysis
  - Performance metrics and recommendations
  - Focus areas for artist recruitment
- Published alongside trends page

### 4. **Subreddit Directory** (`index.html`)
- Comprehensive directory of 60+ music subreddits
- Organized by region and genre
- Useful for manual research and exploration

## 🚀 Quick Start

### View Live Dashboards
1. **Trends Monitor**: https://silken-larch-833w.here.now/
2. **Analytics Dashboard**: https://[latest-analytics].here.now/ (check cron.log for URL)

### Manual Update
```bash
cd /Users/aletviegas/Documents/claude26/music-subreddits
./update_trends.sh
```

### Check Automation Status
```bash
# View cron job
crontab -l | grep update_trends

# View logs
tail -f /Users/aletviegas/Documents/claude26/music-subreddits/cron.log
```

## 📈 Monitored Subreddits

### Latin America & Caribbean (8)
- `reggaeton`, `bachata`, `cumbia`, `salsa`, `merengue`
- `latinrap`, `brazilianmusic`, `mexicanmusic`

### Nordic & Europe (6)
- `nordicmusic`, `electronicmusic`, `dutchmusic`
- `swedishhouse`, `techno`, `deephouse`

### Africa & Middle East (3)
- `arabicmusic`, `afrobeats`, `soukous`

### Asia (6)
- `citypop`, `kpop`, `jpop`, `jrock`, `cpop`, `indianmusic`

### Global & Indie (7)
- `bedroompop`, `indieheads`, `folk`, `worldmusic`
- `hiphopheads`, `rnb`, `jazz`

**Total**: 30 subreddits across 5 regions

## 🔧 Technical Details

### Automation Schedule
- **Frequency**: Every 48 hours
- **Cron Expression**: `0 */48 * * *`
- **Script**: `/Users/aletviegas/Documents/claude26/music-subreddits/update_trends.sh`
- **Logs**: `cron.log` in project directory

### Data Flow
```
Reddit API (via hf CLI) → data/*.txt → generate_trends.py → trends_dynamic.html → here.now
                                   ↘ analytics_dashboard.py → analytics_dashboard.html → here.now
```

### Key Files
- `update_trends.sh` - Main automation script
- `generate_trends.py` - Generates trends HTML from data
- `analytics_dashboard.py` - Creates analytics dashboard
- `data/` - Raw Reddit data (30+ .txt files)
- `cron.log` - Automation logs and URLs

## 📋 Usage for MINY y0 Team

### For Artist Recruitment
1. **Identify trending genres**: Check "Top Keywords" in analytics
2. **Find engaged communities**: See "Top Subreddits by Engagement"
3. **Target specific regions**: Use "Regional Engagement Analysis"
4. **Discover emerging artists**: Browse top posts in relevant subreddits

### For Content Strategy
1. **Align with trends**: Use trending keywords in MINY y0 content
2. **Regional focus**: Tailor content to most engaged regions
3. **Timing**: Schedule announcements when communities are most active

### For Program Planning
1. **Genre focus**: Identify which music styles have strongest communities
2. **Regional balance**: Ensure representation across all MINY y0 cities
3. **Engagement opportunities**: Plan collaborations with active communities

## 🎨 Design Features

### Trends Page
- Light theme with MINY y0 color scheme
- Responsive design (mobile-friendly)
- Interactive cards with hover effects
- Real-time engagement metrics
- Direct links to source discussions

### Analytics Dashboard
- Professional business intelligence style
- Color-coded regions
- Interactive tables and cards
- Actionable insights and recommendations
- Bootstrap 5 framework

## 🔗 Integration with MINY y0

### Website Links
- **Apply for Residency**: https://y0.minyvinyl.com
- **Main Website**: https://minyvinyl.com

### Call-to-Actions
Both dashboards include prominent CTAs linking to:
- MINY y0 residency application page
- MINY vinyl main website
- Live trends monitor for real-time updates

## 📊 Sample Insights (Latest Run)

Based on current data (March 2026):

### Top Performing Communities
1. **r/kpop** - 209.2 avg engagement (highest)
2. **r/hiphopheads** - Strong global reach
3. **r/electronicmusic** - Relevant to European cities

### Regional Engagement
1. **Global/Indie** - 69.2 avg engagement
2. **Asia** - Strong K-pop and city pop communities
3. **Latin America** - Active reggaeton and salsa discussions

### Trending Keywords
- **music**, **song**, **new** (most frequent)
- **album**, **release**, **artist** (common themes)
- **video**, **live**, **tour** (performance-related)

## 🛠️ Maintenance

### Adding New Subreddits
Edit `update_trends.sh` and add to the `SUBREDDITS` array:
```bash
SUBREDDITS=(
    # ... existing subreddits
    "newsubreddit"
)
```

### Troubleshooting
```bash
# Check if automation is running
ps aux | grep update_trends

# View recent logs
tail -50 cron.log

# Test manual run
./update_trends.sh

# Check here.now publishing
ls -la .herenow/state.json
```

### Monitoring
- **Success rate**: Check `cron.log` for fetch results
- **Data volume**: Monitor `data/` directory size
- **Page updates**: Verify timestamps on published pages
- **URL changes**: New here.now URLs logged after each publish

## 📞 Support

### System Status
- **Automation**: ✅ Active (48-hour updates)
- **Data Collection**: ✅ 30 subreddits monitored
- **Publishing**: ✅ here.now integration working
- **Analytics**: ✅ Dashboard generation active

### Known Issues
- Some subreddits may return empty responses (403/404)
- here.now URLs change with each publish (check logs)
- Rate limiting: 1-second delay between subreddit fetches

### Future Enhancements
- Email notifications for significant trends
- Integration with MINY y0 website API
- Historical trend analysis
- Social media cross-posting
- Artist discovery alerts

---

**Last Updated**: March 5, 2026  
**Next Automation Run**: 48 hours from last successful run  
**MINY y0 Website**: https://y0.minyvinyl.com  
**Contact**: MINY y0 Team