import { useState, useCallback } from 'react';
import type { MusicNewsArticle, Genre } from '../types/news';

const FIRESTORE_BASE = 'https://firestore.googleapis.com/v1/projects';

export function useArticles() {
  const [articles, setArticles] = useState<MusicNewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchArticles = useCallback(async (genre: Genre = 'all') => {
    setLoading(true);
    setArticles([]);
    setError(null);

    try {
      const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID || 'miny-ven';
      const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;

      // Fetch metadata only (exclude heavy image_url and full_content fields)
      const metadataFields = [
        'title', 'summary', 'source', 'source_url', 'primary_genre',
        'secondary_genres', 'artist_names', 'image_source',
        'published_at', 'read_time', 'share_count', 'email_count',
        'bookmark_count', 'view_count', 'epk_url', 'epk_status'
      ];

      let allDocs: any[] = [];
      let pageToken = '';
      while (true) {
        const params = new URLSearchParams();
        if (apiKey) params.set('key', apiKey);
        params.set('pageSize', '300');
        if (pageToken) params.set('pageToken', pageToken);
        metadataFields.forEach(f => params.append('mask.fieldPaths', f));
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

      if (allDocs.length === 0) {
        setArticles([]);
        setLoading(false);
        return;
      }

      const fetchedArticles: MusicNewsArticle[] = allDocs.map((doc: any) => {
        const fields = doc.fields;
        const docId = doc.name.split('/').pop();

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
          epkUrl: getField(fields.epk_url) || '',
          epkStatus: getField(fields.epk_status) || 'missing',
        };
      });

      // Sort by published_at desc
      fetchedArticles.sort((a, b) =>
        b.publishedAt.getTime() - a.publishedAt.getTime()
      );

      // Filter by genre if needed
      const filtered = genre === 'all'
        ? fetchedArticles
        : fetchedArticles.filter(a => a.primaryGenre === genre);

      setArticles(filtered);
    } catch (err: any) {
      console.error('Error fetching articles:', err);
      setArticles([]);
      setError(err.message || 'Failed to load articles');
    } finally {
      setLoading(false);
    }
  }, []);

  return { articles, loading, error, fetchArticles };
}
