import { RefreshCw } from 'lucide-react';

export function PullToRefresh({ pullDistance, isPulling }: { pullDistance: number; isPulling: boolean }) {
  if (!isPulling || pullDistance < 20) return null;

  const opacity = Math.min(pullDistance / 80, 1);
  const rotation = Math.min((pullDistance / 100) * 360, 360);

  return (
    <div
      className="absolute top-0 left-0 right-0 flex justify-center items-center z-20 pointer-events-none"
      style={{
        opacity,
        transform: `translateY(${Math.min(pullDistance * 0.5, 60)}px)`,
        paddingTop: 'env(safe-area-inset-top)'
      }}
    >
      <div
        className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center"
        style={{ transform: `rotate(${rotation}deg)` }}
      >
        <RefreshCw className="w-5 h-5 text-white" />
      </div>
    </div>
  );
}
