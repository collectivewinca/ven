import { useState, useCallback } from 'react';
import type { MusicNewsArticle, Genre } from '../types/news';
import { fetchArticles as fetchArticlesFromPb } from '../utils/articles';

export function useArticles() {
  const [articles, setArticles] = useState<MusicNewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchArticles = useCallback(async (genre: Genre = 'all') => {
    setLoading(true);
    setArticles([]);
    setError(null);

    try {
      const result = await fetchArticlesFromPb(genre);
      setArticles(result);
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