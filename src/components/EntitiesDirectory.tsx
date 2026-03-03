import { useState, useEffect, useMemo } from 'react';
import { X, Search, Mic2, Music, MapPin, Sparkles, Disc3, SlidersHorizontal, Building2, ChevronRight, ExternalLink, CheckCircle2 } from 'lucide-react';
import { useEntities } from '../hooks/useEntities';
import type { EntityCategory } from '../types/entity';
import { CATEGORY_META } from '../types/entity';

const CATEGORY_ICONS: Record<EntityCategory, React.ReactNode> = {
  artists: <Mic2 className="w-4 h-4" />,
  bands: <Music className="w-4 h-4" />,
  venues: <MapPin className="w-4 h-4" />,
  festivals: <Sparkles className="w-4 h-4" />,
  labels: <Disc3 className="w-4 h-4" />,
  producers: <SlidersHorizontal className="w-4 h-4" />,
  music_orgs: <Building2 className="w-4 h-4" />,
};

const ALL_CATEGORIES: EntityCategory[] = [
  'artists', 'bands', 'venues', 'festivals', 'labels', 'producers', 'music_orgs',
];

interface Props {
  onClose: () => void;
}

export function EntitiesDirectory({ onClose }: Props) {
  const { entities, loading, fetchEntities } = useEntities();
  const [activeCategory, setActiveCategory] = useState<EntityCategory | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchEntities();
  }, [fetchEntities]);

  const filtered = useMemo(() => {
    let result = entities;
    if (activeCategory !== 'all') {
      result = result.filter(e => e.category === activeCategory);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(e => e.name.toLowerCase().includes(q));
    }
    return result;
  }, [entities, activeCategory, searchQuery]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: entities.length };
    for (const e of entities) {
      counts[e.category] = (counts[e.category] || 0) + 1;
    }
    return counts;
  }, [entities]);

  const enrichedCount = entities.filter(e => e.enriched).length;

  return (
    <div className="fixed inset-0 z-[70] flex flex-col bg-white animate-fade-in">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white/80 backdrop-blur-md">
        <div className="mx-auto max-w-5xl px-4 sm:px-6">
          <div className="flex items-center justify-between py-4">
            <div>
              <h1 className="text-lg font-bold text-slate-900 tracking-tight">Directory</h1>
              <p className="text-xs text-slate-500 mt-0.5">
                {entities.length} entities &middot; {enrichedCount} enriched
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-full border border-slate-200 bg-white p-2.5 text-slate-500 transition hover:bg-slate-50"
              aria-label="Close directory"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Search */}
          <div className="relative pb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" style={{ top: 'calc(50% - 6px)' }} />
            <input
              type="text"
              placeholder="Search entities..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-4 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </div>

          {/* Category tabs */}
          <div className="flex gap-1.5 overflow-x-auto pb-3 scrollbar-hide -mx-4 px-4 sm:-mx-6 sm:px-6">
            <button
              onClick={() => setActiveCategory('all')}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition ${
                activeCategory === 'all'
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              All ({categoryCounts.all || 0})
            </button>
            {ALL_CATEGORIES.map(cat => (
              <button
                key={cat}
                onClick={() => setActiveCategory(cat)}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition inline-flex items-center gap-1.5 ${
                  activeCategory === cat
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {CATEGORY_ICONS[cat]}
                {CATEGORY_META[cat].label} ({categoryCounts[cat] || 0})
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Entity list */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 py-4">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-16 rounded-xl bg-slate-100 animate-pulse" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-20 text-center">
              <p className="text-sm text-slate-500">No entities found</p>
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map(entity => (
                <div
                  key={entity.id}
                  className="group rounded-xl border border-slate-200 bg-white p-3 sm:p-4 transition hover:border-slate-300 hover:shadow-sm"
                >
                  <div className="flex items-start gap-3">
                    {/* Category icon */}
                    <div className={`shrink-0 w-9 h-9 rounded-lg bg-gradient-to-br ${CATEGORY_META[entity.category]?.color || 'from-slate-400 to-slate-500'} flex items-center justify-center text-white`}>
                      {CATEGORY_ICONS[entity.category]}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-slate-900 truncate">
                          {entity.name}
                        </h3>
                        {entity.enriched && (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs text-slate-500">
                          {CATEGORY_META[entity.category]?.label || entity.category}
                        </span>
                        <span className="text-xs text-slate-300">&middot;</span>
                        <span className="text-xs text-slate-500">
                          {entity.mentionScore} mentions
                        </span>
                        {entity.location && (
                          <>
                            <span className="text-xs text-slate-300">&middot;</span>
                            <span className="text-xs text-slate-500">{entity.location}</span>
                          </>
                        )}
                      </div>
                      {entity.bio && (
                        <p className="text-xs text-slate-600 mt-1 line-clamp-2">{entity.bio}</p>
                      )}
                      {entity.genreTags.length > 0 && (
                        <div className="flex gap-1 mt-1.5 flex-wrap">
                          {entity.genreTags.map(tag => (
                            <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="shrink-0 flex items-center gap-1">
                      {entity.website && (
                        <a
                          href={entity.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
                          aria-label="Visit website"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                      <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-slate-500 transition" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
