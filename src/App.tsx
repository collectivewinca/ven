import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import type { MusicNewsArticle, Genre } from './types/news';
import { Bookmark, Music, X, ExternalLink, RefreshCw, Menu, Sun, Moon } from 'lucide-react';
import { ArticleSkeleton } from './components/ArticleSkeleton';
import { ArticleCard } from './components/ArticleCard';
import { ArticleGridItem } from './components/ArticleGridItem';
import { Toast } from './components/Toast';
import { PullToRefresh } from './components/PullToRefresh';
import { isCleanHeadline } from './hooks/useArticleHelpers';
import { useArtistEpk } from './hooks/useArtistEpk';
import { fetchArticlesFromFirestore } from './utils/firestore';

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
  const [pullDistance, setPullDistance] = useState(0);
  const [isPulling, setIsPulling] = useState(false);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [audioLoading, setAudioLoading] = useState(false);
  const [audioArticleId, setAudioArticleId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [displayedSidebarCount, setDisplayedSidebarCount] = useState(20);

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

  const containerRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const bedNodesRef = useRef<{ oscillators: OscillatorNode[]; gain: GainNode } | null>(null);
  const wheelLockRef = useRef(false);

  // ---------- Data fetching ----------

  const fetchArticles = useCallback(async (genre: Genre = 'all') => {
    setLoading(true);
    setArticles([]);

    try {
      const filtered = await fetchArticlesFromFirestore(genre);
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

  // ---------- EPK resolution (RapidConnect) ----------

  // useArtistEpk batch-fetches sm_musicians from PocketBase (published-only)
  // and builds an in-memory name→EPK index. findEpkInText scans free text
  // against that index and returns the artist's EPK URL when an article
  // mentions a published musician. Embedded fallback + localStorage cache
  // hydrate the index before the PB fetch completes.
  const { findEpkInText, ready: epkReady } = useArtistEpk();

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

  // Filter to clean headlines only
  const cleanArticles = articles.filter(a => isCleanHeadline(a.title));
  const filteredArticles = selectedGenre === 'all'
    ? cleanArticles
    : cleanArticles.filter(a => a.primaryGenre === selectedGenre);

  // Resolve EPK URLs against the PocketBase-backed artist index. Re-runs
  // when the PB index hydrates (epkReady flips) without re-fetching
  // Firestore. findEpkInText scans title + summary for a known published
  // musician name and returns their EPK URL on rapidconnect.minyvinyl.com.
  const articlesWithEpk = useMemo(
    () => filteredArticles.map((a) => {
      if (a.epkUrl) return a;
      const text = `${a.title} ${a.summary}`;
      const url = findEpkInText(text);
      if (!url) return a;
      return { ...a, epkUrl: url, epkStatus: 'ready' as const };
    }),
    [filteredArticles, findEpkInText, epkReady]
  );

  const currentArticle = articlesWithEpk[currentIndex];

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

  const handleDesktopNavigate = useCallback((direction: 'next' | 'prev') => {
    if (!filteredArticles.length) return;

    if (direction === 'next' && currentIndex < filteredArticles.length - 1) {
      setCurrentIndex(prev => prev + 1);
      if (currentArticle) trackEvent('desktop_next', currentArticle.id);
    }

    if (direction === 'prev' && currentIndex > 0) {
      setCurrentIndex(prev => prev - 1);
      if (currentArticle) trackEvent('desktop_prev', currentArticle.id);
    }
  }, [currentArticle, currentIndex, filteredArticles.length, trackEvent]);

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

  // ---------- Pull-to-refresh (swipe nav handled by ArticleCard) ----------
  const [touchStart, setTouchStart] = useState<number | null>(null);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    const touchY = e.targetTouches[0].clientY;
    setTouchStart(touchY);
    if (containerRef.current && containerRef.current.scrollTop === 0) {
      setIsPulling(true);
    }
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (!touchStart) return;
    const touchY = e.targetTouches[0].clientY;
    const pullDist = touchStart - touchY;
    if (pullDist < 0 && containerRef.current?.scrollTop === 0) {
      setPullDistance(Math.abs(pullDist));
    }
  }, [touchStart]);

  const onTouchEnd = useCallback(() => {
    setIsPulling(false);
    if (pullDistance > 80) {
      fetchArticles(selectedGenre);
      setToast('Refreshing content...');
    }
    setPullDistance(0);
    setTouchStart(null);
  }, [pullDistance, fetchArticles, selectedGenre]);

  // ---------- Keyboard & effects ----------

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') handleDesktopNavigate('prev');
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') handleDesktopNavigate('next');
      if (e.key === 'b') setShowBookmarks(prev => !prev);
      if (e.key === 'Escape') {
        setShowBookmarks(false);
        setShowMenu(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleDesktopNavigate]);

  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      if (window.innerWidth < 768) return;
      if (showBookmarks || showMenu || loading || filteredArticles.length <= 1) return;

      const target = e.target as HTMLElement | null;
      if (target?.closest('aside')) return;

      if (Math.abs(e.deltaY) < 24 || wheelLockRef.current) return;

      wheelLockRef.current = true;
      if (e.deltaY > 0) handleDesktopNavigate('next');
      else handleDesktopNavigate('prev');

      window.setTimeout(() => {
        wheelLockRef.current = false;
      }, 420);
    };

    window.addEventListener('wheel', handleWheel, { passive: true });
    return () => window.removeEventListener('wheel', handleWheel);
  }, [filteredArticles.length, handleDesktopNavigate, loading, showBookmarks, showMenu]);

  useEffect(() => {
    setCurrentIndex(0);
    setDisplayedSidebarCount(20);
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

  // ---------- Render ----------

  const fluidBtn: React.CSSProperties = {
    padding: 'clamp(0.5rem, 0.35rem + 0.5vw, 0.75rem)',
    minWidth: 'clamp(36px, 32px + 1vw, 48px)',
    minHeight: 'clamp(36px, 32px + 1vw, 48px)',
  };
  const fluidIcon: React.CSSProperties = {
    width: 'clamp(16px, 14px + 0.5vw, 22px)',
    height: 'clamp(16px, 14px + 0.5vw, 22px)',
  };

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
          <>
            {/* Mobile: ArticleCard with internal swipe + pull-to-refresh */}
            <div
              className="h-full md:hidden flex flex-col overflow-hidden relative"
              onTouchStart={onTouchStart}
              onTouchMove={onTouchMove}
              onTouchEnd={onTouchEnd}
            >
              <div className="flex-1 overflow-hidden">
                <ArticleCard
                  article={currentArticle}
                  onNext={() => handleDesktopNavigate('next')}
                  onPrev={() => handleDesktopNavigate('prev')}
                  bookmarks={bookmarks}
                  toggleBookmark={toggleBookmark}
                  handleShare={handleShare}
                  handleListen={handleListen}
                  isAudioPlaying={isAudioPlaying}
                  audioLoading={audioLoading}
                  audioArticleId={audioArticleId}
                />
              </div>
            </div>

            {/* Carousel dots — mobile */}
            <div className="md:hidden shrink-0" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              {renderDots()}
            </div>

            {/* Desktop layout */}
            <div className="hidden md:flex h-full mx-auto flex-col lg:flex-row" style={{ maxWidth: 'clamp(700px, 60vw + 200px, 1600px)', padding: 'clamp(1rem, 0.75rem + 0.75vw, 1.5rem) clamp(1.25rem, 1rem + 1vw, 2rem)', gap: 'clamp(1.25rem, 1rem + 0.75vw, 2rem)' }}>
              {/* Left: featured article */}
              <div className="lg:flex-[2] min-w-0 overflow-y-auto scrollbar-hide shrink-0 lg:shrink">
                <ArticleCard
                  article={currentArticle}
                  onNext={() => handleDesktopNavigate('next')}
                  onPrev={() => handleDesktopNavigate('prev')}
                  bookmarks={bookmarks}
                  toggleBookmark={toggleBookmark}
                  handleShare={handleShare}
                  handleListen={handleListen}
                  isAudioPlaying={isAudioPlaying}
                  audioLoading={audioLoading}
                  audioArticleId={audioArticleId}
                />
              </div>

              {/* Right: sidebar with ArticleGridItem */}
              <aside className="flex-1 min-w-0 flex flex-col">
                <div className="flex items-center justify-between" style={{ marginBottom: 'clamp(0.625rem, 0.5rem + 0.3vw, 1rem)' }}>
                  <button 
                    onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                    className="flex items-center gap-2"
                  >
                    <h3 className="font-display font-bold uppercase tracking-[0.16em]" style={{ fontSize: 'clamp(10px, 9px + 0.2vw, 13px)', color: 'var(--text-quaternary)' }}>
                      More Stories
                    </h3>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {sidebarCollapsed ? '▶' : '▼'}
                    </span>
                  </button>
                  <span className="tabular-nums" style={{ fontSize: 'clamp(9px, 8px + 0.15vw, 12px)', color: 'var(--text-muted)' }}>
                    {filteredArticles.length} articles
                  </span>
                </div>
                
                {!sidebarCollapsed && (
                  <>
                    <div className="flex-1 overflow-y-auto scrollbar-hide">
                      <div 
                        className="grid grid-cols-2 lg:grid-cols-1" 
                        style={{ gap: 'clamp(0.5rem, 0.4rem + 0.3vw, 0.875rem)' }}
                      >
                        {articlesWithEpk
                          .filter(a => a.id !== currentArticle?.id && isCleanHeadline(a.title))
                          .slice(0, displayedSidebarCount)
                          .map((article) => (
                            <ArticleGridItem
                              key={article.id}
                              article={article}
                              onSelect={(id) => {
                                const idx = filteredArticles.findIndex(a => a.id === id);
                                if (idx !== -1) setCurrentIndex(idx);
                              }}
                              isActive={article.id === currentArticle?.id}
                            />
                          ))}
                      </div>
                    </div>
                    
                    {displayedSidebarCount < filteredArticles.filter(a => a.id !== currentArticle?.id).length && (
                      <button
                        onClick={() => setDisplayedSidebarCount(prev => prev + 20)}
                        className="mt-3 px-4 py-2 rounded-full text-sm font-medium transition-all"
                        style={{ background: 'var(--action-bg)', color: 'var(--text-secondary)' }}
                      >
                        Load {Math.min(20, filteredArticles.filter(a => a.id !== currentArticle?.id).length - displayedSidebarCount)} more
                      </button>
                    )}
                  </>
                )}
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
          <div
            className="absolute right-0 top-0 bottom-0 w-full sm:max-w-md animate-slide-in-up flex flex-col"
            style={{ background: 'var(--bg-drawer)', borderLeft: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}
          >
            <div className="flex items-center justify-between px-5 py-4 shrink-0" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
              <div>
                <h2 className="font-display text-lg font-bold">Bookmarks</h2>
                <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-quaternary)' }}>
                  {bookmarks.length} {bookmarks.length === 1 ? 'article' : 'articles'} saved
                </p>
              </div>
              <button
                onClick={() => setShowBookmarks(false)}
                className="p-2 rounded-full transition-all min-w-[36px] min-h-[36px] flex items-center justify-center"
                style={{ color: 'var(--action-text)' }}
                aria-label="Close bookmarks"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 scrollbar-hide">
              {bookmarks.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ background: 'var(--action-bg)' }}>
                    <Bookmark className="w-8 h-8" style={{ color: 'var(--text-faint)' }} />
                  </div>
                  <p className="text-base font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>No bookmarks yet</p>
                  <p className="text-sm" style={{ color: 'var(--text-quaternary)' }}>Articles you bookmark will appear here</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {articles.filter(a => bookmarks.includes(a.id)).map((article, index) => (
                    <div
                      key={article.id}
                      className="group p-4 rounded-2xl cursor-pointer transition-all duration-200 animate-slide-in-up"
                      style={{ background: 'var(--card-bg)', animationDelay: `${index * 50}ms` }}
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
                          <h3 className="text-sm font-semibold leading-snug mb-1.5 line-clamp-2" style={{ color: 'var(--text-primary)' }}>
                            {article.title}
                          </h3>
                          <p className="text-xs line-clamp-2 font-light" style={{ color: 'var(--text-tertiary)' }}>
                            {article.summary}
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleBookmark(article.id);
                          }}
                          className="p-2 rounded-full hover:bg-red-500/20 hover:text-red-400 transition-all duration-200 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 min-w-[32px] min-h-[32px] flex items-center justify-center shrink-0"
                          style={{ background: 'var(--action-bg)', color: 'var(--text-quaternary)' }}
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
          <div
            className="absolute left-0 top-0 bottom-0 w-[84vw] max-w-sm p-5 flex flex-col gap-6 animate-slide-in-left"
            style={{ background: 'var(--bg-drawer)', borderRight: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center overflow-hidden" style={{ background: 'var(--action-bg)', border: '1px solid var(--border-primary)' }}>
                  <img src="/branding/minylogo.png" alt="miny y0" className="w-8 h-8 object-contain" />
                </div>
                <div>
                  <p className="text-sm font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>y0</p>
                  <p className="text-[11px]" style={{ color: 'var(--text-quaternary)' }}>brand menu</p>
                </div>
              </div>
              <button
                onClick={() => setShowMenu(false)}
                className="p-2 rounded-full transition-all"
                style={{ color: 'var(--action-text)' }}
                aria-label="Close menu"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="rounded-2xl p-4 flex items-center justify-between" style={{ border: '1px solid var(--border-primary)', background: 'var(--card-bg)' }}>
              <div className="flex items-center gap-2">
                <img src="/branding/minylogo.png" alt="Miny logo" className="h-8 w-auto object-contain" />
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>miny</span>
              </div>
              <div className="flex items-center gap-2">
                <img src="/branding/velab-logo.png" alt="VE Lab logo" className="h-8 w-auto object-contain opacity-90" />
                <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>VE Lab</span>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-quaternary)' }}>Explore</p>
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
                    className="flex items-center justify-between rounded-xl p-3 transition"
                    style={{ border: '1px solid var(--border-primary)', background: 'var(--card-bg)', color: 'var(--text-primary)' }}
                    aria-label={`Open ${link.name}`}
                  >
                    <span className="flex items-center gap-3">
                      {link.icon}
                      <span>
                        <span className="block text-sm font-semibold">{link.name}</span>
                        <span className="block text-xs" style={{ color: 'var(--text-quaternary)' }}>{link.sub}</span>
                      </span>
                    </span>
                    <ExternalLink className="h-4 w-4" style={{ color: 'var(--text-quaternary)' }} />
                  </a>
                ))}
              </nav>
            </div>

            <div className="mt-auto space-y-2">
              <p className="text-[11px] uppercase tracking-[0.14em]" style={{ color: 'var(--text-quaternary)' }}>Actions</p>
              <div className="rounded-2xl p-3" style={{ border: '1px solid var(--border-primary)', background: 'var(--card-bg)' }}>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      setShowBookmarks(true);
                    }}
                    className="flex-1 rounded-xl px-3 py-2.5 text-sm font-medium transition"
                    style={{ border: '1px solid var(--border-primary)', background: 'var(--action-bg)', color: 'var(--text-primary)' }}
                    aria-label="Open bookmarks"
                  >
                    <span className="inline-flex items-center gap-2">
                      <Bookmark className={`w-4 h-4 ${bookmarks.length > 0 ? 'text-amber-400 fill-amber-400' : ''}`} style={bookmarks.length > 0 ? undefined : { color: 'var(--action-text)' }} />
                      Bookmarks ({bookmarks.length})
                    </span>
                  </button>
                  <button
                    onClick={() => {
                      fetchArticles(selectedGenre);
                      setShowMenu(false);
                    }}
                    className="rounded-xl p-2.5 transition"
                    style={{ border: '1px solid var(--border-primary)', background: 'var(--action-bg)', color: 'var(--action-text)' }}
                    aria-label="Refresh feed"
                  >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              </div>
              <p className="text-xs" style={{ color: 'var(--text-quaternary)' }}>Live music headlines from the miny-ven VM scraper.</p>
            </div>
          </div>
        </div>
      )}

      {/* ─── Footer (desktop only) ─── */}
      <footer
        className="hidden md:flex shrink-0 items-center justify-between z-10"
        style={{ borderTop: '1px solid var(--border-subtle)', padding: '0.5rem clamp(1.25rem, 1rem + 1vw, 2rem)', color: 'var(--text-muted)' }}
      >
        <span className="font-display font-bold tracking-tight" style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
          MINY Indie News
        </span>
        <div className="flex items-center gap-4" style={{ fontSize: '10px' }}>
          <a
            href="https://minyvinyl.com"
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors hover:underline"
            style={{ color: 'var(--text-muted)' }}
          >
            minyvinyl.com
          </a>
          <span style={{ color: 'var(--text-faint)' }}>·</span>
          <a
            href="https://velab.org"
            target="_blank"
            rel="noopener noreferrer"
            className="transition-colors hover:underline"
            style={{ color: 'var(--text-muted)' }}
          >
            velab.org
          </a>
        </div>
      </footer>

      {/* ─── Toast ─── */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

export default App;
