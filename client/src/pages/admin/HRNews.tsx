import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import type { HRNewsArticle, HRNewsFullContent } from '../../api/client';
import { RefreshCw, ExternalLink, ChevronDown, ChevronUp, Newspaper, AlertCircle, Clock } from 'lucide-react';

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

  // Expanded article content
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [fullContent, setFullContent] = useState<Record<string, HRNewsFullContent>>({});
  const [loadingContent, setLoadingContent] = useState<string | null>(null);

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

  const handleToggleContent = async (articleId: string) => {
    if (expandedId === articleId) {
      setExpandedId(null);
      return;
    }

    setExpandedId(articleId);

    // Already loaded
    if (fullContent[articleId]) return;

    try {
      setLoadingContent(articleId);
      const data = await api.adminNews.getFullContent(articleId);
      setFullContent(prev => ({ ...prev, [articleId]: data }));
    } catch (err) {
      console.error('Failed to fetch full content:', err);
      setFullContent(prev => ({
        ...prev,
        [articleId]: { id: articleId, title: '', content: null, error: 'Failed to fetch content' },
      }));
    } finally {
      setLoadingContent(null);
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
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800 border border-zinc-700/50 flex items-center justify-center">
            <Newspaper size={16} className="text-zinc-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-zinc-100">HR News</h1>
            <p className="text-xs text-zinc-500">Latest HR industry news from top sources</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {refreshMessage && (
            <span className="text-xs text-zinc-400 bg-zinc-800/50 px-3 py-1.5 rounded-lg border border-zinc-700/30">
              {refreshMessage}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg border border-zinc-700/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh Feeds'}
          </button>
        </div>
      </div>

      {/* Source Filter Tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-1">
        <button
          onClick={() => { setSourceFilter(null); setOffset(0); }}
          className={`px-3 py-1.5 text-xs rounded-lg border transition-colors whitespace-nowrap ${
            !sourceFilter
              ? 'bg-zinc-700 text-zinc-100 border-zinc-600'
              : 'bg-zinc-800/50 text-zinc-400 border-zinc-700/30 hover:bg-zinc-800 hover:text-zinc-300'
          }`}
        >
          All Sources
        </button>
        {sources.map(s => (
          <button
            key={s}
            onClick={() => { setSourceFilter(s); setOffset(0); }}
            className={`px-3 py-1.5 text-xs rounded-lg border transition-colors whitespace-nowrap ${
              sourceFilter === s
                ? 'bg-zinc-700 text-zinc-100 border-zinc-600'
                : 'bg-zinc-800/50 text-zinc-400 border-zinc-700/30 hover:bg-zinc-800 hover:text-zinc-300'
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
                      {article.title}
                    </h3>

                    {/* Description */}
                    {article.description && (
                      <p className="text-xs text-zinc-400 line-clamp-2 leading-relaxed">
                        {article.description}
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => handleToggleContent(article.id)}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-300 rounded-lg border border-zinc-700/50 transition-colors"
                    >
                      {expandedId === article.id ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      {expandedId === article.id ? 'Close' : 'Read'}
                    </button>
                    {article.link && (
                      <a
                        href={article.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-300 rounded-lg border border-zinc-700/50 transition-colors"
                      >
                        <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                </div>
              </div>

              {/* Expanded Content */}
              {expandedId === article.id && (
                <div className="border-t border-zinc-800 px-4 py-4">
                  {loadingContent === article.id && (
                    <div className="flex items-center gap-2 text-xs text-zinc-500">
                      <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-pulse" />
                      Fetching full article...
                    </div>
                  )}
                  {fullContent[article.id]?.error && (
                    <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-500/5 border border-amber-500/20 rounded-lg px-3 py-2">
                      <AlertCircle size={12} />
                      {fullContent[article.id].error}
                      {article.link && (
                        <a
                          href={article.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-auto text-amber-300 hover:text-amber-200 underline"
                        >
                          Open original
                        </a>
                      )}
                    </div>
                  )}
                  {fullContent[article.id]?.content && (
                    <div className="prose prose-sm prose-invert prose-zinc max-w-none text-xs leading-relaxed [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_p]:text-xs [&_li]:text-xs [&_a]:text-blue-400 [&_a:hover]:text-blue-300 [&_img]:rounded-lg [&_img]:max-h-64">
                      <div
                        dangerouslySetInnerHTML={{
                          __html: fullContent[article.id].content!
                            .replace(/\n/g, '<br/>')
                            .replace(/^# (.*?)(<br\/>)/gm, '<h1>$1</h1>')
                            .replace(/^## (.*?)(<br\/>)/gm, '<h2>$1</h2>')
                            .replace(/^### (.*?)(<br\/>)/gm, '<h3>$1</h3>')
                        }}
                      />
                    </div>
                  )}
                </div>
              )}
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
