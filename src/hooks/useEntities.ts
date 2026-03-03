import { useState, useCallback } from 'react';
import type { Entity, EntityCategory } from '../types/entity';

export function useEntities() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEntities = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/entities.json');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const manifest = await response.json();

      const parsed: Entity[] = [];
      for (const [category, items] of Object.entries(manifest.categories || {})) {
        for (const item of items as any[]) {
          const id = item.name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '')
            .slice(0, 60);

          parsed.push({
            id,
            name: item.name,
            category: category as EntityCategory,
            mentionScore: item.mention_score || 0,
            bio: '',
            website: '',
            socialLinks: [],
            contactEmail: '',
            genreTags: [],
            location: '',
            notes: '',
            enriched: false,
            enrichedAt: '',
          });
        }
      }

      parsed.sort((a, b) => b.mentionScore - a.mentionScore);
      setEntities(parsed);
    } catch (err: any) {
      console.error('Error fetching entities:', err);
      setError(err.message || 'Failed to load entities');
    } finally {
      setLoading(false);
    }
  }, []);

  return { entities, loading, error, fetchEntities };
}
