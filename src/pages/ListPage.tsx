import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { useArticles } from '../hooks/useArticles';

const PAGE_SIZE = 25;

function formatDate(value: Date) {
  if (Number.isNaN(value.getTime())) return 'Unknown';

  return value.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function ListPage() {
  const { articles, loading, error, fetchArticles } = useArticles();
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  useEffect(() => {
    fetchArticles('all');
  }, [fetchArticles]);

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [articles.length]);

  const visibleArticles = useMemo(
    () => articles.slice(0, visibleCount),
    [articles, visibleCount],
  );

  const canLoadMore = visibleCount < articles.length;

  return (
    <main
      className="h-dvh overflow-y-auto"
      style={{
        background:
          'radial-gradient(circle at top left, rgba(14, 165, 233, 0.14), transparent 30%), radial-gradient(circle at top right, rgba(249, 115, 22, 0.14), transparent 24%), var(--bg-primary)',
      }}
    >
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div
          className="mb-6 rounded-[28px] border p-5 sm:p-6"
          style={{
            borderColor: 'var(--border-primary)',
            background: 'var(--glass-bg)',
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p
                className="mb-2 text-xs font-semibold uppercase tracking-[0.22em]"
                style={{ color: 'var(--text-quaternary)' }}
              >
                Article Directory
              </p>
              <h1
                className="font-display text-3xl font-extrabold tracking-[-0.04em] sm:text-4xl"
                style={{ color: 'var(--text-primary)' }}
              >
                Every story in one table
              </h1>
              <p
                className="mt-3 max-w-2xl text-sm sm:text-base"
                style={{ color: 'var(--text-secondary)' }}
              >
                Browse the full feed in batches of 25, then load more when you want the next set.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Link
                to="/"
                className="rounded-full px-4 py-2 text-sm font-semibold transition"
                style={{
                  background: 'var(--action-bg)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-primary)',
                }}
              >
                Back to feed
              </Link>
              <button
                type="button"
                onClick={() => fetchArticles('all')}
                className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition"
                style={{
                  background: 'var(--bg-elevated)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border-primary)',
                }}
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3 text-sm">
            <span
              className="rounded-full px-3 py-1 font-medium"
              style={{ background: 'var(--action-bg)', color: 'var(--text-secondary)' }}
            >
              {loading ? 'Loading articles...' : `${articles.length} total articles`}
            </span>
            <span
              className="rounded-full px-3 py-1 font-medium"
              style={{ background: 'var(--action-bg)', color: 'var(--text-secondary)' }}
            >
              Showing {Math.min(visibleCount, articles.length)} at a time
            </span>
          </div>
        </div>

        <div
          className="overflow-hidden rounded-[28px] border"
          style={{
            borderColor: 'var(--border-primary)',
            background: 'var(--card-bg-active)',
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <thead>
                <tr style={{ background: 'var(--bg-secondary)' }}>
                  {['#', 'Date', 'Genre', 'Title', 'Source', 'Summary', 'Link'].map((heading) => (
                    <th
                      key={heading}
                      className="px-4 py-3 text-left text-xs font-bold uppercase tracking-[0.18em]"
                      style={{
                        color: 'var(--text-quaternary)',
                        borderBottom: '1px solid var(--border-primary)',
                      }}
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleArticles.map((article, index) => (
                  <tr
                    key={article.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      background: index % 2 === 0 ? 'transparent' : 'var(--bg-overlay)',
                    }}
                  >
                    <td className="px-4 py-4 align-top text-sm" style={{ color: 'var(--text-tertiary)' }}>
                      {index + 1}
                    </td>
                    <td className="px-4 py-4 align-top text-sm whitespace-nowrap" style={{ color: 'var(--text-secondary)' }}>
                      {formatDate(article.publishedAt)}
                    </td>
                    <td className="px-4 py-4 align-top">
                      <span
                        className="inline-flex rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-[0.14em]"
                        style={{
                          background: 'var(--action-bg)',
                          color: 'var(--text-primary)',
                        }}
                      >
                        {article.primaryGenre}
                      </span>
                    </td>
                    <td className="px-4 py-4 align-top text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {article.title}
                    </td>
                    <td className="px-4 py-4 align-top text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {article.source}
                    </td>
                    <td className="px-4 py-4 align-top text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                      <div className="max-w-xl">
                        {article.summary || 'No summary available.'}
                      </div>
                    </td>
                    <td className="px-4 py-4 align-top">
                      <a
                        href={article.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 text-sm font-semibold transition hover:underline"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        Open
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </td>
                  </tr>
                ))}

                {!loading && visibleArticles.length === 0 && (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-10 text-center text-sm"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      No articles found.
                    </td>
                  </tr>
                )}

                {loading && (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-10 text-center text-sm"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      Loading articles...
                    </td>
                  </tr>
                )}

                {error && !loading && (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-10 text-center text-sm"
                      style={{ color: '#ef4444' }}
                    >
                      {error}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {canLoadMore && !loading && (
          <div className="flex justify-center py-6">
            <button
              type="button"
              onClick={() => setVisibleCount((current) => current + PAGE_SIZE)}
              className="rounded-full px-6 py-3 text-sm font-semibold transition"
              style={{
                background: 'var(--text-primary)',
                color: 'var(--bg-primary)',
                boxShadow: 'var(--shadow-card)',
              }}
            >
              Load 25 more
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
