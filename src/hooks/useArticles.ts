import { useState, useCallback, useRef } from 'react';
import type { MusicNewsArticle, Genre } from '../types/news';
import {
  fetchArticles as fetchArticlesFromPb,
  LIST_PAGE_SIZE,
} from '../utils/articles';

export function useArticles() {
  const [articles, setArticles] = useState<MusicNewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [genre, setGenre] = useState<Genre>('all');

  const abortRef = useRef<AbortController | null>(null);
  const pageRef = useRef(1);

  const fetchArticles = useCallback(async (nextGenre: Genre = 'all') => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setError(null);
    setGenre(nextGenre);
    // Keep last good data visible until the new page arrives (avoids empty flash).

    try {
      const result = await fetchArticlesFromPb(nextGenre, {
        page: 1,
        perPage: LIST_PAGE_SIZE,
        signal: ac.signal,
      });
      if (ac.signal.aborted) return;

      pageRef.current = 1;
      setPage(1);
      setArticles(result.articles);
      setTotalItems(result.totalItems);
      setTotalPages(result.totalPages);
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      console.error('Error fetching articles:', err);
      setError(err.message || 'Failed to load articles from PocketBase');
      // Only wipe if we have nothing to show
      setArticles((prev) => (prev.length ? prev : []));
    } finally {
      if (!ac.signal.aborted) setLoading(false);
    }
  }, []);

  const loadMore = useCallback(async () => {
    if (loading || loadingMore) return;
    if (pageRef.current >= totalPages) return;

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    const nextPage = pageRef.current + 1;
    setLoadingMore(true);
    setError(null);

    try {
      const result = await fetchArticlesFromPb(genre, {
        page: nextPage,
        perPage: LIST_PAGE_SIZE,
        signal: ac.signal,
      });
      if (ac.signal.aborted) return;

      pageRef.current = result.page;
      setPage(result.page);
      setTotalItems(result.totalItems);
      setTotalPages(result.totalPages);
      setArticles((prev) => {
        const seen = new Set(prev.map((a) => a.id));
        const appended = result.articles.filter((a) => !seen.has(a.id));
        return [...prev, ...appended];
      });
    } catch (err: any) {
      if (err?.name === 'AbortError') return;
      console.error('Error loading more articles:', err);
      setError(err.message || 'Failed to load more articles');
    } finally {
      if (!ac.signal.aborted) setLoadingMore(false);
    }
  }, [genre, loading, loadingMore, totalPages]);

  const canLoadMore = page < totalPages && !loading;

  return {
    articles,
    loading,
    loadingMore,
    error,
    page,
    totalItems,
    totalPages,
    canLoadMore,
    fetchArticles,
    loadMore,
  };
}
