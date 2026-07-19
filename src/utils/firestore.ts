import type { MusicNewsArticle, Genre } from '../types/news';

const FIRESTORE_BASE = 'https://firestore.googleapis.com/v1/projects';

// Fields fetched from Firestore. The mask keeps the payload small by
// excluding heavy fields (image_url, full_content). EPK URLs are resolved
// client-side via useArtistEpk (PocketBase sm_musicians), NOT read from
// Firestore — the epk_url/epk_status fields were never written by the scraper
// and were removed from this mask.
export const ARTICLE_METADATA_FIELDS = [
  'title', 'summary', 'source', 'source_url', 'primary_genre',
  'secondary_genres', 'artist_names', 'image_source',
  'published_at', 'read_time', 'share_count', 'email_count',
  'bookmark_count', 'view_count', 'location',
];

function getField(field: any): any {
  if (!field) return null;
  if (field.stringValue !== undefined) return field.stringValue;
  if (field.integerValue !== undefined) return parseInt(field.integerValue);
  if (field.doubleValue !== undefined) return field.doubleValue;
  if (field.arrayValue) {
    return (field.arrayValue.values || []).map((v: any) => v.stringValue || '');
  }
  return null;
}

export function mapFirestoreArticle(doc: any): MusicNewsArticle {
  const fields = doc.fields;
  const docId = doc.name.split('/').pop();
  return {
    id: docId,
    title: getField(fields.title) || '',
    summary: getField(fields.summary) || '',
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
    location: getField(fields.location) || '',
    epkUrl: '',
    epkStatus: 'missing',
  };
}

export async function fetchArticlesFromFirestore(genre: Genre = 'all'): Promise<MusicNewsArticle[]> {
  const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID || 'miny-ven';
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;

  let allDocs: any[] = [];
  let pageToken = '';
  while (true) {
    const params = new URLSearchParams();
    if (apiKey) params.set('key', apiKey);
    params.set('pageSize', '300');
    if (pageToken) params.set('pageToken', pageToken);
    ARTICLE_METADATA_FIELDS.forEach((f) => params.append('mask.fieldPaths', f));
    const url = `${FIRESTORE_BASE}/${projectId}/databases/(default)/documents/articles?${params}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    allDocs = allDocs.concat(data.documents || []);
    pageToken = data.nextPageToken || '';
    if (!pageToken) break;
  }

  const fetchedArticles: MusicNewsArticle[] = allDocs.map(mapFirestoreArticle);
  fetchedArticles.sort((a, b) => b.publishedAt.getTime() - a.publishedAt.getTime());

  return genre === 'all'
    ? fetchedArticles
    : fetchedArticles.filter((a) => a.primaryGenre === genre);
}