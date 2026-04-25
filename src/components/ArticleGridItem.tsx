import { LazyArticleImage } from './LazyArticleImage';
import type { MusicNewsArticle } from '../types/news';

interface ArticleGridItemProps {
  article: MusicNewsArticle;
  onSelect: (id: string) => void;
  isActive?: boolean;
}

export function ArticleGridItem({ article, onSelect, isActive }: ArticleGridItemProps) {
  return (
    <button
      onClick={() => onSelect(article.id)}
      className={`flex gap-3 p-2 rounded-lg text-left transition-colors w-full ${
        isActive
          ? 'bg-[var(--accent-primary)]/10 border border-[var(--accent-primary)]'
          : 'hover:bg-[var(--background-secondary)]'
      }`}
    >
      <div className="flex-shrink-0 w-20 h-20 rounded-lg overflow-hidden bg-[var(--skeleton-base)]">
        <LazyArticleImage
          articleId={article.id}
          imageSource={article.imageSource}
          primaryGenre={article.primaryGenre}
          className="w-20 h-20 object-cover"
        />
      </div>
      <div className="flex flex-col justify-center min-w-0 flex-1">
        <h3 className="text-[0.8rem] font-semibold line-clamp-2 leading-tight text-[var(--text-primary)]">
          {article.title}
        </h3>
        <p className="text-[0.7rem] text-[var(--text-muted)] truncate mt-1">
          {article.source}
        </p>
      </div>
    </button>
  );
}
