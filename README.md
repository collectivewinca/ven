# miny-ven

60-word music news aggregator with location-based targeting - Gospel, Hip-Hop, Pop, Rock, Electronic

## 🎵 Live Demo

**https://miny-ven.vercel.app**

## ✨ Features

- **Gold-Standard UI**: Premium glass-morphism design with smooth animations
- **5 Balanced Genres**: Gospel, Hip-Hop, Pop, Rock, Electronic
- **60-Word Summaries**: AI-powered concise music news
- **Location-Based News**: Target local music scenes and events
- **Real-Time Updates**: Firebase Firestore for live content updates
- **Bookmark & Share**: Save articles and share via email/social
- **RSS Integration**: Jesusfreakhideout, Pitchfork, Cross Rhythms
- **AI Summarization**: OpenRouter (Mistral 7B) for 60-word summaries
- **Perplexity Search**: Location-aware music news discovery
- **PWA Ready**: Installable on mobile devices

## 🏗️ Architecture

### Frontend
- **Framework**: React 18 + TypeScript
- **Styling**: Tailwind CSS with custom animations
- **Build Tool**: Vite
- **PWA**: Service Worker, Manifest, Offline support
- **UI Icons**: Lucide React
- **State**: React hooks with localStorage persistence

### Backend
- **Language**: Python 3.11+
- **RSS Scraping**: XML parsing with requests
- **AI Summarization**: OpenRouter API (Mistral 7B)
- **Location Search**: Perplexity API
- **Database**: Firebase Firestore
- **Scheduling**: Cron jobs for hourly updates

### APIs
- **OpenRouter**: AI summarization to 60 words
- **Perplexity**: Location-based music news search
- **Firebase**: Real-time database and hosting

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ 
- Python 3.11+
- Firebase account
- Vercel account (for deployment)

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

# Edit .env with your Firebase credentials
VITE_FIREBASE_API_KEY=your_firebase_api_key
VITE_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your_project_id
# ... (see .env.example for all variables)

# Start development server
npm run dev
```

### 3. Scraper Setup

```bash
cd scraper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Edit .env with your API keys
OPENROUTER_API_KEY=your_openrouter_key
PERPLEXITY_API_KEY=your_perplexity_key
FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
```

### 4. Firebase Setup

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Create a new project
3. Enable Firestore Database
4. Download service account key
5. Save as `scraper/firebase-credentials.json`
6. Copy Firebase config to frontend `.env`

### 5. Run Scraper

```bash
cd scraper
python rss_scraper.py
```

## 📁 Project Structure

```
miny-ven/
├── .env.example              # Frontend environment template
├── .gitignore               # Git ignore rules
├── README.md                # This file
├── index.html               # HTML entry point
├── package.json             # Node dependencies
├── scraper/                 # Python backend
│   ├── .env.example         # Backend environment template
│   ├── requirements.txt     # Python dependencies
│   ├── rss_scraper.py       # RSS feed scraper
│   └── seed_data.py         # Initial data seeder
├── src/                     # Frontend source
│   ├── App.tsx              # Main app component
│   ├── App.css              # App styles
│   ├── firebase.ts          # Firebase configuration
│   ├── index.css            # Global styles
│   ├── main.tsx             # Entry point
│   ├── assets/              # Static assets
│   ├── components/          # React components
│   ├── data/                # Mock data
│   └── types/               # TypeScript types
├── public/                  # Public assets
│   ├── manifest.json        # PWA manifest
│   └── sw.js                # Service worker
└── tailwind.config.js       # Tailwind configuration
```

## 🔐 Environment Variables

### Frontend (.env)
```bash
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_STORAGE_BUCKET=
VITE_FIREBASE_MESSAGING_SENDER_ID=
VITE_FIREBASE_APP_ID=
VITE_FIREBASE_MEASUREMENT_ID=
```

### Backend (scraper/.env)
```bash
OPENROUTER_API_KEY=
PERPLEXITY_API_KEY=
FIREBASE_CREDENTIALS_PATH=
```

## 🔧 Configuration

### RSS Feed Sources
Edit `scraper/rss_scraper.py` to add/modify sources:

```python
RSS_SOURCES = {
    "jesusfreakhideout": {
        "url": "https://www.jesusfreakhideout.com/news/feed.xml",
        "genre": "gospel",
        "priority": 1,
    },
    "pitchfork_news": {
        "url": "https://pitchfork.com/feed/feed-news/rss",
        "genre": "mixed",
        "priority": 2,
    },
    # Add more sources here
}
```

### Genre Classification
Customize genre keywords in `scraper/rss_scraper.py`:

```python
GENRE_KEYWORDS = {
    "gospel": ["gospel", "christian", "worship", "ccm", "church"],
    "hiphop": ["hip-hop", "rap", "trap", "r&b", "drill"],
    "pop": ["pop", "mainstream", "chart", "top 40"],
    "rock": ["rock", "alternative", "indie", "punk", "metal"],
    "electronic": ["electronic", "edm", "house", "techno", "dubstep"],
}
```

## 📊 Data Flow

```
RSS Feeds → Python Scraper → OpenRouter AI → 60-Word Summary → Firebase
Perplexity API → Location Search → OpenRouter AI → 60-Word Summary → Firebase
Firebase → Real-time Updates → React PWA → User
```

## 🔄 Automation

### Schedule Scraper (Cron)

Run every 30 minutes:
```bash
*/30 * * * * cd /path/to/miny-ven/scraper && python rss_scraper.py >> scraper.log 2>&1
```

Run Perplexity search hourly:
```bash
0 * * * * cd /path/to/miny-ven/scraper && python perplexity_scraper.py >> perplexity.log 2>&1
```

## 🚢 Deployment

### Vercel (Frontend)

1. Connect GitHub repo to Vercel
2. Set environment variables in Vercel dashboard
3. Deploy automatically on push to main

### Firebase (Backend)

1. Enable Firestore in Firebase Console
2. Set up Firebase Authentication if needed
3. Configure security rules for Firestore

## 📱 PWA Features

- Installable on iOS/Android home screens
- Offline reading capability
- Push notifications (future)
- Background sync (future)

## 🎯 Roadmap

### Phase 1: MVP ✅
- Gold-standard UI
- 5 balanced genres
- RSS integration
- Firebase backend

### Phase 2: Enhanced Content
- Perplexity API integration
- Location-based targeting
- User preferences (news types)
- Real-time updates

### Phase 3: Advanced Features
- Audio previews
- Push notifications
- Multi-language support
- Analytics dashboard

### Phase 4: Monetization
- Sponsored content
- Premium tier
- Affiliate links

## 🔒 Security

- All API keys stored in environment variables
- Firebase security rules for database access
- No sensitive data in repository
- GitHub Secrets for CI/CD

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📝 License

Private repository - All rights reserved

## 🙏 Acknowledgments

- OpenRouter for AI summarization
- Perplexity for location-based search
- Firebase for real-time database
- Unsplash for demo images
- Lucide for icons

## 📞 Support

For questions or issues, please open a GitHub issue or contact the maintainers.

---

Built with ❤️ for music lovers
