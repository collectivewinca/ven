#!/bin/bash

# MINY y0 Music Trends Automation
# Fetches trending music discussions from Reddit and publishes to here.now

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$PROJECT_DIR/data"
LOG_FILE="$PROJECT_DIR/cron.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create directories
mkdir -p "$DATA_DIR"

echo -e "${BLUE}🎵 [$TIMESTAMP] Fetching music trends for MINY y0...${NC}" | tee -a "$LOG_FILE"

# Fetch data from Reddit using hf CLI
echo -e "${BLUE}📡 Fetching from Reddit...${NC}" | tee -a "$LOG_FILE"

# Expanded list of music subreddits relevant to MINY y0 cities
SUBREDDITS=(
    # Latin America & Caribbean
    "reggaeton"     # NYC, Miami, Mexico City, Medellín, Dominican Republic
    "bachata"       # Dominican Republic, NYC, Miami
    "cumbia"        # Mexico City, Medellín, São Paulo
    "salsa"         # NYC, Miami, Dominican Republic
    "merengue"      # Dominican Republic
    "latinrap"      # Mexico City, Medellín
    "brazilianmusic" # São Paulo
    "mexicanmusic"  # Mexico City
    
    # Nordic & Europe
    "nordicmusic"   # Stockholm, Copenhagen
    "electronicmusic" # Amsterdam, Stockholm, Copenhagen
    "dutchmusic"    # Amsterdam
    "swedishhouse"  # Stockholm
    "techno"        # Amsterdam, Berlin influence
    "deephouse"     # Amsterdam, Stockholm
    
    # Africa & Middle East
    "arabicmusic"   # Morocco
    "afrobeats"     # Global influence
    "soukous"       # African rhythms
    
    # Asia
    "citypop"       # Tokyo, Bali
    "kpop"          # Tokyo, Seoul influence
    "jpop"          # Tokyo
    "jrock"         # Tokyo
    "cpop"          # Chinese pop influence
    "indianmusic"   # Bollywood influence in Bali
    
    # Global & Indie
    "bedroompop"    # Global indie scenes
    "indieheads"    # Global indie scenes
    "folk"          # Global folk scenes
    "worldmusic"    # Global coverage
    "hiphopheads"   # Global hip hop influence
    "rnb"           # Global R&B influence
    "jazz"          # Global jazz scenes
)

SUCCESS_COUNT=0
FAIL_COUNT=0

for sub in "${SUBREDDITS[@]}"; do
    echo -n "Fetching r/$sub... " | tee -a "$LOG_FILE"
    if hf reddit -t "$sub" -s hot > "$DATA_DIR/$sub.txt" 2>/dev/null; then
        # Check if file has content (not just error message)
        if [ -s "$DATA_DIR/$sub.txt" ] && ! grep -q "Failed to fetch\|Error\|403\|404" "$DATA_DIR/$sub.txt"; then
            echo -e "${GREEN}✅${NC}" | tee -a "$LOG_FILE"
            ((SUCCESS_COUNT++))
        else
            echo -e "${YELLOW}⚠️ Empty${NC}" | tee -a "$LOG_FILE"
            rm -f "$DATA_DIR/$sub.txt"
            ((FAIL_COUNT++))
        fi
    else
        echo -e "${RED}❌ Failed${NC}" | tee -a "$LOG_FILE"
        ((FAIL_COUNT++))
    fi
    sleep 1  # Rate limiting
done

echo -e "${BLUE}📊 Fetch results: ${GREEN}$SUCCESS_COUNT successful${NC}, ${RED}$FAIL_COUNT failed${NC}" | tee -a "$LOG_FILE"

# Generate dynamic HTML from fetched data
echo -e "${BLUE}🔄 Generating dynamic trends page...${NC}" | tee -a "$LOG_FILE"
cd "$PROJECT_DIR"

TRENDS_SUCCESS=false
ANALYTICS_SUCCESS=false

if python3 generate_trends.py; then
    echo -e "${GREEN}✅ Dynamic trends HTML generated${NC}" | tee -a "$LOG_FILE"
    TRENDS_SUCCESS=true
    
    # Generate analytics dashboard
    echo -e "${BLUE}📊 Generating analytics dashboard...${NC}" | tee -a "$LOG_FILE"
    if python3 analytics_dashboard.py; then
        echo -e "${GREEN}✅ Analytics dashboard generated${NC}" | tee -a "$LOG_FILE"
        ANALYTICS_SUCCESS=true
    else
        echo -e "${YELLOW}⚠️  Failed to generate analytics dashboard${NC}" | tee -a "$LOG_FILE"
    fi
else
    echo -e "${RED}❌ Failed to generate dynamic HTML${NC}" | tee -a "$LOG_FILE"
    exit 1
fi

# Publish to here.now
echo -e "${BLUE}🌐 Publishing to here.now...${NC}" | tee -a "$LOG_FILE"

# Use here-now skill
PUBLISH_SCRIPT="$HOME/.agents/skills/here-now/scripts/publish.sh"
if [ -f "$PUBLISH_SCRIPT" ]; then
    # Publish trends page
    if $TRENDS_SUCCESS; then
        echo -n "Publishing trends page... " | tee -a "$LOG_FILE"
        if "$PUBLISH_SCRIPT" "$PROJECT_DIR/trends_dynamic.html" --client opencode 2>&1 | tail -5; then
            echo -e "${GREEN}✅ Trends published${NC}" | tee -a "$LOG_FILE"
        else
            echo -e "${RED}❌ Failed to publish trends${NC}" | tee -a "$LOG_FILE"
        fi
    fi
    
    # Publish analytics dashboard
    if $ANALYTICS_SUCCESS; then
        echo -n "Publishing analytics dashboard... " | tee -a "$LOG_FILE"
        if "$PUBLISH_SCRIPT" "$PROJECT_DIR/analytics_dashboard.html" --client opencode 2>&1 | tail -5; then
            echo -e "${GREEN}✅ Analytics published${NC}" | tee -a "$LOG_FILE"
        else
            echo -e "${YELLOW}⚠️  Failed to publish analytics${NC}" | tee -a "$LOG_FILE"
        fi
    fi
    
    # Create a simple analytics summary
    TOTAL_POSTS=$(find "$DATA_DIR" -name "*.txt" -exec wc -l {} + | tail -1 | awk '{print $1}')
    echo -e "${BLUE}📈 Automation Summary:${NC}" | tee -a "$LOG_FILE"
    echo "   Timestamp: $TIMESTAMP" | tee -a "$LOG_FILE"
    echo "   Subreddits fetched: $SUCCESS_COUNT/$FAIL_COUNT" | tee -a "$LOG_FILE"
    echo "   Total data lines: $TOTAL_POSTS" | tee -a "$LOG_FILE"
    echo "   Pages generated: $([ $TRENDS_SUCCESS = true ] && echo "Trends") $([ $ANALYTICS_SUCCESS = true ] && echo "Analytics")" | tee -a "$LOG_FILE"
    echo "   Next update: 48 hours" | tee -a "$LOG_FILE"
    
else
    echo -e "${YELLOW}⚠️  here-now publish script not found${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}   Install: https://github.com/anomalyco/opencode/tree/main/skills/here-now${NC}" | tee -a "$LOG_FILE"
    exit 1
fi

echo "" | tee -a "$LOG_FILE"
echo -e "${GREEN}✅ Automation completed at $TIMESTAMP${NC}" | tee -a "$LOG_FILE"