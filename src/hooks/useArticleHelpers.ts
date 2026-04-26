export const AI_PROMPT_PREFIXES = [
  /^key points?:/i,
  /^the context (involves|is|about):/i,
  /^key elements( from the context)?:?/i,
  /^key facts:?/i,
  /^- original:/i,
  /^\d+\. /,
  /^- (?:artist|news|song|album|video|premiere|exclusive|breaking|watch|unveiled|revealed|must-see|inside|cont|review|interview|feature):/i,
];

export function isCleanHeadline(title: string): boolean {
  return !AI_PROMPT_PREFIXES.some((pattern) => pattern.test(title));
}

export function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export const GENRE_GRADIENTS: Record<string, string> = {
  gospel: 'from-amber-500 to-amber-600',
  hiphop: 'from-violet-500 to-violet-600',
  pop: 'from-rose-500 to-rose-600',
  rock: 'from-red-500 to-red-700',
  electronic: 'from-cyan-500 to-cyan-600',
  tech: 'from-emerald-600 to-teal-600',
};
