export function ArticleSkeleton() {
  return (
    <div className="h-full flex flex-col p-4 sm:p-6 animate-pulse">
      <div className="w-20 h-6 bg-slate-200 rounded-full mb-4" />
      <div className="relative aspect-[4/3] mb-4 rounded-2xl bg-slate-100 overflow-hidden">
        <div className="absolute inset-0 skeleton" />
      </div>
      <div className="space-y-3 mb-4">
        <div className="h-7 bg-slate-200 rounded-lg w-3/4" />
        <div className="h-7 bg-slate-200 rounded-lg w-1/2" />
      </div>
      <div className="space-y-2 flex-1">
        <div className="h-4 bg-slate-100 rounded w-full" />
        <div className="h-4 bg-slate-100 rounded w-full" />
        <div className="h-4 bg-slate-100 rounded w-5/6" />
        <div className="h-4 bg-slate-100 rounded w-4/5" />
      </div>
    </div>
  );
}
