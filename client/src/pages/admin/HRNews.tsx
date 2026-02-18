import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import type { HRNewsArticle } from '../../api/client';
import { RefreshCw, ExternalLink, Newspaper, AlertCircle, Clock } from 'lucide-react';

const ITEMS_PER_PAGE = 20;

export default function HRNews() {
  const [articles, setArticles] = useState<HRNewsArticle[]>([]);
  const [total, setTotal] = useState(0);
  const [sources, setSources] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  // Filters
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);

  const fetchArticles = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.adminNews.list({
        source: sourceFilter || undefined,
        limit: ITEMS_PER_PAGE,
        offset,
      });
      setArticles(data.articles);
      setTotal(data.total);
      setSources(data.sources);
    } catch (err) {
      console.error('Failed to fetch articles:', err);
      setError('Failed to load articles');
    } finally {
      setLoading(false);
    }
  }, [sourceFilter, offset]);

  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      setRefreshMessage(null);
      const result = await api.adminNews.refresh();
      if (result.status === 'cached') {
        setRefreshMessage(result.message || 'Feed was recently refreshed.');
      } else {
        setRefreshMessage(`Fetched ${result.new_articles} new article${result.new_articles !== 1 ? 's' : ''}`);
        // Reload articles
        setOffset(0);
        await fetchArticles();
      }
    } catch (err) {
      console.error('Failed to refresh feeds:', err);
      setRefreshMessage('Failed to refresh feeds');
    } finally {
      setRefreshing(false);
      // Clear message after 5 seconds
      setTimeout(() => setRefreshMessage(null), 5000);
    }
  };

  const totalPages = Math.ceil(total / ITEMS_PER_PAGE);
  const currentPage = Math.floor(offset / ITEMS_PER_PAGE) + 1;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-zinc-800 border border-zinc-700/50 flex items-center justify-center shrink-0">
            <Newspaper size={20} className="text-zinc-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">HR News</h1>
            <p className="text-[10px] text-zinc-500 font-mono uppercase tracking-wide">Latest industry insights</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {refreshMessage && (
            <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/5 px-3 py-1.5 border border-emerald-500/10">
              {refreshMessage}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-widest bg-zinc-800 hover:bg-zinc-700 text-zinc-100 border border-zinc-700/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh Feeds'}
          </button>
        </div>
      </div>

      {/* Source Filter Tabs */}
      <div className="flex gap-1 mb-6 overflow-x-auto no-scrollbar pb-1 -mx-4 px-4 sm:mx-0 sm:px-0">
        <button
          onClick={() => { setSourceFilter(null); setOffset(0); }}
          className={`px-4 py-2 text-[10px] uppercase tracking-widest font-bold border transition-colors whitespace-nowrap ${
            !sourceFilter
              ? 'bg-white text-black border-white'
              : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-600 hover:text-zinc-300'
          }`}
        >
          All Sources
        </button>
        {sources.map(s => (
          <button
            key={s}
            onClick={() => { setSourceFilter(s); setOffset(0); }}
            className={`px-4 py-2 text-[10px] uppercase tracking-widest font-bold border transition-colors whitespace-nowrap ${
              sourceFilter === s
                ? 'bg-white text-black border-white'
                : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-600 hover:text-zinc-300'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-2 text-red-400 bg-red-500/5 border border-red-500/20 rounded-lg px-4 py-3 mb-4 text-sm">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-zinc-500 animate-pulse" />
            <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && articles.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-12 h-12 rounded-xl bg-zinc-800 border border-zinc-700/50 flex items-center justify-center mb-4">
            <Newspaper size={20} className="text-zinc-500" />
          </div>
          <h3 className="text-sm font-medium text-zinc-300 mb-1">No articles yet</h3>
          <p className="text-xs text-zinc-500 mb-4">Click "Refresh Feeds" to fetch the latest HR news</p>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg border border-zinc-700/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            Refresh Feeds
          </button>
        </div>
      )}

      {/* Article Cards */}
      {!loading && articles.length > 0 && (
        <div className="space-y-3">
          {articles.map(article => (
            <div
              key={article.id}
              className="bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden"
            >
              <div className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {/* Source + Date */}
                    <div className="flex items-center gap-2 mb-1.5">
                      {article.source_name && (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700/50">
                          {article.source_name}
                        </span>
                      )}
                      {article.pub_date && (
                        <span className="flex items-center gap-1 text-[10px] text-zinc-500">
                          <Clock size={10} />
                          {formatDate(article.pub_date)}
                        </span>
                      )}
                      {article.author && (
                        <span className="text-[10px] text-zinc-500">
                          by {article.author}
                        </span>
                      )}
                    </div>

                    {/* Title */}
                    <h3 className="text-sm font-medium text-zinc-200 mb-1 leading-snug">
                      {article.link ? (
                        <a
                          href={article.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-zinc-100 transition-colors"
                        >
                          {article.title}
                        </a>
                      ) : (
                        article.title
                      )}
                    </h3>

                    {/* Description */}
                    {article.description && (
                      <p className="text-xs text-zinc-400 leading-relaxed">
                        {article.description}
                      </p>
                    )}
                  </div>

                  {/* External Link */}
                  {article.link && (
                    <a
                      href={article.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-300 rounded-lg border border-zinc-700/50 transition-colors flex-shrink-0"
                    >
                      <ExternalLink size={12} />
                      Read
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-zinc-800">
          <span className="text-xs text-zinc-500">
            {offset + 1}-{Math.min(offset + ITEMS_PER_PAGE, total)} of {total}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setOffset(Math.max(0, offset - ITEMS_PER_PAGE))}
              disabled={offset === 0}
              className="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded-lg border border-zinc-700/50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="px-3 py-1.5 text-xs text-zinc-500">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setOffset(offset + ITEMS_PER_PAGE)}
              disabled={offset + ITEMS_PER_PAGE >= total}
              className="px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 rounded-lg border border-zinc-700/50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
