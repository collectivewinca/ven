export interface MusicNewsArticle {
  id: string;
  title: string;
  summary: string;
  source: string;
  sourceUrl: string;
  primaryGenre: 'gospel' | 'hiphop' | 'pop' | 'rock' | 'electronic' | 'tech';
  secondaryGenres: string[];
  artistNames: string[];
  imageUrl?: string;
  imageSource?: string;
  publishedAt: Date;
  readTime: number;
  shareCount: number;
  emailCount: number;
  bookmarkCount: number;
  viewCount: number;
  isBookmarked?: boolean;
  location?: string;
  epkUrl?: string;
  epkStatus?: 'ready' | 'pending' | 'missing';
}

export type Genre = 'gospel' | 'hiphop' | 'pop' | 'rock' | 'electronic' | 'tech' | 'all';

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
