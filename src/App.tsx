import { useState, useEffect, useCallback, useRef } from 'react';
import type { Genre } from './types/news';
import { Bookmark, Share2, Mail, Heart, Music, X, ChevronUp, ChevronDown, ExternalLink, RefreshCw, Smartphone, MessageSquare, Send, Menu } from 'lucide-react';
import { LazyArticleImage } from './components/LazyArticleImage';
import { ArticleSkeleton } from './components/ArticleSkeleton';
import { Toast } from './components/Toast';
import { PullToRefresh } from './components/PullToRefresh';
import { useArticles } from './hooks/useArticles';

const genres: { id: Genre; label: string; gradient: string }[] = [
  { id: 'all', label: 'All', gradient: 'from-gray-600 to-gray-500' },
  { id: 'gospel', label: 'Gospel', gradient: 'from-orange-500 to-amber-500' },
  { id: 'hiphop', label: 'Hip-Hop', gradient: 'from-violet-600 to-indigo-600' },
  { id: 'pop', label: 'Pop', gradient: 'from-pink-500 to-rose-500' },
  { id: 'rock', label: 'Rock', gradient: 'from-red-600 to-orange-600' },
  { id: 'electronic', label: 'Electronic', gradient: 'from-cyan-600 to-blue-600' },
  { id: 'tech', label: 'Tech', gradient: 'from-emerald-600 to-teal-600' },
];

function App() {
  const { articles, loading, error, fetchArticles } = useArticles();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedGenre, setSelectedGenre] = useState<Genre>('all');
  const [bookmarks, setBookmarks] = useState<string[]>(() => {
    const saved = localStorage.getItem('miny-ven-bookmarks');
    return saved ? JSON.parse(saved) : [];
  });
  const [showBookmarks, setShowBookmarks] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [swipeDirection, setSwipeDirection] = useState<'up' | 'down' | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [touchStart, setTouchStart] = useState<number | null>(null);
  const [touchEnd, setTouchEnd] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isPulling, setIsPulling] = useState(false);
  const [showTextModal, setShowTextModal] = useState(false);
  const [smsPhone, setSmsPhone] = useState('');
  const [smsSending, setSmsSending] = useState(false);
  const [isDesktopViewport, setIsDesktopViewport] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.innerWidth >= 1024;
  });
  const [useDesktopShell, setUseDesktopShell] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.innerWidth >= 1024;
  });
  const contentRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentArticle = articles[currentIndex];

  useEffect(() => {
    if (error) setToast(`Error: ${error}`);
    else if (!loading && articles.length === 0) setToast('No articles found.');
  }, [error, loading, articles.length]);

  useEffect(() => {
    fetchArticles(selectedGenre);
  }, [fetchArticles, selectedGenre]);

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
    if (direction === 'up' && currentIndex < articles.length - 1) {
      setSwipeDirection('up');
      setTimeout(() => {
        setCurrentIndex(prev => prev + 1);
        setSwipeDirection(null);
        trackEvent('swipe_up', currentArticle.id);
      }, 300);
    } else if (direction === 'down' && currentIndex > 0) {
      setSwipeDirection('down');
      setTimeout(() => {
        setCurrentIndex(prev => prev - 1);
        setSwipeDirection(null);
      }, 300);
    }
  }, [currentIndex, articles.length, currentArticle, trackEvent]);

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
    } catch {
      console.log('Share cancelled');
    }
  }, [currentArticle, trackEvent]);

  const handleEmail = useCallback(() => {
    if (!currentArticle) return;
    const subject = encodeURIComponent(currentArticle.title);
    const body = encodeURIComponent(`${currentArticle.summary}\n\nRead more: ${currentArticle.sourceUrl}`);
    window.open(`mailto:?subject=${subject}&body=${body}`);
    trackEvent('email', currentArticle.id);
    setToast('Email client opened');
  }, [currentArticle, trackEvent]);

  const handleTextLink = useCallback(async () => {
    if (!currentArticle) return;
    const phone = smsPhone.trim();
    if (!phone) {
      setToast('Enter a phone number first.');
      return;
    }
    setSmsSending(true);
    try {
      const appUrl = import.meta.env.VITE_PUBLIC_APP_URL || window.location.origin;
      const payload = {
        to: phone,
        text: `Check this on miny-ven: ${currentArticle.title}\n${currentArticle.sourceUrl}\nApp: ${appUrl}`,
        articleTitle: currentArticle.title,
        articleUrl: currentArticle.sourceUrl,
      };
      const response = await fetch('/api/quo-sms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data?.error || 'Failed to send SMS');
      setShowTextModal(false);
      setSmsPhone('');
      trackEvent('text_link', currentArticle.id);
      setToast('Text sent successfully.');
    } catch (error: any) {
      const fallbackBody = encodeURIComponent(
        `Check this on miny-ven: ${currentArticle.title}\n${currentArticle.sourceUrl}`
      );
      window.open(`sms:${phone}?&body=${fallbackBody}`);
      setToast(error?.message ? `API failed (${error.message}). Opened SMS app.` : 'API failed. Opened SMS app.');
    } finally {
      setSmsSending(false);
    }
  }, [currentArticle, smsPhone, trackEvent]);

  // Touch handlers
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
      if (pullDist < 0) setPullDistance(Math.abs(pullDist));
    }
    if (!isPulling && touchStart && contentRef.current) {
      const diff = touchStart - touchY;
      contentRef.current.style.transform = `translateY(${-diff * 0.2}px)`;
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
    if (contentRef.current) {
      contentRef.current.style.transform = '';
      contentRef.current.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
      setTimeout(() => {
        if (contentRef.current) contentRef.current.style.transition = '';
      }, 300);
    }
    if (distance > 50) handleSwipe('up');
    else if (distance < -50) handleSwipe('down');
  }, [touchStart, touchEnd, pullDistance, handleSwipe, fetchArticles, selectedGenre]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'ArrowUp') handleSwipe('down');
      if (e.key === 'ArrowDown') handleSwipe('up');
      if (e.key === 'b') setShowBookmarks(prev => !prev);
      if (e.key === 'Escape') {
        setShowBookmarks(false);
        setShowMenu(false);
        setShowTextModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSwipe]);

  useEffect(() => {
    setCurrentIndex(0);
  }, [selectedGenre]);

  useEffect(() => {
    const onResize = () => {
      const desktop = window.innerWidth >= 1024;
      setIsDesktopViewport(desktop);
      if (!desktop) setUseDesktopShell(false);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const showDesktopShell = isDesktopViewport && useDesktopShell;
  const isDesktopGalleryMode = isDesktopViewport && !useDesktopShell;

  // ─── Desktop Gallery (light theme) ───────────────────────────
  const desktopGalleryContent = (
    <div className="h-[100dvh] overflow-hidden bg-gradient-to-br from-slate-50 via-white to-slate-100 text-slate-900">
      <div className="h-full overflow-y-auto scrollbar-hide">
        {/* Sticky Header */}
        <div className="sticky top-0 z-20 border-b border-slate-200 bg-white/80 backdrop-blur-xl">
          <div className="mx-auto max-w-[1400px] px-6 py-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="h-11 w-11 rounded-2xl border border-slate-200 bg-slate-100 p-2">
                  <img src="/branding/minylogo.png" alt="miny y0" className="h-full w-full object-contain" />
                </div>
                <div>
                  <h1 className="text-2xl font-black tracking-tight text-slate-900">y0</h1>
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Live Music Intelligence</p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => fetchArticles(selectedGenre)}
                  className="rounded-full border border-slate-200 bg-white p-2.5 transition hover:bg-slate-50 hover:border-slate-300"
                  disabled={loading}
                  aria-label="Refresh articles"
                >
                  <RefreshCw className={`h-4 w-4 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={() => setShowBookmarks(true)}
                  className="relative rounded-full border border-slate-200 bg-white p-2.5 transition hover:bg-slate-50"
                  aria-label="View bookmarks"
                >
                  <Bookmark className={`h-4 w-4 ${bookmarks.length ? 'fill-amber-500 text-amber-500' : 'text-slate-500'}`} />
                  {bookmarks.length > 0 && (
                    <span className="absolute -right-1 -top-1 grid h-4 w-4 place-items-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
                      {bookmarks.length}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setUseDesktopShell(prev => !prev)}
                  className={`rounded-full border p-2.5 transition ${
                    useDesktopShell
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-600'
                      : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                  }`}
                  aria-label={useDesktopShell ? 'Exit phone preview' : 'Phone preview'}
                >
                  <Smartphone className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {genres.map((genre) => (
                <button
                  key={genre.id}
                  onClick={() => setSelectedGenre(genre.id)}
                  className={`rounded-full px-4 py-1.5 text-xs font-semibold uppercase tracking-wider transition ${
                    selectedGenre === genre.id
                      ? `bg-gradient-to-r ${genre.gradient} text-white shadow-lg`
                      : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300'
                  }`}
                >
                  {genre.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Main Grid */}
        <div className="mx-auto grid max-w-[1400px] grid-cols-1 gap-6 px-4 sm:px-6 py-6 xl:grid-cols-12">
          {/* Featured Article — sticky on wide desktop */}
          <section className="xl:col-span-7 xl:sticky xl:top-[164px] xl:self-start xl:max-h-[calc(100dvh-164px-1.5rem)] xl:overflow-y-auto xl:scrollbar-hide">
            {loading ? (
              <ArticleSkeleton />
            ) : !currentArticle ? (
              <div className="rounded-3xl border border-slate-200 bg-white p-10 text-center text-slate-500">
                No articles available
              </div>
            ) : (
              <article className="overflow-hidden rounded-2xl sm:rounded-3xl border border-slate-200 bg-white shadow-lg">
                <div className="relative aspect-[4/3] sm:aspect-[3/2] xl:aspect-[2.5/1]">
                  <LazyArticleImage
                    articleId={currentArticle.id}
                    imageSource={currentArticle.imageSource}
                    primaryGenre={currentArticle.primaryGenre}
                    className="h-full w-full object-cover"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
                  <div className="absolute bottom-3 left-3 right-3 sm:bottom-4 sm:left-4 sm:right-4 flex items-center justify-between">
                    <span className={`rounded-full bg-gradient-to-r px-2.5 py-0.5 sm:px-3 sm:py-1 text-[10px] sm:text-[11px] font-bold uppercase tracking-wider text-white ${
                      genres.find(g => g.id === currentArticle.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                    }`}>
                      {currentArticle.primaryGenre}
                    </span>
                    <span className="rounded-full bg-black/40 px-2.5 py-0.5 sm:px-3 sm:py-1 text-[10px] sm:text-[11px] text-white/90 backdrop-blur-sm">{currentArticle.source}</span>
                  </div>
                </div>
                <div className="space-y-2 sm:space-y-3 p-4 sm:p-5 lg:p-6">
                  <h2 className="text-lg sm:text-xl lg:text-2xl font-extrabold leading-tight tracking-tight text-slate-900">{currentArticle.title}</h2>
                  <p className="text-sm sm:text-base leading-relaxed text-slate-600">{currentArticle.summary}</p>
                  <div className="flex items-center justify-between pt-2 sm:pt-3 text-xs sm:text-sm text-slate-500">
                    <span>{new Date(currentArticle.publishedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                    <a
                      href={currentArticle.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 sm:gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-medium text-slate-700 transition hover:bg-slate-100 hover:border-slate-300"
                      onClick={() => trackEvent('external_link', currentArticle.id)}
                    >
                      Read source <ExternalLink className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                    </a>
                  </div>
                </div>
              </article>
            )}
          </section>

          {/* More Stories sidebar */}
          <aside className="xl:col-span-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-[0.14em] text-slate-500">More Stories</h3>
              <span className="text-xs text-slate-400">{articles.length} total</span>
            </div>
            <div className="grid gap-3 grid-cols-2 lg:grid-cols-3 xl:grid-cols-2">
              {articles.map((article) => {
                const idx = articles.findIndex(a => a.id === article.id);
                const active = article.id === currentArticle?.id;
                return (
                  <button
                    key={article.id}
                    onClick={() => {
                      setCurrentIndex(idx);
                      trackEvent('desktop_expand', article.id);
                    }}
                    className={`group overflow-hidden rounded-2xl border text-left transition ${
                      active
                        ? 'border-indigo-300 bg-indigo-50 ring-1 ring-indigo-200'
                        : 'border-slate-200 bg-white hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md'
                    }`}
                  >
                    <div className="relative aspect-[16/10]">
                      <LazyArticleImage
                        articleId={article.id}
                        imageSource={article.imageSource}
                        primaryGenre={article.primaryGenre}
                        className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/10 to-transparent" />
                    </div>
                    <div className="space-y-1 p-3">
                      <p className="line-clamp-2 text-sm font-semibold leading-tight text-slate-900">{article.title}</p>
                      <p className="text-xs uppercase tracking-[0.08em] text-slate-500">{article.source}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>
        </div>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );

  // ─── Mobile / Shell Content (light theme) ───────────────────
  const appContent = !currentArticle && !loading ? (
    <div className="h-full bg-slate-50 flex items-center justify-center safe-area-top safe-area-bottom">
      <div className="text-center px-4">
        <Music className="w-16 h-16 text-slate-300 mx-auto mb-4" />
        <p className="text-slate-700 text-lg mb-2">No articles found</p>
        <p className="text-slate-500 text-sm">Run the scraper to populate Firebase with content</p>
        <button
          onClick={() => fetchArticles(selectedGenre)}
          className="mt-6 px-6 py-3 bg-slate-900 rounded-full text-white hover:bg-slate-800 transition-all"
        >
          Retry
        </button>
      </div>
    </div>
  ) : (
    <div className="h-full bg-slate-50 flex flex-col overflow-hidden safe-area-top safe-area-bottom">
      <PullToRefresh pullDistance={pullDistance} isPulling={isPulling} />

      {/* Header */}
      <header className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 glass z-50 border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-slate-100 flex items-center justify-center overflow-hidden border border-slate-200">
            <img src="/branding/minylogo.png" alt="miny y0" className="w-7 h-7 sm:w-8 sm:h-8 object-contain" />
          </div>
          <div>
            <h1 className="text-base sm:text-lg font-bold tracking-tight text-slate-900">y0</h1>
            <p className="text-xs text-slate-500">creator music intelligence</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setShowMenu(false);
              setShowBookmarks(true);
            }}
            className="relative group p-2.5 sm:p-3 rounded-full hover:bg-slate-100 transition-all duration-300 btn-press min-w-[44px] min-h-[44px] flex items-center justify-center"
            aria-label="View bookmarks"
          >
            <Bookmark className={`w-5 h-5 sm:w-6 sm:h-6 transition-all duration-300 ${
              bookmarks.length > 0
                ? 'text-amber-500 fill-amber-500 scale-110'
                : 'text-slate-400 group-hover:text-slate-700'
            }`} />
            {bookmarks.length > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 sm:w-5 sm:h-5 bg-red-500 text-white text-[9px] sm:text-[10px] font-bold rounded-full flex items-center justify-center animate-scale-in shadow-lg">
                {bookmarks.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setShowMenu(true)}
            className="group p-2.5 sm:p-3 rounded-full hover:bg-slate-100 transition-all duration-300 btn-press min-w-[44px] min-h-[44px] flex items-center justify-center"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5 sm:w-6 sm:h-6 text-slate-500 group-hover:text-slate-700" />
          </button>
        </div>
      </header>

      {/* Genre Filter */}
      <div className="px-4 sm:px-6 py-3 border-b border-slate-200 shrink-0 bg-white">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5 sm:gap-2 overflow-x-auto scrollbar-hide pb-1 flex-1">
            {genres.map((genre, index) => (
              <button
                key={genre.id}
                onClick={() => setSelectedGenre(genre.id)}
                className={`relative px-3 sm:px-5 py-2 rounded-full text-xs sm:text-sm font-medium whitespace-nowrap transition-all duration-300 btn-press min-h-[36px] sm:min-h-[40px] ${
                  selectedGenre === genre.id
                    ? `bg-gradient-to-r ${genre.gradient} text-white shadow-lg`
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800'
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {genre.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => fetchArticles(selectedGenre)}
            className="ml-2 p-2 rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 transition-all duration-300 min-w-[40px] min-h-[40px] flex items-center justify-center"
            disabled={loading}
            aria-label="Refresh articles"
          >
            <RefreshCw className={`w-4 h-4 sm:w-5 sm:h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div
        ref={containerRef}
        className="flex-1 relative overflow-y-auto overflow-x-hidden scrollbar-hide bg-slate-50"
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {/* Swipe Hints */}
        <div className="absolute inset-0 pointer-events-none z-10">
          <div className={`absolute top-4 left-1/2 -translate-x-1/2 transition-all duration-300 ${
            currentIndex > 0 ? 'opacity-30' : 'opacity-0'
          }`}>
            <ChevronUp className="w-6 h-6 sm:w-8 sm:h-8 text-slate-400 animate-pulse" />
          </div>
          <div className={`absolute bottom-28 sm:bottom-32 left-1/2 -translate-x-1/2 transition-all duration-300 ${
            currentIndex < articles.length - 1 ? 'opacity-30' : 'opacity-0'
          }`}>
            <ChevronDown className="w-6 h-6 sm:w-8 sm:h-8 text-slate-400 animate-pulse" />
          </div>
        </div>

        {/* Article Card */}
        <div
          ref={contentRef}
          className={`min-h-full transition-all duration-300 ${
            swipeDirection === 'up' ? 'animate-slide-up' :
            swipeDirection === 'down' ? 'animate-slide-down' :
            'animate-fade-in'
          } ${isDragging ? 'cursor-grabbing' : ''}`}
        >
          {loading ? (
            <ArticleSkeleton />
          ) : (
            <div className="min-h-full flex flex-col p-4 sm:p-6">
              <div className="relative aspect-[16/9] mb-4 rounded-2xl sm:rounded-3xl overflow-hidden bg-slate-200 shadow-lg card-hover group">
                <LazyArticleImage
                  articleId={currentArticle.id}
                  imageSource={currentArticle.imageSource}
                  primaryGenre={currentArticle.primaryGenre}
                  className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />

                <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] sm:text-xs font-bold uppercase tracking-[0.08em] bg-gradient-to-r ${
                    genres.find(g => g.id === currentArticle.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                  } text-white shadow-lg backdrop-blur-sm`}>
                    {currentArticle.primaryGenre}
                  </span>
                  <span className="px-2.5 py-1 rounded-full text-[11px] sm:text-xs font-medium text-white/95 bg-black/40 backdrop-blur-sm">
                    {currentArticle.source}
                  </span>
                </div>
              </div>

              <h2
                onClick={() => toggleBookmark(currentArticle.id)}
                className="text-lg sm:text-xl md:text-2xl font-bold text-slate-900 mb-3 leading-tight tracking-tight cursor-pointer hover:text-slate-600 transition-colors select-none"
              >
                {currentArticle.title}
                {bookmarks.includes(currentArticle.id) && (
                  <Bookmark className="inline-block w-5 h-5 ml-2 text-amber-500 fill-amber-500" />
                )}
              </h2>

              <p className="text-slate-600 text-sm sm:text-base leading-relaxed mb-4 flex-1 max-w-[70ch]">
                {currentArticle.summary}
              </p>

              <div className="flex items-center justify-between mb-4 text-xs sm:text-sm text-slate-500">
                <div className="flex items-center gap-2 sm:gap-4">
                  <span>{new Date(currentArticle.publishedAt).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                  })}</span>
                  <span className="w-1 h-1 rounded-full bg-slate-300" />
                  <span>{currentArticle.readTime}s read</span>
                </div>
                <a
                  href={currentArticle.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-slate-500 hover:text-slate-700 transition-colors"
                  onClick={() => trackEvent('external_link', currentArticle.id)}
                >
                  <span className="hidden sm:inline">Source</span>
                  <ExternalLink className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                </a>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between gap-3 pt-3 sm:pt-4 border-t border-slate-200">
                <div className="flex gap-2 sm:gap-3">
                  <button
                    onClick={() => toggleBookmark(currentArticle.id)}
                    className={`group p-3 sm:p-4 rounded-xl sm:rounded-2xl transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center ${
                      bookmarks.includes(currentArticle.id)
                        ? 'bg-amber-100 text-amber-600 shadow-sm'
                        : 'bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700'
                    }`}
                    aria-label={bookmarks.includes(currentArticle.id) ? 'Remove bookmark' : 'Add bookmark'}
                  >
                    <Bookmark className={`w-5 h-5 transition-transform duration-300 ${
                      bookmarks.includes(currentArticle.id) ? 'scale-110 fill-amber-500' : 'group-hover:scale-110'
                    }`} />
                  </button>

                  <button
                    onClick={handleShare}
                    className="group p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center"
                    aria-label="Share article"
                  >
                    <Share2 className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>

                  <button
                    onClick={handleEmail}
                    className="group p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center"
                    aria-label="Email article"
                  >
                    <Mail className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>

                  <button
                    onClick={() => setShowTextModal(true)}
                    className="group p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center"
                    aria-label="Text article link"
                  >
                    <MessageSquare className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>
                </div>

                <div className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 rounded-full bg-slate-100">
                  <Heart className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-red-500 fill-red-500" />
                  <span className="text-xs sm:text-sm font-semibold text-slate-700">
                    {(currentArticle.shareCount + currentArticle.emailCount).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="px-4 sm:px-6 py-3 sm:py-4 glass border-t border-slate-200 shrink-0 safe-area-bottom">
        <div className="flex justify-between items-center text-xs text-slate-500 mb-2">
            <span className="font-medium">
              {currentIndex + 1} <span className="text-slate-300">/</span> {articles.length}
            </span>
            <span className="text-slate-400 hidden sm:inline">Swipe to navigate</span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-1 sm:h-1.5 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-slate-600 to-slate-800 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${((currentIndex + 1) / articles.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Bookmarks Drawer */}
      {showBookmarks && (
        <div className="fixed inset-0 z-50 animate-fade-in">
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={() => setShowBookmarks(false)}
          />
          <div className="absolute right-0 top-0 bottom-0 w-full sm:max-w-md bg-white border-l border-slate-200 animate-slide-in-up flex flex-col">
            <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-slate-200 glass shrink-0">
              <div>
                <h2 className="text-lg sm:text-xl font-bold text-slate-900">Bookmarks</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {bookmarks.length} {bookmarks.length === 1 ? 'article' : 'articles'} saved
                </p>
              </div>
              <button
                onClick={() => setShowBookmarks(false)}
                className="p-2.5 sm:p-3 rounded-full hover:bg-slate-100 transition-all duration-300 btn-press min-w-[44px] min-h-[44px] flex items-center justify-center"
                aria-label="Close bookmarks"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 sm:p-6 scrollbar-hide">
              {bookmarks.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-slate-100 flex items-center justify-center mb-4">
                    <Bookmark className="w-8 h-8 sm:w-10 sm:h-10 text-slate-300" />
                  </div>
                  <p className="text-slate-700 text-base sm:text-lg font-medium mb-2">No bookmarks yet</p>
                  <p className="text-slate-500 text-xs sm:text-sm">Articles you bookmark will appear here</p>
                </div>
              ) : (
                <div className="space-y-3 sm:space-y-4">
                  {articles.filter(a => bookmarks.includes(a.id)).map((article, index) => (
                    <div
                      key={article.id}
                      className="group p-4 sm:p-5 rounded-xl sm:rounded-2xl bg-slate-50 hover:bg-slate-100 cursor-pointer transition-all duration-300 card-hover animate-slide-in-up border border-slate-200"
                      style={{ animationDelay: `${index * 50}ms` }}
                      onClick={() => {
                        const idx = articles.findIndex(a => a.id === article.id);
                        setCurrentIndex(idx);
                        setShowBookmarks(false);
                      }}
                    >
                      <div className="flex items-start justify-between gap-3 sm:gap-4">
                        <div className="flex-1 min-w-0">
                          <span className={`inline-block px-2 sm:px-3 py-0.5 sm:py-1 rounded-full text-[11px] sm:text-xs font-bold uppercase tracking-[0.08em] mb-2 sm:mb-3 bg-gradient-to-r ${
                            genres.find(g => g.id === article.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                          } text-white`}>
                            {article.primaryGenre}
                          </span>
                          <h3 className="text-slate-900 text-sm sm:text-base font-semibold leading-snug mb-1.5 sm:mb-2 line-clamp-2">
                            {article.title}
                          </h3>
                          <p className="text-slate-500 text-xs sm:text-sm line-clamp-2">
                            {article.summary}
                          </p>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleBookmark(article.id);
                          }}
                          className="p-2 rounded-full bg-white hover:bg-red-50 text-slate-400 hover:text-red-500 transition-all duration-300 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 min-w-[36px] min-h-[36px] flex items-center justify-center shrink-0 border border-slate-200"
                          aria-label="Remove bookmark"
                        >
                          <X className="w-4 h-4" />
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

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      {/* Menu Drawer */}
      {showMenu && (
        <div className="fixed inset-0 z-[60] animate-fade-in">
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={() => setShowMenu(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-[84vw] max-w-sm bg-white border-r border-slate-200 p-5 sm:p-6 flex flex-col gap-6 animate-slide-in-left">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center overflow-hidden">
                  <img src="/branding/minylogo.png" alt="miny y0" className="w-8 h-8 object-contain" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900 tracking-tight">y0</p>
                  <p className="text-[11px] text-slate-500">brand menu</p>
                </div>
              </div>
              <button
                onClick={() => setShowMenu(false)}
                className="p-2 rounded-full hover:bg-slate-100"
                aria-label="Close menu"
              >
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <img src="/branding/minylogo.png" alt="Miny logo" className="h-8 w-auto object-contain" />
                <span className="text-sm font-semibold text-slate-700">miny</span>
              </div>
              <div className="flex items-center gap-2">
                <img src="/branding/velab-logo.png" alt="VE Lab logo" className="h-8 w-auto object-contain opacity-90" />
                <span className="text-sm font-semibold text-slate-700">VE Lab</span>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Explore</p>
              <nav className="space-y-2">
                <a
                  href="https://minyvinyl.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-700 transition hover:bg-slate-50"
                  aria-label="Open Miny Vinyl"
                >
                  <span className="flex items-center gap-3">
                    <img src="/branding/minylogo.png" alt="" className="h-6 w-6 object-contain" />
                    <span>
                      <span className="block text-sm font-semibold">Miny Vinyl</span>
                      <span className="block text-xs text-slate-500">Main platform</span>
                    </span>
                  </span>
                  <ExternalLink className="h-4 w-4 text-slate-400" />
                </a>
                <a
                  href="https://velab.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-700 transition hover:bg-slate-50"
                  aria-label="Open VE Lab"
                >
                  <span className="flex items-center gap-3">
                    <img src="/branding/velab-logo.png" alt="" className="h-6 w-6 object-contain" />
                    <span>
                      <span className="block text-sm font-semibold">VE Lab</span>
                      <span className="block text-xs text-slate-500">Studio + research</span>
                    </span>
                  </span>
                  <ExternalLink className="h-4 w-4 text-slate-400" />
                </a>
              </nav>
            </div>

            <div className="mt-auto space-y-2">
              <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Actions</p>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      setShowBookmarks(true);
                    }}
                    className="flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                    aria-label="Open bookmarks"
                  >
                    <span className="inline-flex items-center gap-2">
                      <Bookmark className={`w-4 h-4 ${bookmarks.length > 0 ? 'text-amber-500 fill-amber-500' : 'text-slate-500'}`} />
                      Bookmarks ({bookmarks.length})
                    </span>
                  </button>
                  <button
                    onClick={() => {
                      fetchArticles(selectedGenre);
                      setShowMenu(false);
                    }}
                    className="rounded-xl border border-slate-200 bg-white p-2.5 text-slate-600 transition hover:bg-slate-50"
                    aria-label="Refresh feed"
                  >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              </div>
              <p className="text-xs text-slate-500">Live music headlines from the miny-ven VM scraper.</p>
            </div>
          </div>
        </div>
      )}

      {/* SMS Modal */}
      {showTextModal && (
        <div className="fixed inset-0 z-50 animate-fade-in">
          <div
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={() => setShowTextModal(false)}
          />
          <div className="absolute inset-x-4 top-1/2 -translate-y-1/2 mx-auto w-full max-w-md rounded-3xl border border-slate-200 bg-white p-5 shadow-2xl">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-slate-900">Text This Link</h3>
              <p className="mt-1 text-sm text-slate-500">Send this article link using Quo API.</p>
            </div>
            <label className="mb-2 block text-xs uppercase tracking-wide text-slate-500">Phone Number</label>
            <input
              value={smsPhone}
              onChange={(e) => setSmsPhone(e.target.value)}
              placeholder="+1 555 123 4567"
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
              autoFocus
            />
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                onClick={() => setShowTextModal(false)}
                className="rounded-xl px-4 py-2 text-sm text-slate-500 hover:bg-slate-100"
                type="button"
              >
                Cancel
              </button>
              <button
                onClick={handleTextLink}
                disabled={smsSending}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 hover:bg-slate-800"
                type="button"
              >
                <Send className="h-4 w-4" />
                {smsSending ? 'Sending...' : 'Send text'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className={showDesktopShell ? 'desktop-shell-scene' : ''}>
      {showDesktopShell && (
        <button
          onClick={() => setUseDesktopShell(false)}
          className="fixed top-4 right-4 z-[80] rounded-full border border-indigo-300 bg-indigo-50 p-2.5 text-indigo-600 shadow-lg transition hover:bg-indigo-100"
          aria-label="Exit phone preview"
          type="button"
        >
          <Smartphone className="h-4 w-4" />
        </button>
      )}

      {isDesktopGalleryMode ? (
        desktopGalleryContent
      ) : (
      <div className={showDesktopShell ? 'iphone-shell-frame' : ''}>
        {showDesktopShell && (
          <>
            <span className="iphone-side-btn iphone-side-btn--mute" />
            <span className="iphone-side-btn iphone-side-btn--up" />
            <span className="iphone-side-btn iphone-side-btn--down" />
            <span className="iphone-side-btn iphone-side-btn--power" />
            <div className="iphone-dynamic-island" />
          </>
        )}

        <div className={showDesktopShell ? 'iphone-shell-screen' : 'h-[100dvh]'}>
          {appContent}
        </div>
      </div>
      )}
    </div>
  );
}

export default App;
