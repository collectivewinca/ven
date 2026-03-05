export function ArticleSkeleton({ variant = 'featured' }: { variant?: 'featured' | 'compact' }) {
  if (variant === 'compact') {
    return (
      <div className="rounded-2xl overflow-hidden animate-pulse" style={{ background: 'var(--card-bg)' }}>
        <div className="aspect-video skeleton" style={{ background: 'var(--skeleton-base)' }} />
        <div className="p-3 space-y-2">
          <div className="h-4 rounded w-3/4" style={{ background: 'var(--skeleton-shine)' }} />
          <div className="h-3 rounded w-1/2" style={{ background: 'var(--skeleton-base)' }} />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl overflow-hidden animate-pulse shadow-2xl" style={{ background: 'var(--card-bg)' }}>
      <div className="aspect-[16/9] skeleton" style={{ background: 'var(--skeleton-base)' }} />
      <div className="p-6 space-y-4">
        <div className="flex gap-2">
          <div className="h-6 w-20 rounded-full" style={{ background: 'var(--skeleton-shine)' }} />
          <div className="h-6 w-24 rounded-full" style={{ background: 'var(--skeleton-base)' }} />
        </div>
        <div className="space-y-2">
          <div className="h-7 rounded w-3/4" style={{ background: 'var(--skeleton-shine)' }} />
          <div className="h-7 rounded w-1/2" style={{ background: 'var(--skeleton-shine)' }} />
        </div>
        <div className="space-y-2">
          <div className="h-4 rounded w-full" style={{ background: 'var(--skeleton-base)' }} />
          <div className="h-4 rounded w-5/6" style={{ background: 'var(--skeleton-base)' }} />
          <div className="h-4 rounded w-4/5" style={{ background: 'var(--skeleton-base)' }} />
        </div>
      </div>
    </div>
  );
}
