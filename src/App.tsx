import { useState, useEffect, useCallback, useRef } from 'react';
import type { MusicNewsArticle, Genre } from './types/news';
import { Bookmark, Share2, Music, X, ExternalLink, RefreshCw, Menu, Volume2, Pause, Sun, Moon } from 'lucide-react';
import { LazyArticleImage } from './components/LazyArticleImage';
import { ArticleSkeleton } from './components/ArticleSkeleton';
import { Toast } from './components/Toast';
import { PullToRefresh } from './components/PullToRefresh';
import { useArtistEpk } from './hooks/useArtistEpk';

function App() {
  const [articles, setArticles] = useState<MusicNewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedGenre, setSelectedGenre] = useState<Genre>('all');
  const [bookmarks, setBookmarks] = useState<string[]>(() => {
    const saved = localStorage.getItem('miny-ven-bookmarks');
    return saved ? JSON.parse(saved) : [];
  });
  const [showBookmarks, setShowBookmarks] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [touchStart, setTouchStart] = useState<number | null>(null);
  const [touchEnd, setTouchEnd] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isPulling, setIsPulling] = useState(false);
  const [audioLoading, setAudioLoading] = useState(false);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const { ready: epkReady, getEpkUrl, findEpkInText } = useArtistEpk();
  const [audioArticleId, setAudioArticleId] = useState<string | null>(null);

  // ---------- Theme ----------
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = localStorage.getItem('miny-ven-theme');
    if (saved === 'light' || saved === 'dark') return saved;
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
    return 'light';
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(theme);
    localStorage.setItem('miny-ven-theme', theme);
    // Update meta theme-color
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'dark' ? '#06060a' : '#f5f5f7');
  }, [theme]);

  // Listen for system preference changes
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('miny-ven-theme')) {
        setTheme(e.matches ? 'dark' : 'light');
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  }, []);

  const contentRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const bedNodesRef = useRef<{ oscillators: OscillatorNode[]; gain: GainNode } | null>(null);

  // ---------- Data fetching ----------

  const fetchArticles = useCallback(async (genre: Genre = 'all') => {
    setLoading(true);
    setArticles([]);

    try {
      const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID || 'miny-ven';
      const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;
      console.log('Fetching articles from REST API...');

      const metadataFields = [
        'title', 'summary', 'source', 'source_url', 'primary_genre',
        'secondary_genres', 'artist_names', 'image_source',
        'published_at', 'read_time', 'share_count', 'email_count',
        'bookmark_count', 'view_count', 'location'
      ];

      let allDocs: any[] = [];
      let pageToken = '';
      while (true) {
        const params = new URLSearchParams();
        if (apiKey) params.set('key', apiKey);
        params.set('pageSize', '300');
        if (pageToken) params.set('pageToken', pageToken);
        metadataFields.forEach(f => params.append('mask.fieldPaths', f));
        const url = `https://firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents/articles?${params}`;
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        allDocs = allDocs.concat(data.documents || []);
        pageToken = data.nextPageToken || '';
        if (!pageToken) break;
      }

      console.log(`REST API: fetched ${allDocs.length} docs (metadata only)`);

      if (allDocs.length === 0) {
        setArticles([]);
        setToast('No articles found.');
        setLoading(false);
        return;
      }

      const fetchedArticles: MusicNewsArticle[] = allDocs.map((doc: any) => {
        const fields = doc.fields;
        const docId = doc.name.split('/').pop();

        const getField = (field: any) => {
          if (!field) return null;
          if (field.stringValue !== undefined) return field.stringValue;
          if (field.integerValue !== undefined) return parseInt(field.integerValue);
          if (field.doubleValue !== undefined) return field.doubleValue;
          if (field.arrayValue) {
            return (field.arrayValue.values || []).map((v: any) => v.stringValue || '');
          }
          return null;
        };

        return {
          id: docId,
          title: getField(fields.title) || '',
          summary: getField(fields.summary) || '',
          fullContent: getField(fields.full_content) || '',
          source: getField(fields.source) || '',
          sourceUrl: getField(fields.source_url) || '',
          primaryGenre: getField(fields.primary_genre) || '',
          secondaryGenres: getField(fields.secondary_genres) || [],
          artistNames: getField(fields.artist_names) || [],
          imageUrl: '',
          imageSource: getField(fields.image_source) || '',
          publishedAt: new Date(getField(fields.published_at) || Date.now()),
          readTime: getField(fields.read_time) || 60,
          shareCount: getField(fields.share_count) || 0,
          emailCount: getField(fields.email_count) || 0,
          bookmarkCount: getField(fields.bookmark_count) || 0,
          viewCount: getField(fields.view_count) || 0,
          isBookmarked: false,
          location: getField(fields.location) || ''
        };
      });

      fetchedArticles.sort((a: MusicNewsArticle, b: MusicNewsArticle) =>
        b.publishedAt.getTime() - a.publishedAt.getTime()
      );

      const filtered = genre === 'all'
        ? fetchedArticles
        : fetchedArticles.filter((a: MusicNewsArticle) => a.primaryGenre === genre);

      setArticles(filtered);
      console.log(`Loaded ${filtered.length} articles from REST API`);

      if (filtered.length === 0) {
        setToast('No articles found for this genre.');
      }
    } catch (error: any) {
      console.error('Error fetching articles:', error);
      console.error('Error message:', error.message);
      setArticles([]);
      setToast(`Error: ${error.message || 'Failed to load articles'}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchArticles(selectedGenre);
  }, [fetchArticles, selectedGenre]);

  // ---------- Constants ----------

  const genres: { id: Genre; label: string; gradient: string }[] = [
    { id: 'all', label: 'All', gradient: 'from-gray-600 to-gray-500' },
    { id: 'gospel', label: 'Gospel', gradient: 'from-amber-500 to-amber-600' },
    { id: 'hiphop', label: 'Hip-Hop', gradient: 'from-violet-500 to-violet-600' },
    { id: 'pop', label: 'Pop', gradient: 'from-rose-500 to-rose-600' },
    { id: 'rock', label: 'Rock', gradient: 'from-red-500 to-red-600' },
    { id: 'electronic', label: 'Electronic', gradient: 'from-cyan-500 to-cyan-600' },
    { id: 'tech', label: 'Tech', gradient: 'from-emerald-600 to-teal-600' },
  ];

  const filteredArticles = selectedGenre === 'all'
    ? articles
    : articles.filter(a => a.primaryGenre === selectedGenre);

  const currentArticle = filteredArticles[currentIndex];

  // ---------- Audio ----------

  const ensureAudioContext = useCallback(() => {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    if (!Ctx) return null;
    if (!audioContextRef.current) {
      audioContextRef.current = new Ctx();
    }
    if (audioContextRef.current.state === 'suspended') {
      audioContextRef.current.resume().catch(() => {});
    }
    return audioContextRef.current;
  }, []);

  const stopNewsBed = useCallback(() => {
    if (!bedNodesRef.current) return;
    const { oscillators, gain } = bedNodesRef.current;
    oscillators.forEach((osc) => {
      try { osc.stop(); } catch {}
      try { osc.disconnect(); } catch {}
    });
    try { gain.disconnect(); } catch {}
    bedNodesRef.current = null;
  }, []);

  const playNewsSting = useCallback((phase: 'start' | 'end') => {
    const ctx = ensureAudioContext();
    if (!ctx) return;

    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.connect(gain);
    gain.connect(ctx.destination);

    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.14, now + 0.04);
    gain.gain.exponentialRampToValueAtTime(0.05, now + 0.16);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.52);

    if (phase === 'start') {
      osc.frequency.setValueAtTime(520, now);
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.16);
      osc.frequency.exponentialRampToValueAtTime(740, now + 0.34);
    } else {
      osc.frequency.setValueAtTime(740, now);
      osc.frequency.exponentialRampToValueAtTime(560, now + 0.18);
      osc.frequency.exponentialRampToValueAtTime(420, now + 0.34);
    }

    osc.start(now);
    osc.stop(now + 0.56);
  }, [ensureAudioContext]);

  const startNewsBed = useCallback(() => {
    if (bedNodesRef.current) return;
    const ctx = ensureAudioContext();
    if (!ctx) return;

    const master = ctx.createGain();
    master.gain.value = 0.02;
    master.connect(ctx.destination);

    const oscA = ctx.createOscillator();
    const oscB = ctx.createOscillator();
    const lfo = ctx.createOscillator();
    const lfoGain = ctx.createGain();

    oscA.type = 'sine';
    oscA.frequency.value = 220;
    oscB.type = 'triangle';
    oscB.frequency.value = 329.63;

    lfo.type = 'sine';
    lfo.frequency.value = 0.28;
    lfoGain.gain.value = 0.01;

    lfo.connect(lfoGain);
    lfoGain.connect(master.gain);

    oscA.connect(master);
    oscB.connect(master);

    oscA.start();
    oscB.start();
    lfo.start();

    bedNodesRef.current = {
      oscillators: [oscA, oscB, lfo],
      gain: master,
    };
  }, [ensureAudioContext]);

  const stopAudio = useCallback(() => {
    stopNewsBed();
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
    setIsAudioPlaying(false);
    setAudioLoading(false);
    setAudioArticleId(null);
  }, [stopNewsBed]);

  // ---------- Actions ----------

  useEffect(() => {
    localStorage.setItem('miny-ven-bookmarks', JSON.stringify(bookmarks));
  }, [bookmarks]);

  const trackEvent = useCallback((eventType: string, articleId: string) => {
    console.log('Analytics:', {
      eventType,
      articleId,
      genre: currentArticle?.primaryGenre,
      timestamp: new Date().toISOString()
    });
  }, [currentArticle]);

  const handleSwipe = useCallback((direction: 'up' | 'down') => {
    if (direction === 'up' && currentIndex < filteredArticles.length - 1) {
      setCurrentIndex(prev => prev + 1);
      trackEvent('swipe_up', currentArticle.id);
    } else if (direction === 'down' && currentIndex > 0) {
      setCurrentIndex(prev => prev - 1);
    }
  }, [currentIndex, filteredArticles.length, currentArticle, trackEvent]);

  const toggleBookmark = useCallback((articleId: string) => {
    setBookmarks(prev => {
      const isBookmarked = prev.includes(articleId);
      const newBookmarks = isBookmarked
        ? prev.filter(id => id !== articleId)
        : [...prev, articleId];

      setToast(isBookmarked ? 'Removed from bookmarks' : 'Added to bookmarks');
      trackEvent(isBookmarked ? 'unbookmark' : 'bookmark', articleId);
      return newBookmarks;
    });
  }, [trackEvent]);

  const handleShare = useCallback(async () => {
    if (!currentArticle) return;

    try {
      if (navigator.share) {
        await navigator.share({
          title: currentArticle.title,
          text: currentArticle.summary,
          url: currentArticle.sourceUrl,
        });
      } else {
        await navigator.clipboard.writeText(`${currentArticle.title}\n\n${currentArticle.summary}\n\n${currentArticle.sourceUrl}`);
        setToast('Link copied to clipboard');
      }
      trackEvent('share', currentArticle.id);
    } catch (error) {
      console.log('Share cancelled');
    }
  }, [currentArticle, trackEvent]);

  const handleListen = useCallback(async () => {
    if (!currentArticle) return;

    if (isAudioPlaying && audioArticleId === currentArticle.id) {
      stopAudio();
      setToast('Audio paused');
      return;
    }

    setAudioLoading(true);
    setAudioArticleId(currentArticle.id);
    try {
      const weekday = new Date().toLocaleDateString('en-US', { weekday: 'long' });
      const text = `This is VEN Music Industry News, ${weekday} edition. ` +
        `Now we segue into the next headline. ${currentArticle.title}. ` +
        `${currentArticle.summary}. ` +
        `That wraps this VEN briefing segment. Stay tuned for the next music industry update.`;

      playNewsSting('start');
      const response = await fetch('/api/elevenlabs-tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data?.error || 'Failed to generate audio');
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);

      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = objectUrl;

      const audio = new Audio(objectUrl);
      audioRef.current = audio;
      audio.onended = () => {
        playNewsSting('end');
        window.setTimeout(() => stopAudio(), 380);
      };
      audio.onerror = () => {
        stopAudio();
        setToast('Audio playback failed');
      };

      startNewsBed();
      await audio.play();
      setIsAudioPlaying(true);
      setAudioLoading(false);
      trackEvent('listen_audio', currentArticle.id);
    } catch (error: any) {
      stopAudio();
      setToast(error?.message || 'Unable to generate audio');
    }
  }, [audioArticleId, currentArticle, isAudioPlaying, playNewsSting, startNewsBed, stopAudio, trackEvent]);

  // ---------- Touch handlers ----------

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    const touchY = e.targetTouches[0].clientY;
    setTouchEnd(null);
    setTouchStart(touchY);
    setIsDragging(true);

    if (containerRef.current && containerRef.current.scrollTop === 0) {
      setIsPulling(true);
    }
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    const touchY = e.targetTouches[0].clientY;
    setTouchEnd(touchY);

    if (isPulling && touchStart && containerRef.current?.scrollTop === 0) {
      const pullDist = touchStart - touchY;
      if (pullDist < 0) {
        setPullDistance(Math.abs(pullDist));
      }
    }

    if (!isPulling && touchStart && contentRef.current) {
      const diff = touchStart - touchY;
      const translateY = diff * 0.2;
      contentRef.current.style.transform = `translateY(${-translateY}px)`;
    }
  }, [touchStart, isPulling]);

  const onTouchEnd = useCallback(() => {
    setIsDragging(false);
    setIsPulling(false);

    if (pullDistance > 80) {
      fetchArticles(selectedGenre);
      setToast('Refreshing content...');
    }
    setPullDistance(0);

    if (!touchStart || !touchEnd) {
      if (contentRef.current) contentRef.current.style.transform = '';
      return;
    }

    const distance = touchStart - touchEnd;
    const minSwipeDistance = 50;

    if (contentRef.current) {
      contentRef.current.style.transform = '';
      contentRef.current.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
      setTimeout(() => {
        if (contentRef.current) contentRef.current.style.transition = '';
      }, 300);
    }

    if (distance > minSwipeDistance) {
      handleSwipe('up');
    } else if (distance < -minSwipeDistance) {
      handleSwipe('down');
    }
  }, [touchStart, touchEnd, pullDistance, handleSwipe, fetchArticles, selectedGenre]);

  // ---------- Keyboard & effects ----------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowUp') handleSwipe('down');
      if (e.key === 'ArrowDown') handleSwipe('up');
      if (e.key === 'b') setShowBookmarks(prev => !prev);
      if (e.key === 'Escape') {
        setShowBookmarks(false);
        setShowMenu(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSwipe]);

  useEffect(() => {
    setCurrentIndex(0);
  }, [selectedGenre]);

  useEffect(() => {
    return () => stopAudio();
  }, [stopAudio]);

  useEffect(() => {
    if (!currentArticle) return;
    if (audioArticleId && audioArticleId !== currentArticle.id) {
      stopAudio();
    }
  }, [audioArticleId, currentArticle, stopAudio]);

  // ---------- Helpers ----------

  const genreGradient = (genre: string) =>
    genres.find(g => g.id === genre)?.gradient || 'from-gray-600 to-gray-500';

  const locationFlag = (location: string): string => {
    const flags: Record<string, string> = {
      scandinavia: '🇸🇪',
      amsterdam: '🇳🇱',
      morocco: '🇲🇦',
      nyc: '🇺🇸',
      mexico: '🇲🇽',
      medellin: '🇨🇴',
      brazil: '🇧🇷',
      miami: '🇺🇸',
      caribbean: '🇩🇴',
      tokyo: '🇯🇵',
      bali: '🇮🇩',
      // Fallback mappings
      'new york': '🇺🇸',
      'new york city': '🇺🇸',
      'los angeles': '🇺🇸',
      'london': '🇬🇧',
      'uk': '🇬🇧',
      'england': '🇬🇧',
      'nashville': '🇺🇸',
      'atlanta': '🇺🇸',
      'chicago': '🇺🇸',
      'toronto': '🇨🇦',
      'canada': '🇨🇦',
      'australia': '🇦🇺',
      'sydney': '🇦🇺',
      'germany': '🇩🇪',
      'berlin': '🇩🇪',
      'france': '🇫🇷',
      'paris': '🇫🇷',
      'nigeria': '🇳🇬',
      'south africa': '🇿🇦',
      'jamaica': '🇯🇲',
      'cuba': '🇨🇺',
      'korea': '🇰🇷',
      'seoul': '🇰🇷',
      'china': '🇨🇳',
      'india': '🇮🇳',
      'mumbai': '🇮🇳',
      'dubai': '🇦🇪',
      'uae': '🇦🇪',
    };
    return flags[location?.toLowerCase()] || '';
  };

  // Carousel dots: show max 7 with ellipsis
  const renderDots = () => {
    const total = filteredArticles.length;
    if (total <= 1) return null;

    const maxDots = 7;
    let dots: (number | 'ellipsis')[] = [];

    if (total <= maxDots) {
      dots = Array.from({ length: total }, (_, i) => i);
    } else {
      if (currentIndex <= 3) {
        dots = [0, 1, 2, 3, 4, 'ellipsis', total - 1];
      } else if (currentIndex >= total - 4) {
        dots = [0, 'ellipsis', total - 5, total - 4, total - 3, total - 2, total - 1];
      } else {
        dots = [0, 'ellipsis', currentIndex - 1, currentIndex, currentIndex + 1, 'ellipsis', total - 1];
      }
    }

    return (
      <div className="flex items-center justify-center gap-1.5 py-3 safe-area-bottom">
        {dots.map((dot, i) =>
          dot === 'ellipsis' ? (
            <span key={`e${i}`} className="w-1 h-1 rounded-full bg-white/20" />
          ) : (
            <button
              key={dot}
              onClick={() => setCurrentIndex(dot)}
              className={`rounded-full transition-all duration-300 ${
                dot === currentIndex
                  ? 'w-2.5 h-2.5 bg-white'
                  : 'w-1.5 h-1.5 bg-white/30 hover:bg-white/50'
              }`}
              aria-label={`Go to article ${dot + 1}`}
            />
          )
        )}
      </div>
    );
  };

  // ---------- Action buttons (shared) ----------

  // Fully fluid sizing — scales continuously with viewport, no breakpoint jumps
  const fluidBtn: React.CSSProperties = {
    padding: 'clamp(0.5rem, 0.35rem + 0.5vw, 0.75rem)',
    minWidth: 'clamp(36px, 32px + 1vw, 48px)',
    minHeight: 'clamp(36px, 32px + 1vw, 48px)',
  };
  const fluidIcon: React.CSSProperties = {
    width: 'clamp(16px, 14px + 0.5vw, 22px)',
    height: 'clamp(16px, 14px + 0.5vw, 22px)',
  };
  const fluidGap: React.CSSProperties = {
    gap: 'clamp(0.375rem, 0.25rem + 0.4vw, 0.75rem)',
  };

  const renderActions = () => {
    if (!currentArticle) return null;
    return (
          <div className="flex items-center" style={fluidGap}>
        <button
          onClick={() => toggleBookmark(currentArticle.id)}
          className={`rounded-xl transition-all duration-200 btn-press flex items-center justify-center ${
            bookmarks.includes(currentArticle.id) ? 'bg-amber-500/20' : ''
          }`}
          style={{
            ...fluidBtn,
            background: bookmarks.includes(currentArticle.id) ? 'rgba(245, 158, 11, 0.15)' : 'var(--action-bg)',
            color: bookmarks.includes(currentArticle.id) ? '#f59e0b' : 'var(--action-text)'
          }}
          aria-label={bookmarks.includes(currentArticle.id) ? 'Remove bookmark' : 'Add bookmark'}
        >
          <Bookmark style={fluidIcon} className={bookmarks.includes(currentArticle.id) ? 'fill-amber-400' : ''} />
        </button>

        <button
          onClick={handleShare}
          className="rounded-xl transition-all duration-200 btn-press flex items-center justify-center"
          style={{ ...fluidBtn, background: 'var(--action-bg)', color: 'var(--action-text)' }}
          aria-label="Share article"
        >
          <Share2 style={fluidIcon} />
        </button>

        <button
          onClick={handleListen}
          disabled={audioLoading}
          className="rounded-xl transition-all duration-200 btn-press flex items-center justify-center disabled:opacity-50"
          style={{ ...fluidBtn, background: 'var(--action-bg)', color: 'var(--action-text)' }}
          aria-label="Listen to article"
        >
          {audioLoading ? (
            <RefreshCw style={fluidIcon} className="animate-spin" />
          ) : isAudioPlaying && audioArticleId === currentArticle.id ? (
            <Pause style={fluidIcon} />
          ) : (
            <Volume2 style={fluidIcon} />
          )}
        </button>

        <a
          href={currentArticle.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-xl transition-all duration-200 flex items-center justify-center"
          style={{ ...fluidBtn, background: 'var(--action-bg)', color: 'var(--action-text)' }}
          onClick={() => trackEvent('external_link', currentArticle.id)}
          aria-label="Open source article"
        >
          <ExternalLink style={fluidIcon} />
        </a>
      </div>
    );
  };

  // ---------- Render ----------

  if (!currentArticle && !loading) {
    return (
      <div className="h-dvh flex items-center justify-center safe-area-top safe-area-bottom" style={{ background: 'var(--bg-primary)' }}>
        <div className="text-center px-4">
          <Music className="w-16 h-16 mx-auto mb-6" style={{ color: 'var(--text-faint)' }} />
          <p className="font-display text-lg font-bold mb-2" style={{ color: 'var(--text-tertiary)' }}>No articles found</p>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Run the scraper to populate Firebase with content</p>
          <button
            onClick={() => fetchArticles(selectedGenre)}
            className="mt-8 px-7 py-3 rounded-full transition-all font-medium text-sm tracking-wide"
            style={{ background: 'var(--action-bg)', color: 'var(--text-secondary)' }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-dvh flex flex-col overflow-hidden safe-area-top safe-area-bottom relative" style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      {/* Atmospheric background glow */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute top-0 left-1/4 w-[600px] h-[400px] rounded-full blur-[120px]" style={{ background: 'var(--glow-a)' }} />
        <div className="absolute bottom-1/4 right-0 w-[500px] h-[350px] rounded-full blur-[100px]" style={{ background: 'var(--glow-b)' }} />
      </div>

      <PullToRefresh pullDistance={pullDistance} isPulling={isPulling} />

      {/* ─── Header ─── */}
      <header className="shrink-0 z-50 glass" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
        {/* Top bar */}
        <div className="flex items-center justify-between" style={{ padding: 'clamp(0.5rem, 0.4rem + 0.5vw, 0.875rem) clamp(1rem, 0.75rem + 1vw, 2rem)' }}>
          <div className="flex items-center" style={{ gap: 'clamp(0.625rem, 0.5rem + 0.3vw, 0.75rem)' }}>
            <div
              className="rounded-xl bg-white/[0.07] flex items-center justify-center overflow-hidden border border-white/[0.08]"
              style={{ width: 'clamp(32px, 28px + 0.8vw, 44px)', height: 'clamp(32px, 28px + 0.8vw, 44px)' }}
            >
              <img src="/branding/minylogo.png" alt="miny y0" className="object-contain" style={{ width: 'clamp(24px, 20px + 0.8vw, 36px)', height: 'clamp(24px, 20px + 0.8vw, 36px)' }} />
            </div>
            <div>
              <h1 className="font-display font-extrabold tracking-tight leading-none" style={{ fontSize: 'clamp(0.875rem, 0.75rem + 0.4vw, 1.25rem)', color: 'var(--text-primary)' }}>y0</h1>
              <p className="uppercase tracking-[0.2em] font-medium mt-0.5" style={{ fontSize: 'clamp(8px, 7px + 0.2vw, 11px)', color: 'var(--text-muted)' }}>Music Intelligence</p>
            </div>
          </div>

          {/* Desktop: genre pills inline */}
          <div className="hidden md:flex items-center" style={{ gap: 'clamp(0.25rem, 0.15rem + 0.2vw, 0.5rem)' }}>
            {genres.map((genre) => (
              <button
                key={genre.id}
                onClick={() => setSelectedGenre(genre.id)}
                className={`rounded-full font-semibold uppercase tracking-[0.08em] transition-all duration-250 ${
                  selectedGenre === genre.id
                    ? `bg-gradient-to-r ${genre.gradient} text-white shadow-lg`
                    : ''
                }`}
                style={selectedGenre !== genre.id 
                  ? { color: 'var(--pill-text)', background: 'transparent', padding: 'clamp(0.25rem, 0.2rem + 0.2vw, 0.5rem) clamp(0.75rem, 0.5rem + 0.5vw, 1.25rem)', fontSize: 'clamp(10px, 9px + 0.2vw, 13px)' }
                  : { padding: 'clamp(0.25rem, 0.2rem + 0.2vw, 0.5rem) clamp(0.75rem, 0.5rem + 0.5vw, 1.25rem)', fontSize: 'clamp(10px, 9px + 0.2vw, 13px)' }
                }
              >
                {genre.label}
              </button>
            ))}
          </div>

          <div className="flex items-center" style={{ gap: 'clamp(0.125rem, 0.1rem + 0.15vw, 0.375rem)' }}>
            <button
              onClick={toggleTheme}
              className="rounded-full transition-all flex items-center justify-center"
              style={{ ...fluidBtn, color: 'var(--action-text)' }}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? <Sun style={fluidIcon} /> : <Moon style={fluidIcon} />}
            </button>
            <button
              onClick={() => fetchArticles(selectedGenre)}
              className="hidden md:flex rounded-full transition-all items-center justify-center"
              style={{ ...fluidBtn, color: 'var(--action-text)' }}
              disabled={loading}
              aria-label="Refresh articles"
            >
              <RefreshCw style={fluidIcon} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
              onClick={() => {
                setShowMenu(false);
                setShowBookmarks(true);
              }}
              className="relative rounded-full transition-all flex items-center justify-center"
              style={fluidBtn}
              aria-label="View bookmarks"
            >
              <Bookmark style={fluidIcon} className={`transition-all ${
                bookmarks.length > 0
                  ? 'text-amber-400 fill-amber-400'
                  : ''
              }`} />
              {bookmarks.length > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-rose-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center animate-scale-in">
                  {bookmarks.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setShowMenu(true)}
              className="rounded-full transition-all flex items-center justify-center md:hidden"
              style={{ ...fluidBtn, color: 'var(--action-text)' }}
              aria-label="Open menu"
            >
              <Menu style={fluidIcon} />
            </button>
          </div>
        </div>

        {/* Mobile: genre pills row */}
        <div className="md:hidden px-4 pb-3 flex items-center gap-2">
          <div className="flex gap-1.5 overflow-x-auto scrollbar-hide flex-1">
            {genres.map((genre) => (
              <button
                key={genre.id}
                onClick={() => setSelectedGenre(genre.id)}
                className={`px-3.5 py-1.5 rounded-full text-[11px] font-semibold whitespace-nowrap transition-all duration-250 ${
                  selectedGenre === genre.id
                    ? `bg-gradient-to-r ${genre.gradient} text-white shadow-lg`
                    : ''
                }`}
                style={selectedGenre !== genre.id ? { background: 'var(--pill-bg)', color: 'var(--pill-text)' } : undefined}
              >
                {genre.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => fetchArticles(selectedGenre)}
            className="p-2 rounded-full transition-all min-w-[36px] min-h-[36px] flex items-center justify-center shrink-0"
            style={{ background: 'var(--action-bg)', color: 'var(--action-text)' }}
            disabled={loading}
            aria-label="Refresh articles"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {/* ─── Main Content ─── */}
      <div className="flex-1 overflow-hidden">
        {loading ? (
          /* Loading skeleton */
          <div className="h-full overflow-y-auto scrollbar-hide md:flex md:flex-col lg:flex-row md:mx-auto" style={{ padding: 'clamp(1rem, 0.75rem + 0.75vw, 1.5rem)', maxWidth: 'clamp(700px, 60vw + 200px, 1600px)', gap: 'clamp(1.25rem, 1rem + 0.75vw, 2rem)' }}>
            <div className="lg:flex-[2] min-w-0">
              <ArticleSkeleton variant="featured" />
            </div>
            <div className="hidden md:grid grid-cols-2 lg:grid-cols-1 gap-3 mt-4 lg:mt-0 flex-1 min-w-0">
              <ArticleSkeleton variant="compact" />
              <ArticleSkeleton variant="compact" />
              <ArticleSkeleton variant="compact" />
              <ArticleSkeleton variant="compact" />
            </div>
          </div>
        ) : (
          /* ─── Mobile layout ─── */
          <>
            <div
              ref={containerRef}
              className="h-full md:hidden flex flex-col overflow-hidden relative"
              onTouchStart={onTouchStart}
              onTouchMove={onTouchMove}
              onTouchEnd={onTouchEnd}
            >
              <div
                ref={contentRef}
                key={currentArticle?.id}
                className={`flex-1 flex flex-col overflow-y-auto overflow-x-hidden scrollbar-hide animate-crossfade ${isDragging ? 'cursor-grabbing' : ''}`}
              >
                {/* Hero image — full bleed, adapts to screen */}
                <div className="relative h-[36vh] shrink-0 overflow-hidden">
                  <LazyArticleImage
                    articleId={currentArticle.id}
                    imageSource={currentArticle.imageSource}
                    primaryGenre={currentArticle.primaryGenre}
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute inset-0" style={{ background: `linear-gradient(to bottom, var(--gradient-overlay-top), transparent, var(--gradient-overlay-bottom-solid))` }} />
                  <div className="absolute bottom-0 left-0 right-0 px-5 pb-4">
                    <h2
                      onClick={() => toggleBookmark(currentArticle.id)}
                      className="font-display font-extrabold tracking-[-0.02em] leading-[1.12] text-white cursor-pointer select-none drop-shadow-[0_2px_12px_rgba(0,0,0,0.5)]"
                      style={{ fontSize: 'clamp(1.25rem, 1rem + 2vw, 1.75rem)' }}
                    >
                      {currentArticle.title}
                      {bookmarks.includes(currentArticle.id) && (
                        <Bookmark className="inline-block w-5 h-5 ml-2 text-amber-400 fill-amber-400 align-text-top" />
                      )}
                    </h2>
                  </div>
                </div>

                {/* Below the fold */}
                <div className="px-5 pt-3 pb-2 flex flex-col gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2.5 py-[3px] rounded-full text-[10px] font-bold uppercase tracking-[0.1em] bg-gradient-to-r ${genreGradient(currentArticle.primaryGenre)} text-white`}>
                      {currentArticle.primaryGenre}
                    </span>
                    {currentArticle.location && locationFlag(currentArticle.location) && (
                      <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
                        {locationFlag(currentArticle.location)}
                      </span>
                    )}
                    <span className="text-[10px] uppercase tracking-[0.14em] font-medium" style={{ color: 'var(--text-muted)' }}>
                      {currentArticle.source}
                    </span>
                    <span className="w-[3px] h-[3px] rounded-full" style={{ background: 'var(--text-faint)' }} />
                    <span className="text-[10px] uppercase tracking-[0.14em] font-medium" style={{ color: 'var(--text-muted)' }}>
                      {new Date(currentArticle.publishedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                    </span>
                  </div>

                  <p className="font-light leading-[1.6] tracking-[0.01em]" style={{ fontSize: 'clamp(0.8rem, 0.75rem + 0.5vw, 0.9rem)', color: 'var(--text-secondary)' }}>
                    {currentArticle.summary}
                  </p>

                  {(() => {
                    const epkUrl = epkReady ? (getEpkUrl(currentArticle.artistNames) || findEpkInText(currentArticle.title + ' ' + currentArticle.summary)) : null;
                    return epkUrl ? (
                      <a
                        href={epkUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 self-start px-3 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-[0.1em]"
                        style={{ background: 'var(--accent, #6366f1)', color: '#fff', textDecoration: 'none' }}
                      >
                        Discover Artist <ExternalLink size={10} />
                      </a>
                    ) : null;
                  })()}
                </div>
              </div>

              {/* Actions — pinned at bottom, always visible */}
              <div className="shrink-0" style={{ padding: 'clamp(0.5rem, 0.4rem + 0.3vw, 0.75rem) clamp(1rem, 0.75rem + 0.5vw, 1.5rem)', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-primary)' }}>
                {renderActions()}
              </div>
            </div>

            {/* Carousel dots — mobile */}
            <div className="md:hidden shrink-0" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              {renderDots()}
            </div>

            {/* ─── Desktop layout ─── */}
            <div className="hidden md:flex h-full mx-auto flex-col lg:flex-row" style={{ maxWidth: 'clamp(700px, 60vw + 200px, 1600px)', padding: 'clamp(1rem, 0.75rem + 0.75vw, 1.5rem) clamp(1.25rem, 1rem + 1vw, 2rem)', gap: 'clamp(1.25rem, 1rem + 0.75vw, 2rem)' }}>
              {/* Left: featured article (full width on md, 2/3 on lg+) */}
              <div className="lg:flex-[2] min-w-0 overflow-y-auto scrollbar-hide shrink-0 lg:shrink">
                <article
                  key={currentArticle?.id}
                  className="rounded-2xl overflow-hidden animate-crossfade"
                  style={{ background: 'var(--card-bg)', boxShadow: 'var(--shadow-featured)' }}
                >
                  <div className="relative aspect-[16/9] overflow-hidden">
                    <LazyArticleImage
                      articleId={currentArticle.id}
                      imageSource={currentArticle.imageSource}
                      primaryGenre={currentArticle.primaryGenre}
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0" style={{ background: `linear-gradient(to bottom, var(--gradient-overlay-top), transparent, var(--gradient-overlay-bottom))` }} />
                    <div className="absolute bottom-0 left-0 right-0" style={{ padding: 'clamp(1.25rem, 1rem + 1vw, 2rem)' }}>
                      <div className="flex items-center gap-2.5" style={{ marginBottom: 'clamp(0.625rem, 0.5rem + 0.3vw, 1rem)' }}>
                        <span className={`px-3 py-[3px] rounded-full text-[10px] font-bold uppercase tracking-[0.1em] bg-gradient-to-r ${genreGradient(currentArticle.primaryGenre)} text-white`}>
                          {currentArticle.primaryGenre}
                        </span>
                        {currentArticle.location && locationFlag(currentArticle.location) && (
                          <span className="text-[14px]" style={{ color: 'var(--text-secondary)' }}>
                            {locationFlag(currentArticle.location)}
                          </span>
                        )}
                        <span className="px-3 py-[3px] rounded-full text-[10px] tracking-[0.08em] backdrop-blur-md uppercase font-medium" style={{ color: 'var(--text-secondary)', background: 'var(--action-bg)' }}>
                          {currentArticle.source}
                        </span>
                      </div>
                      <h2
                        onClick={() => toggleBookmark(currentArticle.id)}
                        className="font-display font-extrabold tracking-[-0.025em] leading-[1.08] text-white cursor-pointer select-none hover:text-white/90 transition-colors drop-shadow-[0_2px_16px_rgba(0,0,0,0.4)]"
                        style={{ fontSize: 'clamp(1.5rem, 1.2rem + 1.5vw, 2.5rem)' }}
                      >
                        {currentArticle.title}
                        {bookmarks.includes(currentArticle.id) && (
                          <Bookmark className="inline-block w-7 h-7 ml-2 text-amber-400 fill-amber-400 align-text-top" />
                        )}
                      </h2>
                    </div>
                  </div>

                  <div style={{ padding: 'clamp(1.25rem, 1rem + 1vw, 2rem)', display: 'flex', flexDirection: 'column', gap: 'clamp(0.875rem, 0.75rem + 0.4vw, 1.25rem)' }}>
                    {/* Summary — always fully visible */}
                    <p className="font-light leading-[1.75] tracking-[0.01em] max-w-[64ch]" style={{ fontSize: 'clamp(0.9rem, 0.85rem + 0.25vw, 1.05rem)', color: 'var(--text-secondary)' }}>
                      {currentArticle.summary}
                    </p>

                    <div className="flex items-center justify-between pt-3" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <span className="text-[10px] uppercase tracking-[0.16em] font-medium" style={{ color: 'var(--text-muted)' }}>
                        {new Date(currentArticle.publishedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                        {(() => {
                          const epkUrl = epkReady ? (getEpkUrl(currentArticle.artistNames) || findEpkInText(currentArticle.title + ' ' + currentArticle.summary)) : null;
                          return epkUrl ? (
                            <>
                              <span className="mx-2.5" style={{ color: 'var(--text-faint)' }}>·</span>
                              <a
                                href={epkUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 font-bold"
                                style={{ color: 'var(--accent, #6366f1)', textDecoration: 'none', letterSpacing: '0.08em' }}
                                onClick={(e) => e.stopPropagation()}
                              >
                                Discover Artist <ExternalLink size={9} />
                              </a>
                            </>
                          ) : (
                            <>
                              <span className="mx-2.5" style={{ color: 'var(--text-faint)' }}>·</span>
                              {currentArticle.readTime}s read
                            </>
                          );
                        })()}
                      </span>
                      {renderActions()}
                    </div>
                  </div>
                </article>
              </div>

              {/* Right: sidebar list on lg+, grid below on md only */}
              <aside className="flex-1 min-w-0 flex flex-col">
                <div className="flex items-center justify-between" style={{ marginBottom: 'clamp(0.625rem, 0.5rem + 0.3vw, 1rem)' }}>
                  <h3 className="font-display font-bold uppercase tracking-[0.16em]" style={{ fontSize: 'clamp(10px, 9px + 0.2vw, 13px)', color: 'var(--text-quaternary)' }}>More Stories</h3>
                  <span className="tabular-nums" style={{ fontSize: 'clamp(9px, 8px + 0.15vw, 12px)', color: 'var(--text-muted)' }}>{filteredArticles.length} articles</span>
                </div>
                <div className="flex-1 overflow-y-auto scrollbar-hide">
                  <div className="grid grid-cols-2 lg:grid-cols-1" style={{ gap: 'clamp(0.5rem, 0.4rem + 0.3vw, 0.875rem)' }}>
                    {filteredArticles.map((article, idx) => {
                      const active = article.id === currentArticle?.id;
                      return (
                        <button
                          key={article.id}
                          onClick={() => {
                            setCurrentIndex(idx);
                            trackEvent('desktop_expand', article.id);
                          }}
                          className="w-full group card-hover rounded-xl overflow-hidden text-left transition-all duration-250"
                          style={active
                            ? { background: 'var(--card-bg-active)', boxShadow: `var(--shadow-card), inset 0 0 0 1px var(--card-border-active)` }
                            : { background: 'var(--card-bg)', boxShadow: `0 0 0 1px var(--card-border)` }
                          }
                        >
                          <div className="relative aspect-[2/1] overflow-hidden">
                            <LazyArticleImage
                              articleId={article.id}
                              imageSource={article.imageSource}
                              primaryGenre={article.primaryGenre}
                              className="w-full h-full object-cover transition-transform duration-600 group-hover:scale-105"
                            />
                            <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0.05), transparent)' }} />
                            <span className={`absolute top-2.5 left-2.5 px-2 py-[2px] rounded-full text-[9px] font-bold uppercase tracking-[0.1em] bg-gradient-to-r ${genreGradient(article.primaryGenre)} text-white`}>
                              {article.primaryGenre}
                            </span>
                          </div>
                          <div style={{ padding: 'clamp(0.625rem, 0.5rem + 0.3vw, 0.875rem) clamp(0.75rem, 0.6rem + 0.3vw, 1rem)', display: 'flex', flexDirection: 'column', gap: 'clamp(0.25rem, 0.2rem + 0.15vw, 0.5rem)' }}>
                            <p className="font-display font-bold leading-snug text-white/90 line-clamp-2 tracking-[-0.01em]" style={{ fontSize: 'clamp(12px, 11px + 0.2vw, 15px)' }}>{article.title}</p>
                            <p className="uppercase tracking-[0.12em] text-white/25 font-medium" style={{ fontSize: 'clamp(9px, 8px + 0.15vw, 12px)' }}>{article.source}</p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </aside>
            </div>
          </>
        )}
      </div>

      {/* ─── Bookmarks Drawer ─── */}
      {showBookmarks && (
        <div className="fixed inset-0 z-50 animate-fade-in">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowBookmarks(false)}
          />
          <div className="absolute right-0 top-0 bottom-0 w-full sm:max-w-md bg-[#08080d] border-l border-white/[0.06] animate-slide-in-up flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06] shrink-0">
              <div>
                <h2 className="font-display text-lg font-bold">Bookmarks</h2>
                <p className="text-[11px] text-white/30 mt-0.5">
                  {bookmarks.length} {bookmarks.length === 1 ? 'article' : 'articles'} saved
                </p>
              </div>
              <button
                onClick={() => setShowBookmarks(false)}
                className="p-2 rounded-full hover:bg-white/[0.08] transition-all min-w-[36px] min-h-[36px] flex items-center justify-center"
                aria-label="Close bookmarks"
              >
                <X className="w-5 h-5 text-white/60" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 scrollbar-hide">
              {bookmarks.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 rounded-full bg-white/[0.04] flex items-center justify-center mb-4">
                    <Bookmark className="w-8 h-8 text-white/15" />
                  </div>
                  <p className="text-white/60 text-base font-medium mb-2">No bookmarks yet</p>
                  <p className="text-white/35 text-sm">Articles you bookmark will appear here</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {articles.filter(a => bookmarks.includes(a.id)).map((article, index) => (
                    <div
                      key={article.id}
                      className="group p-4 rounded-2xl bg-white/[0.04] hover:bg-white/[0.07] cursor-pointer transition-all duration-200 animate-slide-in-up"
                      style={{ animationDelay: `${index * 50}ms` }}
                      onClick={() => {
                        const idx = articles.findIndex(a => a.id === article.id);
                        setCurrentIndex(idx);
                        setShowBookmarks(false);
                      }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider mb-2 bg-gradient-to-r ${genreGradient(article.primaryGenre)} text-white`}>
                            {article.primaryGenre}
                          </span>
                          <h3 className="text-white text-sm font-semibold leading-snug mb-1.5 line-clamp-2">
                            {article.title}
                          </h3>
                          <p className="text-white/45 text-xs line-clamp-2 font-light">
                            {article.summary}
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleBookmark(article.id);
                          }}
                          className="p-2 rounded-full bg-white/[0.04] hover:bg-red-500/20 text-white/30 hover:text-red-400 transition-all duration-200 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 min-w-[32px] min-h-[32px] flex items-center justify-center shrink-0"
                          aria-label="Remove bookmark"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ─── Slide-out Menu ─── */}
      {showMenu && (
        <div className="fixed inset-0 z-[60] animate-fade-in">
          <div
            className="absolute inset-0 bg-black/65 backdrop-blur-sm"
            onClick={() => setShowMenu(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-[84vw] max-w-sm bg-[#08080d] border-r border-white/[0.06] p-5 flex flex-col gap-6 animate-slide-in-left">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-white/10 border border-white/[0.12] flex items-center justify-center overflow-hidden">
                  <img src="/branding/minylogo.png" alt="miny y0" className="w-8 h-8 object-contain" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white tracking-tight">y0</p>
                  <p className="text-[11px] text-white/40">brand menu</p>
                </div>
              </div>
              <button
                onClick={() => setShowMenu(false)}
                className="p-2 rounded-full hover:bg-white/[0.08]"
                aria-label="Close menu"
              >
                <X className="w-4 h-4 text-white/60" />
              </button>
            </div>

            <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <img src="/branding/minylogo.png" alt="Miny logo" className="h-8 w-auto object-contain" />
                <span className="text-sm font-semibold text-white/90">miny</span>
              </div>
              <div className="flex items-center gap-2">
                <img src="/branding/velab-logo.png" alt="VE Lab logo" className="h-8 w-auto object-contain opacity-90" />
                <span className="text-sm font-semibold text-white/90">VE Lab</span>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-[0.14em] text-white/40">Explore</p>
              <nav className="space-y-2">
                {[
                  { href: 'https://minyvinyl.com', name: 'Miny Vinyl', sub: 'Main platform', icon: <img src="/branding/minylogo.png" alt="" className="h-6 w-6 object-contain" /> },
                  { href: 'https://velab.org', name: 'VE Lab', sub: 'Studio + research', icon: <img src="/branding/velab-logo.png" alt="" className="h-6 w-6 object-contain" /> },
                  { href: 'https://rapidconnect.minyvinyl.com', name: 'RapidConnect', sub: 'rapidconnect.minyvinyl.com', icon: <div className="h-6 w-6 rounded-lg bg-cyan-500/20 text-cyan-300 text-[10px] font-bold grid place-items-center">R</div> },
                  { href: 'https://minyfy.minyvinyl.com', name: 'MINYfy', sub: 'minyfy.minyvinyl.com', icon: <div className="h-6 w-6 rounded-lg bg-fuchsia-500/20 text-fuchsia-300 text-[10px] font-bold grid place-items-center">M</div> },
                  { href: 'https://skills.minyvinyl.com', name: 'Strat by M', sub: 'skills.minyvinyl.com', icon: <div className="h-6 w-6 rounded-lg bg-amber-500/20 text-amber-300 text-[10px] font-bold grid place-items-center">S</div> },
                ].map((link) => (
                  <a
                    key={link.href}
                    href={link.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between rounded-xl border border-white/[0.08] bg-white/[0.03] p-3 text-white/90 transition hover:bg-white/[0.08]"
                    aria-label={`Open ${link.name}`}
                  >
                    <span className="flex items-center gap-3">
                      {link.icon}
                      <span>
                        <span className="block text-sm font-semibold">{link.name}</span>
                        <span className="block text-xs text-white/40">{link.sub}</span>
                      </span>
                    </span>
                    <ExternalLink className="h-4 w-4 text-white/30" />
                  </a>
                ))}
              </nav>
            </div>

            <div className="mt-auto space-y-2">
              <p className="text-[11px] uppercase tracking-[0.14em] text-white/40">Actions</p>
              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-3">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      setShowBookmarks(true);
                    }}
                    className="flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2.5 text-sm font-medium text-white/90 transition hover:bg-white/[0.08]"
                    aria-label="Open bookmarks"
                  >
                    <span className="inline-flex items-center gap-2">
                      <Bookmark className={`w-4 h-4 ${bookmarks.length > 0 ? 'text-amber-400 fill-amber-400' : 'text-white/60'}`} />
                      Bookmarks ({bookmarks.length})
                    </span>
                  </button>
                  <button
                    onClick={() => {
                      fetchArticles(selectedGenre);
                      setShowMenu(false);
                    }}
                    className="rounded-xl border border-white/[0.08] bg-white/[0.04] p-2.5 text-white/60 transition hover:bg-white/[0.08]"
                    aria-label="Refresh feed"
                  >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-white/30">Live music headlines from the miny-ven VM scraper.</p>
            </div>
          </div>
        </div>
      )}

      {/* ─── Toast ─── */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

export default App;
