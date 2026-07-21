import type { MusicNewsArticle, Genre } from '../types/news';

// Articles read from PocketBase (miny-database.exe.xyz). Firebase/Firestore
// was removed 2026-07 — PB is the source of truth (~47k+ articles).
//
// IMPORTANT: never walk every PB page into the browser. Callers must pass
// page/perPage and load more on demand. Full-corpus client pagination
// (~95 × 500) was a production failure mode (net::ERR_FAILED mid-fetch).

const PB_BASE = 'https://miny-database.exe.xyz';
const PB_COLLECTION = 'articles';

/** Default first-window size for the card feed (home). */
export const HOME_PAGE_SIZE = 80;

/** Default page size for the directory table (/list). */
export const LIST_PAGE_SIZE = 25;

// Fields requested from PocketBase. Keep payload small — no full_content.
// curated/curator/entity_rc_url intentionally omitted until UI uses them.
const ARTICLE_FIELDS = [
  'id',
  'title',
  'summary',
  'source',
  'source_url',
  'primary_genre',
  'secondary_genres',
  'artist_names',
  'image_url',
  'image_source',
  'published_at',
  'read_time',
  'share_count',
  'email_count',
  'bookmark_count',
  'view_count',
  'location',
];

export type FetchArticlesOptions = {
  page?: number;
  perPage?: number;
  signal?: AbortSignal;
};

export type FetchArticlesResult = {
  articles: MusicNewsArticle[];
  totalItems: number;
  totalPages: number;
  page: number;
  perPage: number;
};

/** Normalize PB date strings like "2026-04-28 17:00:00.000Z" for Safari. */
function parsePbDate(value: unknown): Date {
  if (value == null || value === '') return new Date(0);
  const raw = String(value);
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? new Date(0) : d;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function mapPbArticle(record: any): MusicNewsArticle {
  return {
    id: record.id,
    title: record.title || '',
    summary: record.summary || '',
    source: record.source || '',
    sourceUrl: record.source_url || '',
    primaryGenre: record.primary_genre || '',
    secondaryGenres: asStringArray(record.secondary_genres),
    artistNames: asStringArray(record.artist_names),
    imageUrl: record.image_url || '',
    imageSource: record.image_source || '',
    publishedAt: parsePbDate(record.published_at),
    readTime: record.read_time || 60,
    shareCount: record.share_count || 0,
    emailCount: record.email_count || 0,
    bookmarkCount: record.bookmark_count || 0,
    viewCount: record.view_count || 0,
    isBookmarked: false,
    location: record.location || '',
    epkUrl: '',
    epkStatus: 'missing',
  };
}

/**
 * Fetch one page of articles from PocketBase.
 * Genre is filtered server-side when not "all".
 */
export async function fetchArticles(
  genre: Genre = 'all',
  opts: FetchArticlesOptions = {},
): Promise<FetchArticlesResult> {
  const page = Math.max(1, opts.page ?? 1);
  const perPage = Math.min(500, Math.max(1, opts.perPage ?? HOME_PAGE_SIZE));

  const params = new URLSearchParams();
  params.set('perPage', String(perPage));
  params.set('page', String(page));
  params.set('fields', ARTICLE_FIELDS.join(','));
  params.set('sort', '-published_at');

  if (genre !== 'all') {
    // PocketBase filter: match primary_genre exactly (same as prior client filter).
    const safe = String(genre).replace(/"/g, '\\"');
    params.set('filter', `primary_genre = "${safe}"`);
  }

  const url = `${PB_BASE}/api/collections/${PB_COLLECTION}/records?${params}`;
  const response = await fetch(url, { signal: opts.signal });
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  const items = Array.isArray(data.items) ? data.items : [];

  return {
    articles: items.map(mapPbArticle),
    totalItems: Number(data.totalItems) || 0,
    totalPages: Number(data.totalPages) || 1,
    page,
    perPage,
  };
}
