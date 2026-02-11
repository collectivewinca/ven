# miny-ven

60-word music news PWA for creators - Gospel, Hip-Hop, Pop, Rock, Electronic

## 🎵 Live Demo

**https://minyven-news.vercel.app**

## ✨ Features

- **60-Word Summaries**: AI-powered concise music news using DeepSeek API
- **5 Balanced Genres**: Gospel, Hip-Hop, Pop, Rock, Electronic
- **Smart Duplicate Detection**: Fuzzy matching (80% similarity) prevents duplicates
- **Real-Time Updates**: 35+ articles from RSS feeds (hourly auto-refresh)
- **Bookmarks**: Click title to save articles locally
- **Text Link (Quo API)**: Send article links via SMS from the app
- **Swipe Navigation**: Mobile-optimized swipe to browse
- **Pull to Refresh**: Easy content updates
- **PWA Ready**: Installable on mobile devices

## 🏗️ Architecture

### Frontend
- **Framework**: React 18 + TypeScript
- **Styling**: Tailwind CSS with custom glass-morphism design
- **Build Tool**: Vite
- **Data**: REST API calls to Firebase Firestore
- **UI**: Genre badges and source on image, clickable titles

### Backend
- **Language**: Python 3.11+
- **RSS Scraping**: Jesusfreakhideout, Pitchfork, Rolling Stone, Billboard
- **AI Summarization**: DeepSeek API (60-word summaries)
- **Database**: Firebase Firestore (REST API)
- **Automation**: GitHub Actions cron job (hourly)

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ 
- Python 3.11+
- Firebase project

### 1. Clone Repository

```bash
git clone https://github.com/collectivewinca/miny-ven.git
cd miny-ven
```

### 2. Frontend Setup

```bash
# Install dependencies
npm install

# Create environment file
cp .env.example .env

# Add your Firebase credentials to .env
npm run build
npm run dev
```

### 3. Scraper Setup

```bash
cd scraper
pip install -r requirements.txt

# Add API keys to .env
cp .env.example .env
```

### 4. Run Scraper Manually

```bash
cd scraper
python3 rss_scraper.py
```

### 5. Clean Up Duplicates

```bash
cd scraper
python3 cleanup_duplicates.py
```

## 📁 Project Structure

```
miny-ven/
├── .github/workflows/         # GitHub Actions automation
│   └── scraper.yml            # Hourly RSS scraper
├── scraper/                   # Python backend
│   ├── rss_scraper.py         # Main scraper with fuzzy duplicates
│   ├── cleanup_duplicates.py  # Remove duplicate articles
│   ├── seed_firebase_rest.py  # Initial data seeding
│   └── .env                   # API keys
├── src/                       # Frontend source
│   ├── App.tsx               # Main app with bookmarks
│   └── firebase.ts           # Firebase config
├── api/
│   └── quo-sms.js            # Server-side Quo SMS endpoint
├── firestore.rules           # Database security rules
└── firebase.json             # Firebase config
```

## 🔐 Environment Variables

### Frontend (.env)
```bash
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=miny-ven.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=miny-ven
VITE_FIREBASE_STORAGE_BUCKET=miny-ven.firebasestorage.app
VITE_FIREBASE_MESSAGING_SENDER_ID=1055083577389
VITE_FIREBASE_APP_ID=1:1055083577389:web:xxx
VITE_FIREBASE_MEASUREMENT_ID=G-xxx
VITE_PUBLIC_APP_URL=https://miny-ven.vercel.app
```

### Backend (scraper/.env)
```bash
FIREBASE_PROJECT_ID=miny-ven
FIREBASE_API_KEY=
DEEPSEEK_API_KEY=
OPENROUTER_API_KEY=
PERPLEXITY_API_KEY=
```

### Vercel Server Environment Variables (for Quo SMS API)
```bash
QUO_API_URL=
QUO_API_KEY=
QUO_API_KEY_HEADER=Authorization
QUO_AUTH_SCHEME=raw
QUO_FROM=
```

## 🔄 Automation (GitHub Actions)

**Hourly RSS Scraper** runs automatically via GitHub Actions:
- Checks 5 RSS sources every hour
- Uses DeepSeek AI for 60-word summaries
- Prevents duplicates with fuzzy matching (80% threshold)
- Updates Firebase Firestore

**Manual trigger:**
```bash
gh workflow run scraper.yml
```

**Monitor runs:**
```bash
gh run list --workflow=scraper.yml
```

## 🎯 Current Status

- **35 Articles** in database
- **5 RSS Sources**: Jesusfreakhideout, Pitchfork News, Pitchfork Reviews, Rolling Stone, Billboard
- **DeepSeek AI**: Summarizes to exactly 60 words
- **No Duplicates**: Fuzzy matching prevents similar articles

## 🔧 Key Features Explained

### Duplicate Prevention
The scraper uses **Jaccard similarity** to detect near-duplicate titles:
- Extracts key words (removes "the", "a", "to", etc.)
- Calculates 80% similarity threshold
- Blocks articles like:
  - "Adam Sandler Award for His Songwriting" vs "Adam Sandler Songwriting Award" → **Blocked**

### Bookmarks
- **Click article title** to bookmark/unbookmark
- **Yellow bookmark icon** appears next to title when saved
- **Bookmark button** in header shows count badge
- Saved to browser localStorage

### UI Layout
- **Genre badge** (top-left of image): "Gospel", "Hip-Hop", etc.
- **Source badge** (top-right of image): "Pitchfork", "Billboard", etc.
- **Title**: Clickable to toggle bookmark
- **16:9 Image**: Compact format for mobile

## 🚢 Deployment

### Vercel (Frontend)
Already deployed: https://dist-bay-two-38.vercel.app

```bash
cd dist
vercel --prod
```

### Firebase
Firestore database with public reads and constrained writes:
- Authenticated users can write/delete.
- Unauthenticated scraper writes are limited to strict article schema + safe counters.

## 📱 Recent Articles

- Piss in the Wind (Pitchfork Reviews)
- Do You Still Love Me? (Pitchfork Reviews)
- Bad Bunny's Super Bowl Performance (Rolling Stone)
- Britney Spears Sells Catalog (Rolling Stone)
- Adam Sandler ASCAP Award (Billboard)
- Fireflight's Dawn Michele New Group (Jesusfreakhideout)

## 📝 License

Private repository - All rights reserved

---

Built with ❤️ for music creators
