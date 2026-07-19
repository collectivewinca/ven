import { useRef, useState } from 'react';
import type { MusicNewsArticle } from '../types/news';
import { LazyArticleImage } from './LazyArticleImage';
import { GenreBadge } from './GenreBadge';
import {
  Bookmark,
  Share2,
  Volume2,
  Pause,
  RefreshCw,
  ExternalLink,
  Music,
} from 'lucide-react';

interface ArticleCardProps {
  article: MusicNewsArticle;
  onNext: () => void;
  onPrev: () => void;
  isPlaying?: boolean;
  onPlay?: () => void;
  bookmarks: string[];
  toggleBookmark: (id: string) => void;
  handleShare: () => void;
  handleListen: () => void;
  isAudioPlaying: boolean;
  audioLoading: boolean;
  audioArticleId: string | null;
}

const SWIPE_THRESHOLD = 50;

export function ArticleCard({
  article,
  onNext,
  onPrev,
  bookmarks,
  toggleBookmark,
  handleShare,
  handleListen,
  isAudioPlaying,
  audioLoading,
  audioArticleId,
}: ArticleCardProps) {
  const touchStartX = useRef<number>(0);
  const touchCurrentX = useRef<number>(0);
  const [isDragging, setIsDragging] = useState(false);
  const [translateX, setTranslateX] = useState(0);

  const isBookmarked = bookmarks.includes(article.id);

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    touchCurrentX.current = e.touches[0].clientX;
    setIsDragging(true);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    touchCurrentX.current = e.touches[0].clientX;
    const delta = touchCurrentX.current - touchStartX.current;
    setTranslateX(delta);
  };

  const handleTouchEnd = () => {
    const delta = touchCurrentX.current - touchStartX.current;
    if (Math.abs(delta) > SWIPE_THRESHOLD) {
      if (delta < 0) {
        onNext();
      } else {
        onPrev();
      }
    }
    setTranslateX(0);
    setIsDragging(false);
  };

  const isArticleAudioPlaying = isAudioPlaying && audioArticleId === article.id;
  const isArticleAudioLoading = audioLoading && audioArticleId === article.id;

  const renderAudioButton = () => {
    if (isArticleAudioLoading) {
      return (
        <button
          onClick={handleListen}
          className="p-2 rounded-full hover:bg-white/20 transition-colors text-green-400"
          aria-label="Loading audio"
        >
          <RefreshCw className="w-5 h-5 animate-spin" />
        </button>
      );
    }
    if (isArticleAudioPlaying) {
      return (
        <button
          onClick={handleListen}
          className="p-2 rounded-full hover:bg-white/20 transition-colors text-green-400"
          aria-label="Pause audio"
        >
          <Pause className="w-5 h-5" />
        </button>
      );
    }
    return (
      <button
        onClick={handleListen}
        className="p-2 rounded-full hover:bg-white/20 transition-colors text-green-400"
        aria-label="Listen to article"
      >
        <Volume2 className="w-5 h-5" />
      </button>
    );
  };

  return (
    <div
      className="relative w-full overflow-hidden rounded-2xl bg-[var(--card-bg)] shadow-lg select-none"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{
        transform: `translateX(${translateX}px)`,
        transition: isDragging ? 'none' : 'transform 0.3s ease-out',
      }}
    >
      <div className="relative aspect-video w-full overflow-hidden rounded-t-2xl">
        <LazyArticleImage
          articleId={article.id}
          imageSource={article.imageSource}
          primaryGenre={article.primaryGenre}
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
        <div className="absolute top-3 left-3">
          <GenreBadge genre={article.primaryGenre} size="sm" />
        </div>
      </div>

      <div className="p-4 space-y-3">
        <h2 className="text-lg font-bold leading-tight line-clamp-2" style={{ fontSize: '1.25rem', lineHeight: 1.3 }}>
          {article.title}
        </h2>

        <p className="text-sm leading-relaxed line-clamp-3" style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>
          {article.summary}
        </p>

        <div className="flex items-center gap-1 pt-2">
          <button
            onClick={() => toggleBookmark(article.id)}
            className={`p-2 rounded-full hover:bg-white/20 transition-colors ${isBookmarked ? 'text-yellow-400' : 'text-green-400'}`}
            aria-label={isBookmarked ? 'Remove bookmark' : 'Add bookmark'}
          >
            <Bookmark className={`w-5 h-5 ${isBookmarked ? 'fill-current' : ''}`} />
          </button>

          <button
            onClick={handleShare}
            className="p-2 rounded-full hover:bg-white/20 transition-colors text-green-400"
            aria-label="Share article"
          >
            <Share2 className="w-5 h-5" />
          </button>

          {renderAudioButton()}

          {article.epkUrl && (
            <a
              href={article.epkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-2 rounded-full hover:bg-white/20 transition-colors text-cyan-300"
              aria-label="View artist EPK on RapidConnect"
              title="RapidConnect EPK"
            >
              <Music className="w-5 h-5" />
            </a>
          )}

          <a
            href={article.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 rounded-full hover:bg-white/20 transition-colors text-green-400 ml-auto"
            aria-label="Open original article"
          >
            <ExternalLink className="w-5 h-5" />
          </a>
        </div>
      </div>
    </div>
  );
}
