import type { Genre } from '../types/news';

interface GenreBadgeProps {
  genre: Genre;
  size?: 'sm' | 'md';
}

const genreGradients: Record<Genre, string> = {
  gospel: 'from-amber-500 to-amber-600',
  hiphop: 'from-violet-500 to-violet-600',
  pop: 'from-rose-500 to-rose-600',
  rock: 'from-red-500 to-red-700',
  electronic: 'from-cyan-500 to-cyan-600',
  tech: 'from-emerald-600 to-teal-600',
  all: 'from-gray-500 to-gray-600',
};

const sizeClasses = {
  sm: 'text-xs px-2 py-0.5',
  md: 'text-sm px-3 py-1',
};

export function GenreBadge({ genre, size = 'md' }: GenreBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full bg-gradient-to-r font-medium text-white ${genreGradients[genre]} ${sizeClasses[size]}`}
    >
      {genre.charAt(0).toUpperCase() + genre.slice(1)}
    </span>
  );
}
