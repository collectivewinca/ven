import { useState, useEffect, useCallback, useRef } from 'react';
import type { MusicNewsArticle, Genre } from './types/news';
import { Bookmark, Share2, Mail, Heart, Music, X, ChevronUp, ChevronDown, ExternalLink, RefreshCw, Smartphone, MessageSquare, Send, Menu } from 'lucide-react';

// Loading skeleton component
const ArticleSkeleton = () => (
  <div className="h-full flex flex-col p-4 sm:p-6 animate-pulse">
    <div className="w-20 h-6 bg-white/10 rounded-full mb-4" />
    <div className="relative aspect-[4/3] mb-4 rounded-2xl bg-white/5 overflow-hidden">
      <div className="absolute inset-0 skeleton" />
    </div>
    <div className="space-y-3 mb-4">
      <div className="h-7 bg-white/10 rounded-lg w-3/4" />
      <div className="h-7 bg-white/10 rounded-lg w-1/2" />
    </div>
    <div className="space-y-2 flex-1">
      <div className="h-4 bg-white/5 rounded w-full" />
      <div className="h-4 bg-white/5 rounded w-full" />
      <div className="h-4 bg-white/5 rounded w-5/6" />
      <div className="h-4 bg-white/5 rounded w-4/5" />
    </div>
  </div>
);

// Toast notification component
const Toast = ({ message, onClose }: { message: string; onClose: () => void }) => {
  useEffect(() => {
    const timer = setTimeout(onClose, 2000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-slide-in-up px-4">
      <div className="glass-light px-5 py-3 rounded-full text-sm font-medium text-white shadow-2xl whitespace-nowrap">
        {message}
      </div>
    </div>
  );
};

// Pull to refresh indicator
const PullToRefresh = ({ pullDistance, isPulling }: { pullDistance: number; isPulling: boolean }) => {
  if (!isPulling || pullDistance < 20) return null;
  
  const opacity = Math.min(pullDistance / 80, 1);
  const rotation = Math.min((pullDistance / 100) * 360, 360);
  
  return (
    <div 
      className="absolute top-0 left-0 right-0 flex justify-center items-center z-20 pointer-events-none"
      style={{ 
        opacity,
        transform: `translateY(${Math.min(pullDistance * 0.5, 60)}px)`,
        paddingTop: 'env(safe-area-inset-top)'
      }}
    >
      <div 
        className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center"
        style={{ transform: `rotate(${rotation}deg)` }}
      >
        <RefreshCw className="w-5 h-5 text-white" />
      </div>
    </div>
  );
};

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

  // Fetch articles from Firebase using REST API
  const fetchArticles = useCallback(async (genre: Genre = 'all') => {
    setLoading(true);
    setArticles([]);
    
    try {
      // Use REST API directly to avoid Firestore client issues
      const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID || 'miny-ven';
      const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;
      const apiKeyParam = apiKey ? `?key=${apiKey}` : '';
      const url = `https://firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents/articles${apiKeyParam}`;
      
      console.log('Fetching articles from REST API...');
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('REST API response:', data);
      
      if (!data.documents) {
        setArticles([]);
        setToast('No articles found.');
        setLoading(false);
        return;
      }
      
      const fetchedArticles: MusicNewsArticle[] = data.documents.map((doc: any) => {
        const fields = doc.fields;
        const docId = doc.name.split('/').pop();
        
        // Helper to get field value
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
          imageUrl: getField(fields.image_url) || '',
          publishedAt: new Date(getField(fields.published_at) || Date.now()),
          readTime: getField(fields.read_time) || 60,
          shareCount: getField(fields.share_count) || 0,
          emailCount: getField(fields.email_count) || 0,
          bookmarkCount: getField(fields.bookmark_count) || 0,
          viewCount: getField(fields.view_count) || 0,
          isBookmarked: false
        };
      });
      
      // Sort by published_at desc
      fetchedArticles.sort((a: MusicNewsArticle, b: MusicNewsArticle) => 
        b.publishedAt.getTime() - a.publishedAt.getTime()
      );
      
      // Filter by genre if needed
      const filteredArticles = genre === 'all' 
        ? fetchedArticles 
        : fetchedArticles.filter((a: MusicNewsArticle) => a.primaryGenre === genre);
      
      setArticles(filteredArticles);
      console.log(`Loaded ${filteredArticles.length} articles from REST API`);
      
      if (filteredArticles.length === 0) {
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

  // Fetch articles on mount and when genre changes
  useEffect(() => {
    fetchArticles(selectedGenre);
  }, [fetchArticles, selectedGenre]);

  const genres: { id: Genre; label: string; gradient: string }[] = [
    { id: 'all', label: 'All', gradient: 'from-gray-600 to-gray-500' },
    { id: 'gospel', label: 'Gospel', gradient: 'from-orange-500 to-amber-500' },
    { id: 'hiphop', label: 'Hip-Hop', gradient: 'from-violet-600 to-indigo-600' },
    { id: 'pop', label: 'Pop', gradient: 'from-pink-500 to-rose-500' },
    { id: 'rock', label: 'Rock', gradient: 'from-red-600 to-orange-600' },
    { id: 'electronic', label: 'Electronic', gradient: 'from-cyan-600 to-blue-600' },
  ];

  const filteredArticles = selectedGenre === 'all' 
    ? articles 
    : articles.filter(a => a.primaryGenre === selectedGenre);

  const getFallbackImage = useCallback((genre?: string) => {
    const map: Record<string, string> = {
      gospel: '/branding/minylogo.png',
      hiphop: '/branding/minylogo.png',
      pop: '/branding/minylogo.png',
      rock: '/branding/minylogo.png',
      electronic: '/branding/minylogo.png',
    };
    return map[genre || ''] || '/branding/minylogo.png';
  }, []);

  const resolveArticleImage = useCallback((imageUrl?: string, genre?: string) => {
    const raw = (imageUrl || '').trim();
    if (!raw) return getFallbackImage(genre);
    if (raw.includes('images.unsplash.com')) return getFallbackImage(genre);
    return raw;
  }, [getFallbackImage]);

  const currentArticle = filteredArticles[currentIndex];

  // Save bookmarks to localStorage
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
      if (!response.ok) {
        throw new Error(data?.error || 'Failed to send SMS');
      }

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

  // Enhanced touch handlers with pull-to-refresh and drag feedback
  const onTouchStart = useCallback((e: React.TouchEvent) => {
    const touchY = e.targetTouches[0].clientY;
    setTouchEnd(null);
    setTouchStart(touchY);
    setIsDragging(true);
    
    // Check if at top of content for pull-to-refresh
    if (containerRef.current && containerRef.current.scrollTop === 0) {
      setIsPulling(true);
    }
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    const touchY = e.targetTouches[0].clientY;
    setTouchEnd(touchY);
    
    // Handle pull-to-refresh
    if (isPulling && touchStart && containerRef.current?.scrollTop === 0) {
      const pullDist = touchStart - touchY;
      if (pullDist < 0) {
        setPullDistance(Math.abs(pullDist));
      }
    }
    
    // Visual drag feedback for swipe
    if (!isPulling && touchStart && contentRef.current) {
      const diff = touchStart - touchY;
      const translateY = diff * 0.2;
      contentRef.current.style.transform = `translateY(${-translateY}px)`;
    }
  }, [touchStart, isPulling]);

  const onTouchEnd = useCallback(() => {
    setIsDragging(false);
    setIsPulling(false);
    
    // Handle pull-to-refresh
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

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
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

  // Reset index when genre changes
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

  const desktopGalleryContent = (
    <div className="h-[100dvh] overflow-hidden bg-[radial-gradient(circle_at_8%_8%,#1f2937_0%,#111827_40%,#030712_100%)] text-white">
      <div className="h-full overflow-y-auto scrollbar-hide">
        <div className="sticky top-0 z-20 border-b border-white/10 bg-black/40 backdrop-blur-xl">
          <div className="mx-auto max-w-[1400px] px-6 py-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="h-11 w-11 rounded-2xl border border-white/20 bg-white/10 p-2">
                  <img src="/branding/minylogo.png" alt="miny y0" className="h-full w-full object-contain" />
                </div>
                <div>
                  <h1 className="text-2xl font-black tracking-tight">y0</h1>
                  <p className="text-xs uppercase tracking-[0.22em] text-white/50">Live Music Intelligence</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => fetchArticles(selectedGenre)}
                  className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-medium transition hover:bg-white/20"
                  disabled={loading}
                >
                  <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
                <button
                  onClick={() => setShowBookmarks(true)}
                  className="relative rounded-full border border-white/20 bg-white/10 p-2.5 transition hover:bg-white/20"
                  aria-label="View bookmarks"
                >
                  <Bookmark className={`h-4 w-4 ${bookmarks.length ? 'fill-yellow-400 text-yellow-400' : 'text-white/80'}`} />
                  {bookmarks.length > 0 && (
                    <span className="absolute -right-1 -top-1 grid h-4 w-4 place-items-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
                      {bookmarks.length}
                    </span>
                  )}
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
                      : 'border border-white/20 bg-white/5 text-white/70 hover:bg-white/10'
                  }`}
                >
                  {genre.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mx-auto grid max-w-[1400px] grid-cols-12 gap-6 px-6 py-6">
          <section className="col-span-12 lg:col-span-7">
            {loading ? (
              <ArticleSkeleton />
            ) : !currentArticle ? (
              <div className="rounded-3xl border border-white/10 bg-black/30 p-10 text-center text-white/60">
                No articles available
              </div>
            ) : (
              <article className="overflow-hidden rounded-3xl border border-white/10 bg-black/45 shadow-2xl">
                <div className="relative aspect-[16/9]">
                  <img
                    src={resolveArticleImage(currentArticle.imageUrl, currentArticle.primaryGenre)}
                    alt={currentArticle.title}
                    className="h-full w-full object-cover"
                    loading="lazy"
                    onError={(e) => {
                      const el = e.currentTarget as HTMLImageElement;
                      el.src = getFallbackImage(currentArticle.primaryGenre);
                    }}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black via-black/25 to-transparent" />
                  <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between">
                    <span className={`rounded-full bg-gradient-to-r px-3 py-1 text-[11px] font-bold uppercase tracking-wider ${
                      genres.find(g => g.id === currentArticle.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                    }`}>
                      {currentArticle.primaryGenre}
                    </span>
                    <span className="rounded-full bg-black/50 px-3 py-1 text-[11px] text-white/90">{currentArticle.source}</span>
                  </div>
                </div>
                <div className="space-y-3 p-6">
                  <h2 className="text-2xl font-extrabold leading-tight tracking-tight">{currentArticle.title}</h2>
                  <p className="leading-relaxed text-white/75">{currentArticle.summary}</p>
                  <div className="flex items-center justify-between pt-2 text-sm text-white/55">
                    <span>{new Date(currentArticle.publishedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                    <a
                      href={currentArticle.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 rounded-full border border-white/20 px-3 py-1.5 text-white/80 transition hover:bg-white/10"
                      onClick={() => trackEvent('external_link', currentArticle.id)}
                    >
                      Open Source <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  </div>
                </div>
              </article>
            )}
          </section>

          <aside className="col-span-12 lg:col-span-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-[0.2em] text-white/60">More Stories</h3>
              <span className="text-xs text-white/40">{filteredArticles.length} total</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {filteredArticles.map((article) => {
                const idx = filteredArticles.findIndex(a => a.id === article.id);
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
                        ? 'border-white/40 bg-white/10'
                        : 'border-white/10 bg-black/35 hover:-translate-y-0.5 hover:border-white/25 hover:bg-black/55'
                    }`}
                  >
                    <div className="relative aspect-[16/10]">
                      <img
                        src={resolveArticleImage(article.imageUrl, article.primaryGenre)}
                        alt={article.title}
                        className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
                        loading="lazy"
                        onError={(e) => {
                          const el = e.currentTarget as HTMLImageElement;
                          el.src = getFallbackImage(article.primaryGenre);
                        }}
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
                    </div>
                    <div className="space-y-1 p-3">
                      <p className="line-clamp-2 text-sm font-semibold leading-tight text-white">{article.title}</p>
                      <p className="text-[11px] uppercase tracking-wider text-white/45">{article.source}</p>
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

  const appContent = !currentArticle && !loading ? (
    <div className="h-full bg-black flex items-center justify-center safe-area-top safe-area-bottom">
      <div className="text-center px-4">
        <Music className="w-16 h-16 text-white/20 mx-auto mb-4" />
        <p className="text-white/40 text-lg mb-2">No articles found</p>
        <p className="text-white/20 text-sm">Run the scraper to populate Firebase with content</p>
        <button 
          onClick={() => fetchArticles(selectedGenre)}
          className="mt-6 px-6 py-3 bg-white/10 rounded-full text-white hover:bg-white/20 transition-all"
        >
          Retry
        </button>
      </div>
    </div>
  ) : (
    <div className="h-full bg-black flex flex-col overflow-hidden safe-area-top safe-area-bottom">
      {/* Pull to Refresh Indicator */}
      <PullToRefresh pullDistance={pullDistance} isPulling={isPulling} />
      
      {/* Premium Header - Mobile Optimized */}
      <header className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 glass z-50 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-white/10 flex items-center justify-center overflow-hidden border border-white/20">
            <img src="/branding/minylogo.png" alt="miny y0" className="w-7 h-7 sm:w-8 sm:h-8 object-contain" />
          </div>
          <div>
            <h1 className="text-base sm:text-lg font-bold tracking-tight">y0</h1>
            <p className="text-[10px] sm:text-xs text-white/40">creator music intelligence</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button 
            onClick={() => {
              setShowMenu(false);
              setShowBookmarks(true);
            }}
            className="relative group p-2.5 sm:p-3 rounded-full hover:bg-white/5 transition-all duration-300 btn-press min-w-[44px] min-h-[44px] flex items-center justify-center"
            aria-label="View bookmarks"
          >
            <Bookmark className={`w-5 h-5 sm:w-6 sm:h-6 transition-all duration-300 ${
              bookmarks.length > 0 
                ? 'text-yellow-400 fill-yellow-400 scale-110' 
                : 'text-white/60 group-hover:text-white'
            }`} />
            {bookmarks.length > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 sm:w-5 sm:h-5 bg-red-500 text-white text-[9px] sm:text-[10px] font-bold rounded-full flex items-center justify-center animate-scale-in shadow-lg">
                {bookmarks.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setShowMenu(true)}
            className="group p-2.5 sm:p-3 rounded-full hover:bg-white/5 transition-all duration-300 btn-press min-w-[44px] min-h-[44px] flex items-center justify-center"
            aria-label="Open menu"
          >
            <Menu className="w-5 h-5 sm:w-6 sm:h-6 text-white/70 group-hover:text-white" />
          </button>
        </div>
      </header>

      {/* Genre Filter - Mobile Optimized */}
      <div className="px-4 sm:px-6 py-3 border-b border-white/5 shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5 sm:gap-2 overflow-x-auto scrollbar-hide pb-1 flex-1">
            {genres.map((genre, index) => (
              <button
                key={genre.id}
                onClick={() => setSelectedGenre(genre.id)}
                className={`relative px-3 sm:px-5 py-2 rounded-full text-xs sm:text-sm font-medium whitespace-nowrap transition-all duration-300 btn-press min-h-[36px] sm:min-h-[40px] ${
                  selectedGenre === genre.id 
                    ? `bg-gradient-to-r ${genre.gradient} text-white shadow-lg` 
                    : 'bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80'
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {genre.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => fetchArticles(selectedGenre)}
            className="ml-2 p-2 rounded-full bg-white/5 text-white/60 hover:bg-white/10 hover:text-white transition-all duration-300 min-w-[40px] min-h-[40px] flex items-center justify-center"
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
        className="flex-1 relative overflow-y-auto overflow-x-hidden scrollbar-hide"
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {/* Swipe Hints */}
        <div className="absolute inset-0 pointer-events-none z-10">
          <div className={`absolute top-4 left-1/2 -translate-x-1/2 transition-all duration-300 ${
            currentIndex > 0 ? 'opacity-30' : 'opacity-0'
          }`}>
            <ChevronUp className="w-6 h-6 sm:w-8 sm:h-8 text-white animate-pulse" />
          </div>
          <div className={`absolute bottom-28 sm:bottom-32 left-1/2 -translate-x-1/2 transition-all duration-300 ${
            currentIndex < filteredArticles.length - 1 ? 'opacity-30' : 'opacity-0'
          }`}>
            <ChevronDown className="w-6 h-6 sm:w-8 sm:h-8 text-white animate-pulse" />
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
              {/* Image with Gradient Overlay - Smaller size with tags */}
              <div className="relative aspect-[16/9] mb-4 rounded-2xl sm:rounded-3xl overflow-hidden bg-gray-900 shadow-2xl card-hover group">
                <img 
                  src={resolveArticleImage(currentArticle.imageUrl, currentArticle.primaryGenre)}
                  alt={currentArticle.title}
                  className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                  loading="lazy"
                  onError={(e) => {
                    const el = e.currentTarget as HTMLImageElement;
                    if (!el.src.endsWith('/branding/minylogo.png')) {
                      el.src = getFallbackImage(currentArticle.primaryGenre);
                    }
                  }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />
                
                {/* Genre Badge & Source - positioned on image */}
                <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[9px] sm:text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r ${
                    genres.find(g => g.id === currentArticle.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                  } text-white shadow-lg backdrop-blur-sm`}>
                    {currentArticle.primaryGenre}
                  </span>
                  <span className="px-2.5 py-1 rounded-full text-[9px] sm:text-[10px] font-medium text-white/90 bg-black/40 backdrop-blur-sm">
                    {currentArticle.source}
                  </span>
                </div>
              </div>

              {/* Title - Clickable to bookmark */}
              <h2 
                onClick={() => toggleBookmark(currentArticle.id)}
                className="text-lg sm:text-xl md:text-2xl font-bold text-white mb-3 leading-tight tracking-tight cursor-pointer hover:text-white/80 transition-colors select-none"
              >
                {currentArticle.title}
                {bookmarks.includes(currentArticle.id) && (
                  <Bookmark className="inline-block w-5 h-5 ml-2 text-yellow-400 fill-yellow-400" />
                )}
              </h2>

              {/* Summary - Mobile Optimized */}
              <p className="text-white/70 text-sm sm:text-base leading-relaxed mb-4 flex-1">
                {currentArticle.summary}
              </p>

              {/* Meta Info - Mobile Optimized */}
              <div className="flex items-center justify-between mb-4 text-xs sm:text-sm text-white/40">
                <div className="flex items-center gap-2 sm:gap-4">
                  <span>{new Date(currentArticle.publishedAt).toLocaleDateString('en-US', { 
                    month: 'short', 
                    day: 'numeric',
                    year: 'numeric'
                  })}</span>
                  <span className="w-1 h-1 rounded-full bg-white/20" />
                  <span>{currentArticle.readTime}s read</span>
                </div>
                <a 
                  href={currentArticle.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 hover:text-white/60 transition-colors"
                  onClick={() => trackEvent('external_link', currentArticle.id)}
                >
                  <span className="hidden sm:inline">Source</span>
                  <ExternalLink className="w-3 h-3 sm:w-3.5 sm:h-3.5" />
                </a>
              </div>

              {/* Action Buttons - Mobile Optimized */}
              <div className="flex items-center justify-between gap-3 pt-3 sm:pt-4 border-t border-white/5">
                <div className="flex gap-2 sm:gap-3">
                  <button 
                    onClick={() => toggleBookmark(currentArticle.id)}
                    className={`group p-3 sm:p-4 rounded-xl sm:rounded-2xl transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center ${
                      bookmarks.includes(currentArticle.id) 
                        ? 'bg-yellow-400 text-black shadow-lg shadow-yellow-400/30' 
                        : 'bg-white/5 text-white/60 hover:bg-white/10 hover:text-white'
                    }`}
                    aria-label={bookmarks.includes(currentArticle.id) ? 'Remove bookmark' : 'Add bookmark'}
                  >
                    <Bookmark className={`w-5 h-5 transition-transform duration-300 ${
                      bookmarks.includes(currentArticle.id) ? 'scale-110' : 'group-hover:scale-110'
                    }`} />
                  </button>
                  
                  <button 
                    onClick={handleShare}
                    className="group p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-white/5 text-white/60 hover:bg-white/10 hover:text-white transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center"
                    aria-label="Share article"
                  >
                    <Share2 className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>
                  
                  <button 
                    onClick={handleEmail}
                    className="group p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-white/5 text-white/60 hover:bg-white/10 hover:text-white transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center"
                    aria-label="Email article"
                  >
                    <Mail className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>

                  <button
                    onClick={() => setShowTextModal(true)}
                    className="group p-3 sm:p-4 rounded-xl sm:rounded-2xl bg-white/5 text-white/60 hover:bg-white/10 hover:text-white transition-all duration-300 btn-press min-w-[48px] min-h-[48px] flex items-center justify-center"
                    aria-label="Text article link"
                  >
                    <MessageSquare className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>
                </div>

                {/* Popularity Score */}
                <div className="flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 rounded-full bg-white/5">
                  <Heart className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-red-500 fill-red-500" />
                  <span className="text-xs sm:text-sm font-semibold text-white">
                    {(currentArticle.shareCount + currentArticle.emailCount).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Progress Bar - Mobile Optimized */}
      <div className="px-4 sm:px-6 py-3 sm:py-4 glass border-t border-white/5 shrink-0 safe-area-bottom">
        <div className="flex justify-between items-center text-xs text-white/40 mb-2">
          <span className="font-medium">
            {currentIndex + 1} <span className="text-white/20">/</span> {filteredArticles.length}
          </span>
          <span className="text-white/30 hidden sm:inline">Swipe to navigate</span>
        </div>
        <div className="w-full bg-white/5 rounded-full h-1 sm:h-1.5 overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-white/80 to-white rounded-full transition-all duration-500 ease-out"
            style={{ width: `${((currentIndex + 1) / filteredArticles.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Bookmarks Bottom Sheet - Mobile Optimized */}
      {showBookmarks && (
        <div className="fixed inset-0 z-50 animate-fade-in">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowBookmarks(false)}
          />
          <div className="absolute right-0 top-0 bottom-0 w-full sm:max-w-md bg-black border-l border-white/10 animate-slide-in-up flex flex-col">
            {/* Drawer Header */}
            <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-white/10 glass shrink-0">
              <div>
                <h2 className="text-lg sm:text-xl font-bold">Bookmarks</h2>
                <p className="text-[10px] sm:text-xs text-white/40 mt-0.5">
                  {bookmarks.length} {bookmarks.length === 1 ? 'article' : 'articles'} saved
                </p>
              </div>
              <button 
                onClick={() => setShowBookmarks(false)}
                className="p-2.5 sm:p-3 rounded-full hover:bg-white/10 transition-all duration-300 btn-press min-w-[44px] min-h-[44px] flex items-center justify-center"
                aria-label="Close bookmarks"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Bookmarks List */}
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 scrollbar-hide">
              {bookmarks.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-full bg-white/5 flex items-center justify-center mb-4">
                    <Bookmark className="w-8 h-8 sm:w-10 sm:h-10 text-white/20" />
                  </div>
                  <p className="text-white/40 text-base sm:text-lg font-medium mb-2">No bookmarks yet</p>
                  <p className="text-white/20 text-xs sm:text-sm">Articles you bookmark will appear here</p>
                </div>
              ) : (
                <div className="space-y-3 sm:space-y-4">
                  {articles.filter(a => bookmarks.includes(a.id)).map((article, index) => (
                    <div 
                      key={article.id}
                      className="group p-4 sm:p-5 rounded-xl sm:rounded-2xl bg-white/5 hover:bg-white/10 cursor-pointer transition-all duration-300 card-hover animate-slide-in-up"
                      style={{ animationDelay: `${index * 50}ms` }}
                      onClick={() => {
                        const idx = articles.findIndex(a => a.id === article.id);
                        setCurrentIndex(idx);
                        setShowBookmarks(false);
                      }}
                    >
                      <div className="flex items-start justify-between gap-3 sm:gap-4">
                        <div className="flex-1 min-w-0">
                          <span className={`inline-block px-2 sm:px-3 py-0.5 sm:py-1 rounded-full text-[9px] sm:text-[10px] font-bold uppercase tracking-wider mb-2 sm:mb-3 bg-gradient-to-r ${
                            genres.find(g => g.id === article.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                          } text-white`}>
                            {article.primaryGenre}
                          </span>
                          <h3 className="text-white text-sm sm:text-base font-semibold leading-snug mb-1.5 sm:mb-2 line-clamp-2">
                            {article.title}
                          </h3>
                          <p className="text-white/40 text-xs sm:text-sm line-clamp-2">
                            {article.summary}
                          </p>
                        </div>
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleBookmark(article.id);
                          }}
                          className="p-2 rounded-full bg-white/5 hover:bg-red-500/20 text-white/40 hover:text-red-400 transition-all duration-300 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 min-w-[36px] min-h-[36px] flex items-center justify-center shrink-0"
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

      {/* Toast Notification */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}

      {/* Slide-out Menu */}
      {showMenu && (
        <div className="fixed inset-0 z-[60] animate-fade-in">
          <div
            className="absolute inset-0 bg-black/65 backdrop-blur-sm"
            onClick={() => setShowMenu(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-[84vw] max-w-sm bg-black border-r border-white/10 p-5 sm:p-6 flex flex-col gap-6 animate-slide-in-left">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-white/10 border border-white/20 flex items-center justify-center overflow-hidden">
                  <img src="/branding/minylogo.png" alt="miny y0" className="w-8 h-8 object-contain" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white tracking-tight">y0</p>
                  <p className="text-[11px] text-white/45">brand menu</p>
                </div>
              </div>
              <button
                onClick={() => setShowMenu(false)}
                className="p-2 rounded-full hover:bg-white/10"
                aria-label="Close menu"
              >
                <X className="w-4 h-4 text-white/80" />
              </button>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 flex items-center justify-between">
              <img src="/branding/minylogo.png" alt="Miny logo" className="h-8 w-auto object-contain" />
              <img src="/branding/velab-logo.png" alt="VE Lab logo" className="h-8 w-auto object-contain opacity-90" />
            </div>

            <nav className="space-y-2">
              <a
                href="https://minyvinyl.com"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center rounded-xl p-3 text-white/85 hover:bg-white/10"
                aria-label="Open Miny Vinyl"
                title="Open Miny Vinyl"
              >
                <img src="/branding/minylogo.png" alt="" className="h-6 w-6 object-contain" />
              </a>
              <a
                href="https://velab.org"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center rounded-xl p-3 text-white/85 hover:bg-white/10"
                aria-label="Open VE Lab"
                title="Open VE Lab"
              >
                <img src="/branding/velab-logo.png" alt="" className="h-6 w-6 object-contain" />
              </a>
            </nav>

            <div className="mt-auto">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      setShowMenu(false);
                      setShowBookmarks(true);
                    }}
                    className="w-11 h-11 rounded-xl bg-white/10 hover:bg-white/15 flex items-center justify-center"
                    aria-label="Open bookmarks"
                  >
                    <Bookmark className={`w-5 h-5 ${bookmarks.length > 0 ? 'text-yellow-400 fill-yellow-400' : 'text-white/80'}`} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SMS Modal */}
      {showTextModal && (
        <div className="fixed inset-0 z-50 animate-fade-in">
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setShowTextModal(false)}
          />
          <div className="absolute inset-x-4 top-1/2 -translate-y-1/2 mx-auto w-full max-w-md rounded-3xl border border-white/15 bg-black/90 p-5 shadow-2xl">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-white">Text This Link</h3>
              <p className="mt-1 text-sm text-white/55">Send this article link using Quo API.</p>
            </div>
            <label className="mb-2 block text-xs uppercase tracking-wide text-white/45">Phone Number</label>
            <input
              value={smsPhone}
              onChange={(e) => setSmsPhone(e.target.value)}
              placeholder="+1 555 123 4567"
              className="w-full rounded-2xl border border-white/15 bg-white/5 px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:border-white/40"
              autoFocus
            />
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                onClick={() => setShowTextModal(false)}
                className="rounded-xl px-4 py-2 text-sm text-white/75 hover:bg-white/10"
                type="button"
              >
                Cancel
              </button>
              <button
                onClick={handleTextLink}
                disabled={smsSending}
                className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-sm font-medium text-black disabled:opacity-50"
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
      {isDesktopViewport && (
        <button
          onClick={() => setUseDesktopShell(prev => !prev)}
          className="desktop-shell-toggle"
          type="button"
        >
          <Smartphone className="w-4 h-4" />
          {showDesktopShell ? 'Shell on' : 'Shell off'}
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
