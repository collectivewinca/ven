import { useState, useEffect } from 'react';

const FIRESTORE_BASE = 'https://firestore.googleapis.com/v1/projects';
const PROJECT_ID = import.meta.env.VITE_FIREBASE_PROJECT_ID || 'miny-ven';

// Image cache: docId -> image URL (persists across re-renders)
const imageCache = new Map<string, string>();

export const genrePlaceholder = (genre?: string) => {
  const key = (genre || 'mixed').toLowerCase();
  const palette: Record<string, [string, string]> = {
    gospel: ['#f59e0b', '#f97316'],
    hiphop: ['#0ea5e9', '#2563eb'],
    pop: ['#ec4899', '#f43f5e'],
    rock: ['#ef4444', '#7c3aed'],
    electronic: ['#14b8a6', '#0ea5e9'],
    tech: ['#10b981', '#0f766e'],
    mixed: ['#4b5563', '#111827'],
  };
  const [a, b] = palette[key] || palette.mixed;
  const label = (genre || 'music').toUpperCase();
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1600 900'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0%' stop-color='${a}'/><stop offset='100%' stop-color='${b}'/></linearGradient></defs><rect width='1600' height='900' fill='url(#g)'/><circle cx='1320' cy='160' r='220' fill='rgba(255,255,255,0.15)'/><circle cx='280' cy='760' r='280' fill='rgba(255,255,255,0.12)'/><text x='80' y='820' font-size='92' fill='rgba(255,255,255,0.85)' font-family='system-ui, -apple-system, Segoe UI, sans-serif' font-weight='700'>${label}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

export function LazyArticleImage({ articleId, imageSource, primaryGenre, className }: {
  articleId: string;
  imageSource?: string;
  primaryGenre?: string;
  className?: string;
}) {
  const [src, setSrc] = useState<string>(() => imageCache.get(articleId) || '');
  const [loading, setLoading] = useState(!imageCache.has(articleId));
  const fallback = genrePlaceholder(primaryGenre);
  const logoFallback = '/branding/minylogo.png';

  useEffect(() => {
    if (imageCache.has(articleId)) {
      setSrc(imageCache.get(articleId)!);
      setLoading(false);
      return;
    }
    if (!imageSource || imageSource === 'none') {
      setSrc(fallback);
      setLoading(false);
      imageCache.set(articleId, fallback);
      return;
    }
    let cancelled = false;
    const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;
    const params = new URLSearchParams();
    if (apiKey) params.set('key', apiKey);
    params.append('mask.fieldPaths', 'image_url');
    const url = `${FIRESTORE_BASE}/${PROJECT_ID}/databases/(default)/documents/articles/${articleId}?${params}`;
    fetch(url).then(r => r.json()).then(doc => {
      if (cancelled) return;
      const raw = doc?.fields?.image_url?.stringValue?.trim() || '';
      const resolved = (raw && !raw.includes('images.unsplash.com')) ? raw : fallback;
      imageCache.set(articleId, resolved);
      setSrc(resolved);
      setLoading(false);
    }).catch(() => {
      if (!cancelled) {
        setSrc(fallback);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [articleId, imageSource]);

  if (loading) {
    return <div className={`${className} animate-pulse`} style={{ background: 'var(--skeleton-base)' }} />;
  }

  return (
    <img
      src={src}
      alt=""
      className={className}
      onError={(e) => {
        const img = e.target as HTMLImageElement;
        if (img.src !== fallback) {
          img.src = fallback;
          return;
        }
        img.src = logoFallback;
      }}
    />
  );
}
