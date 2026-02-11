import { useState, useEffect, useCallback, useRef } from 'react';
import type { MusicNewsArticle, Genre } from './types/news';
import { db } from './firebase';
import { collection, query, orderBy, limit, getDocs, where } from 'firebase/firestore';
import { Bookmark, Share2, Mail, Heart, Music, X, ChevronUp, ChevronDown, ExternalLink, RefreshCw } from 'lucide-react';

// Loading skeleton component
const ArticleSkeleton = () => (
  <div className="h-full flex flex-col p-6 animate-pulse">
    <div className="w-20 h-6 bg-white/10 rounded-full mb-6" />
    <div className="relative aspect-[4/3] mb-6 rounded-3xl bg-white/5 overflow-hidden">
      <div className="absolute inset-0 skeleton" />
    </div>
    <div className="space-y-3 mb-4">
      <div className="h-8 bg-white/10 rounded-lg w-3/4" />
      <div className="h-8 bg-white/10 rounded-lg w-1/2" />
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
    <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-slide-in-up">
      <div className="glass-light px-6 py-3 rounded-full text-sm font-medium text-white shadow-2xl">
        {message}
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
  const [swipeDirection, setSwipeDirection] = useState<'up' | 'down' | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [touchStart, setTouchStart] = useState<number | null>(null);
  const [touchEnd, setTouchEnd] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  // Fetch articles from Firebase
  const fetchArticles = useCallback(async (genre: Genre = 'all') => {
    setLoading(true);
    try {
      let q;
      if (genre === 'all') {
        q = query(
          collection(db, 'articles'),
          orderBy('published_at', 'desc'),
          limit(50)
        );
      } else {
        q = query(
          collection(db, 'articles'),
          where('primary_genre', '==', genre),
          orderBy('published_at', 'desc'),
          limit(50)
        );
      }
      
      const querySnapshot = await getDocs(q);
      const fetchedArticles: MusicNewsArticle[] = [];
      
      querySnapshot.forEach((doc) => {
        const data = doc.data();
        fetchedArticles.push({
          id: doc.id,
          title: data.title,
          summary: data.summary,
          fullContent: data.full_content,
          source: data.source,
          sourceUrl: data.source_url,
          primaryGenre: data.primary_genre,
          secondaryGenres: data.secondary_genres || [],
          artistNames: data.artist_names || [],
          imageUrl: data.image_url,
          publishedAt: new Date(data.published_at),
          readTime: data.read_time || 60,
          shareCount: data.share_count || 0,
          emailCount: data.email_count || 0,
          bookmarkCount: data.bookmark_count || 0,
          viewCount: data.view_count || 0,
          isBookmarked: false
        });
      });
      
      // If no articles in Firebase, fall back to mock data for now
      if (fetchedArticles.length === 0) {
        console.log('No articles in Firebase, using mock data');
        const { mockArticles } = await import('./data/mockArticles');
        setArticles(mockArticles);
      } else {
        setArticles(fetchedArticles);
      }
    } catch (error) {
      console.error('Error fetching articles:', error);
      // Fallback to mock data
      const { mockArticles } = await import('./data/mockArticles');
      setArticles(mockArticles);
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

  // Enhanced touch handlers with drag feedback
  const onTouchStart = useCallback((e: React.TouchEvent) => {
    setTouchEnd(null);
    setTouchStart(e.targetTouches[0].clientY);
    setIsDragging(true);
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    setTouchEnd(e.targetTouches[0].clientY);
    
    // Visual drag feedback
    if (touchStart && contentRef.current) {
      const diff = touchStart - e.targetTouches[0].clientY;
      const translateY = diff * 0.3; // Reduced movement for subtle effect
      contentRef.current.style.transform = `translateY(${-translateY}px)`;
    }
  }, [touchStart]);

  const onTouchEnd = useCallback(() => {
    setIsDragging(false);
    if (!touchStart || !touchEnd) {
      if (contentRef.current) contentRef.current.style.transform = '';
      return;
    }
    
    const distance = touchStart - touchEnd;
    const minSwipeDistance = 80;
    
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
  }, [touchStart, touchEnd, handleSwipe]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowUp') handleSwipe('down');
      if (e.key === 'ArrowDown') handleSwipe('up');
      if (e.key === 'b') setShowBookmarks(prev => !prev);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSwipe]);

  // Reset index when genre changes
  useEffect(() => {
    setCurrentIndex(0);
  }, [selectedGenre]);

  if (!currentArticle) {
    return (
      <div className="h-screen bg-black flex items-center justify-center">
        <div className="text-center">
          <Music className="w-16 h-16 text-white/20 mx-auto mb-4" />
          <p className="text-white/40 text-lg">No articles found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-black flex flex-col overflow-hidden safe-area-top safe-area-bottom">
      {/* Premium Header */}
      <header className="flex items-center justify-between px-6 py-4 glass z-50 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-white/20 to-white/5 flex items-center justify-center">
            <Music className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight">miny-ven</h1>
            <p className="text-xs text-white/40">60-word music news</p>
          </div>
        </div>
        
        <button 
          onClick={() => setShowBookmarks(true)}
          className="relative group p-3 rounded-full hover:bg-white/5 transition-all duration-300 btn-press"
          aria-label="View bookmarks"
        >
          <Bookmark className={`w-6 h-6 transition-all duration-300 ${
            bookmarks.length > 0 
              ? 'text-yellow-400 fill-yellow-400 scale-110' 
              : 'text-white/60 group-hover:text-white'
          }`} />
          {bookmarks.length > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center animate-scale-in shadow-lg">
              {bookmarks.length}
            </span>
          )}
        </button>
      </header>

      {/* Genre Filter - Premium Pills */}
      <div className="px-6 py-4 border-b border-white/5">
        <div className="flex items-center justify-between mb-2">
          <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-1 flex-1">
            {genres.map((genre, index) => (
              <button
                key={genre.id}
                onClick={() => setSelectedGenre(genre.id)}
                className={`relative px-5 py-2.5 rounded-full text-sm font-medium whitespace-nowrap transition-all duration-300 btn-press ${
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
            className="ml-3 p-2 rounded-full bg-white/5 text-white/60 hover:bg-white/10 hover:text-white transition-all duration-300"
            disabled={loading}
            aria-label="Refresh articles"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div 
        className="flex-1 relative overflow-hidden"
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {/* Swipe Hints */}
        <div className="absolute inset-0 pointer-events-none z-10">
          <div className={`absolute top-8 left-1/2 -translate-x-1/2 transition-all duration-300 ${
            currentIndex > 0 ? 'opacity-40' : 'opacity-0'
          }`}>
            <ChevronUp className="w-8 h-8 text-white animate-pulse" />
          </div>
          <div className={`absolute bottom-32 left-1/2 -translate-x-1/2 transition-all duration-300 ${
            currentIndex < filteredArticles.length - 1 ? 'opacity-40' : 'opacity-0'
          }`}>
            <ChevronDown className="w-8 h-8 text-white animate-pulse" />
          </div>
        </div>

        {/* Article Card */}
        <div 
          ref={contentRef}
          className={`h-full transition-all duration-300 ${
            swipeDirection === 'up' ? 'animate-slide-up' : 
            swipeDirection === 'down' ? 'animate-slide-down' : 
            'animate-fade-in'
          } ${isDragging ? 'cursor-grabbing' : ''}`}
        >
          {loading ? (
            <ArticleSkeleton />
          ) : (
            <div className="h-full flex flex-col p-6">
              {/* Genre Badge & Source */}
              <div className="flex items-center justify-between mb-6">
                <span className={`inline-flex items-center px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider bg-gradient-to-r ${
                  genres.find(g => g.id === currentArticle.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                } text-white shadow-lg`}>
                  {currentArticle.primaryGenre}
                </span>
                <span className="text-xs text-white/40 font-medium">
                  {currentArticle.source}
                </span>
              </div>

              {/* Image with Gradient Overlay */}
              <div className="relative aspect-[16/10] mb-6 rounded-3xl overflow-hidden bg-gray-900 shadow-2xl card-hover group">
                <img 
                  src={currentArticle.imageUrl} 
                  alt={currentArticle.title}
                  className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
                <div className="absolute inset-0 bg-gradient-to-br from-black/30 to-transparent" />
              </div>

              {/* Title */}
              <h2 className="responsive-title font-bold text-white mb-4 leading-tight tracking-tight">
                {currentArticle.title}
              </h2>

              {/* Summary */}
              <p className="text-white/70 text-base sm:text-lg leading-relaxed mb-6 flex-1">
                {currentArticle.summary}
              </p>

              {/* Meta Info */}
              <div className="flex items-center justify-between mb-6 text-xs sm:text-sm text-white/40">
                <div className="flex items-center gap-4">
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
                  className="flex items-center gap-1.5 hover:text-white/60 transition-colors"
                  onClick={() => trackEvent('external_link', currentArticle.id)}
                >
                  <span>Source</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between gap-4 pt-4 border-t border-white/5">
                <div className="flex gap-3">
                  <button 
                    onClick={() => toggleBookmark(currentArticle.id)}
                    className={`group p-4 rounded-2xl transition-all duration-300 btn-press ${
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
                    className="group p-4 rounded-2xl bg-white/5 text-white/60 hover:bg-white/10 hover:text-white transition-all duration-300 btn-press"
                    aria-label="Share article"
                  >
                    <Share2 className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>
                  
                  <button 
                    onClick={handleEmail}
                    className="group p-4 rounded-2xl bg-white/5 text-white/60 hover:bg-white/10 hover:text-white transition-all duration-300 btn-press"
                    aria-label="Email article"
                  >
                    <Mail className="w-5 h-5 transition-transform duration-300 group-hover:scale-110" />
                  </button>
                </div>

                {/* Popularity Score */}
                <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/5">
                  <Heart className="w-4 h-4 text-red-500 fill-red-500" />
                  <span className="text-sm font-semibold text-white">
                    {(currentArticle.shareCount + currentArticle.emailCount).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="px-6 py-4 glass border-t border-white/5">
        <div className="flex justify-between items-center text-xs text-white/40 mb-3">
          <span className="font-medium">
            {currentIndex + 1} <span className="text-white/20">/</span> {filteredArticles.length}
          </span>
          <span className="text-white/30">Swipe to navigate</span>
        </div>
        <div className="w-full bg-white/5 rounded-full h-1.5 overflow-hidden">
          <div 
            className="h-full bg-gradient-to-r from-white/80 to-white rounded-full transition-all duration-500 ease-out"
            style={{ width: `${((currentIndex + 1) / filteredArticles.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Bookmarks Sidebar - Premium Drawer */}
      {showBookmarks && (
        <div className="fixed inset-0 z-50 animate-fade-in">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowBookmarks(false)}
          />
          <div className="absolute right-0 top-0 bottom-0 w-full max-w-md bg-black border-l border-white/10 animate-slide-in-up">
            <div className="h-full flex flex-col">
              {/* Drawer Header */}
              <div className="flex items-center justify-between px-6 py-5 border-b border-white/10 glass">
                <div>
                  <h2 className="text-xl font-bold">Bookmarks</h2>
                  <p className="text-xs text-white/40 mt-0.5">
                    {bookmarks.length} {bookmarks.length === 1 ? 'article' : 'articles'} saved
                  </p>
                </div>
                <button 
                  onClick={() => setShowBookmarks(false)}
                  className="p-3 rounded-full hover:bg-white/10 transition-all duration-300 btn-press"
                  aria-label="Close bookmarks"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Bookmarks List */}
              <div className="flex-1 overflow-y-auto p-6 scrollbar-hide">
                {bookmarks.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center">
                    <div className="w-20 h-20 rounded-full bg-white/5 flex items-center justify-center mb-4">
                      <Bookmark className="w-10 h-10 text-white/20" />
                    </div>
                    <p className="text-white/40 text-lg font-medium mb-2">No bookmarks yet</p>
                    <p className="text-white/20 text-sm">Articles you bookmark will appear here</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {articles.filter(a => bookmarks.includes(a.id)).map((article, index) => (
                      <div 
                        key={article.id}
                        className="group p-5 rounded-2xl bg-white/5 hover:bg-white/10 cursor-pointer transition-all duration-300 card-hover animate-slide-in-up"
                        style={{ animationDelay: `${index * 50}ms` }}
                        onClick={() => {
                          const idx = articles.findIndex(a => a.id === article.id);
                          setCurrentIndex(idx);
                          setShowBookmarks(false);
                        }}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <span className={`inline-block px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider mb-3 bg-gradient-to-r ${
                              genres.find(g => g.id === article.primaryGenre)?.gradient || 'from-gray-600 to-gray-500'
                            } text-white`}>
                              {article.primaryGenre}
                            </span>
                            <h3 className="text-white font-semibold leading-snug mb-2 line-clamp-2">
                              {article.title}
                            </h3>
                            <p className="text-white/40 text-sm line-clamp-2">
                              {article.summary}
                            </p>
                          </div>
                          <button 
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleBookmark(article.id);
                            }}
                            className="p-2 rounded-full bg-white/5 hover:bg-red-500/20 text-white/40 hover:text-red-400 transition-all duration-300 opacity-0 group-hover:opacity-100"
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
        </div>
      )}

      {/* Toast Notification */}
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

export default App;
