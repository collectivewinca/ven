import type { MusicNewsArticle, Genre } from '../types/news';

// Articles migrated from Firestore to PocketBase (miny-database.exe.xyz) in
// 2026-05. The old miny-ven Firestore project is a stale April snapshot
// (last article 2026-04-28) and is no longer written to. PB is the source of
// truth (46k+ articles, curated/curator/entity fields Firestore lacked).
//
// sm_musicians (EPK source) lives on the same PB instance — see useArtistEpk.

const PB_BASE = 'https://miny-database.exe.xyz';
const PB_COLLECTION = 'articles';

// Fields requested from PocketBase. Keeps the payload small by excluding
// heavy fields (full_content) unless needed. EPK URLs are resolved
// client-side via useArtistEpk, NOT read from PB epk_url/epk_status (those
// fields exist on PB records but are stubs — the real EPK lookup scans
// article text against the sm_musicians index).
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
  'curated',
  'curator',
  'entity_rc_url',
];

function mapPbArticle(record: any): MusicNewsArticle {
  return {
    id: record.id,
    title: record.title || '',
    summary: record.summary || '',
    source: record.source || '',
    sourceUrl: record.source_url || '',
    primaryGenre: record.primary_genre || '',
    secondaryGenres: record.secondary_genres || [],
    artistNames: record.artist_names || [],
    imageUrl: record.image_url || '',
    imageSource: record.image_source || '',
    publishedAt: new Date(record.published_at || Date.now()),
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

export async function fetchArticles(genre: Genre = 'all'): Promise<MusicNewsArticle[]> {
  const allRecords: any[] = [];
  let page = 1;

  while (true) {
    const params = new URLSearchParams();
    params.set('perPage', '500');
    params.set('page', String(page));
    params.set('fields', ARTICLE_FIELDS.join(','));
    // Sort by published_at descending — PB supports the sort param.
    params.set('sort', '-published_at');

    const url = `${PB_BASE}/api/collections/${PB_COLLECTION}/records?${params}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    if (data.items) allRecords.push(...data.items);
    if (page >= Number(data.totalPages || 1) || !data.items?.length) break;
    page += 1;
  }

  const fetchedArticles: MusicNewsArticle[] = allRecords.map(mapPbArticle);

  return genre === 'all'
    ? fetchedArticles
    : fetchedArticles.filter((a) => a.primaryGenre === genre);
}