export interface MusicNewsArticle {
  id: string;
  title: string;
  summary: string;
  fullContent?: string;
  source: string;
  sourceUrl: string;
  primaryGenre: 'gospel' | 'hiphop' | 'pop' | 'rock' | 'electronic';
  secondaryGenres: string[];
  artistNames: string[];
  imageUrl?: string;
  publishedAt: Date;
  readTime: number;
  shareCount: number;
  emailCount: number;
  bookmarkCount: number;
  viewCount: number;
  isBookmarked?: boolean;
}

export type Genre = 'gospel' | 'hiphop' | 'pop' | 'rock' | 'electronic' | 'all';

export interface AnalyticsEvent {
  articleId: string;
  eventType: 'view' | 'share' | 'email' | 'bookmark' | 'swipe';
  genre: string;
  timestamp: Date;
  sessionId: string;
}

export interface GenreStats {
  genre: Genre;
  articleCount: number;
  totalViews: number;
  totalShares: number;
  totalEmails: number;
  totalBookmarks: number;
  lastUpdated: Date;
}
