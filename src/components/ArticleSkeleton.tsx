export function ArticleSkeleton({ variant = 'featured' }: { variant?: 'featured' | 'compact' }) {
  if (variant === 'compact') {
    return (
      <div className="rounded-2xl bg-white/5 overflow-hidden animate-pulse">
        <div className="aspect-video bg-white/5 skeleton" />
        <div className="p-3 space-y-2">
          <div className="h-4 bg-white/8 rounded w-3/4" />
          <div className="h-3 bg-white/5 rounded w-1/2" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-white/5 overflow-hidden animate-pulse shadow-2xl">
      <div className="aspect-[16/9] bg-white/5 skeleton" />
      <div className="p-6 space-y-4">
        <div className="flex gap-2">
          <div className="h-6 w-20 bg-white/8 rounded-full" />
          <div className="h-6 w-24 bg-white/5 rounded-full" />
        </div>
        <div className="space-y-2">
          <div className="h-7 bg-white/8 rounded w-3/4" />
          <div className="h-7 bg-white/8 rounded w-1/2" />
        </div>
        <div className="space-y-2">
          <div className="h-4 bg-white/5 rounded w-full" />
          <div className="h-4 bg-white/5 rounded w-5/6" />
          <div className="h-4 bg-white/5 rounded w-4/5" />
        </div>
      </div>
    </div>
  );
}
