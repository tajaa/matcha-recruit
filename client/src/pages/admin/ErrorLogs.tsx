import { useState, useEffect, useCallback } from 'react';
import { errorLogs } from '../../api/client';
import type { ErrorLogItem } from '../../api/client';
import { useIsLightMode } from '../../hooks/useIsLightMode';
import { AlertTriangle, Trash2, ChevronDown, ChevronRight, Search, X } from 'lucide-react';

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-xl',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  rowHover: 'hover:bg-stone-50',
  skeleton: 'bg-stone-200',
  skeletonFaint: 'bg-stone-200/50',
  emptyBg: 'bg-stone-100 rounded-xl',
  emptyIcon: 'text-stone-300',
  emptyText: 'text-stone-400',
  errorBg: 'bg-red-50 border-red-200 text-red-700',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnDanger: 'bg-red-600 text-white hover:bg-red-700',
  methodBadge: 'bg-stone-200 text-stone-600 border-stone-300',
  traceback: 'bg-stone-200 text-stone-800 border-stone-300',
  searchBg: 'bg-stone-50 border-stone-300 text-zinc-900 placeholder:text-stone-400',
  countBadge: 'bg-red-100 text-red-700',
  inputBg: 'bg-white border-stone-300',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-xl',
  border: 'border-white/10',
  divide: 'divide-white/5',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  rowHover: 'hover:bg-white/5',
  skeleton: 'bg-zinc-800',
  skeletonFaint: 'bg-zinc-800/50',
  emptyBg: 'bg-zinc-900/50 border border-white/10 rounded-xl',
  emptyIcon: 'text-zinc-700',
  emptyText: 'text-zinc-500',
  errorBg: 'bg-red-500/10 border-red-500/20 text-red-400',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600',
  btnDanger: 'bg-red-600/80 text-white hover:bg-red-600',
  methodBadge: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  traceback: 'bg-black/40 text-zinc-300 border-zinc-800',
  searchBg: 'bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-600',
  countBadge: 'bg-red-500/20 text-red-400',
  inputBg: 'bg-zinc-900 border-zinc-700',
} as const;

const METHOD_COLORS: Record<string, string> = {
  GET: 'text-emerald-400',
  POST: 'text-sky-400',
  PUT: 'text-amber-400',
  PATCH: 'text-amber-400',
  DELETE: 'text-red-400',
};

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  const diffMonth = Math.floor(diffDay / 30);
  return `${diffMonth}mo ago`;
}

const PAGE_SIZE = 50;

export function ErrorLogs() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const [items, setItems] = useState<ErrorLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchPath, setSearchPath] = useState('');
  const [activeSearch, setActiveSearch] = useState('');
  const [clearing, setClearing] = useState(false);

  const fetchLogs = useCallback(async (offset = 0, append = false) => {
    try {
      if (append) setLoadingMore(true);
      else setLoading(true);
      const data = await errorLogs.get(PAGE_SIZE, offset, activeSearch || undefined);
      if (append) {
        setItems(prev => [...prev, ...data.items]);
      } else {
        setItems(data.items);
      }
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to fetch error logs:', err);
      setError('Failed to load error logs');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [activeSearch]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleSearch = () => {
    setActiveSearch(searchPath);
  };

  const handleClearSearch = () => {
    setSearchPath('');
    setActiveSearch('');
  };

  const handleClearLogs = async () => {
    if (!confirm('Delete all error logs?')) return;
    setClearing(true);
    try {
      await errorLogs.clear();
      setItems([]);
      setTotal(0);
    } catch {
      setError('Failed to clear logs');
    } finally {
      setClearing(false);
    }
  };

  const hasMore = items.length < total;

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-6 py-8 px-4 sm:px-6">
        <div className={`border-b ${t.border} pb-6`}>
          <div className={`h-8 w-48 ${t.skeleton} animate-pulse rounded-md`} />
          <div className={`h-4 w-64 ${t.skeletonFaint} animate-pulse mt-3 rounded-md`} />
        </div>
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className={`border ${t.border} ${t.card} p-4 flex items-start gap-3`}>
              <div className={`w-6 h-6 ${t.skeleton} animate-pulse shrink-0 rounded`} />
              <div className="flex-1 space-y-2">
                <div className={`h-4 w-2/3 ${t.skeleton} animate-pulse rounded`} />
                <div className={`h-3 w-1/3 ${t.skeletonFaint} animate-pulse rounded`} />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6 py-8 px-4 sm:px-6">
      {/* Header */}
      <div className={`border-b ${t.border} pb-6 flex items-end justify-between`}>
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-2xl font-bold tracking-tight ${t.textMain}`}>Error Logs</h1>
            {total > 0 && (
              <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${t.countBadge}`}>
                {total}
              </span>
            )}
          </div>
          <p className={`text-xs ${t.textMuted} mt-1.5`}>
            Application errors captured from the backend
          </p>
        </div>
        {items.length > 0 && (
          <button
            onClick={handleClearLogs}
            disabled={clearing}
            className={`text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5 ${t.btnDanger} transition-colors`}
          >
            <Trash2 size={12} />
            {clearing ? 'Clearing...' : 'Clear All'}
          </button>
        )}
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search size={14} className={`absolute left-3 top-1/2 -translate-y-1/2 ${t.textFaint}`} />
          <input
            type="text"
            value={searchPath}
            onChange={(e) => setSearchPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Filter by path..."
            className={`w-full pl-9 pr-8 py-2 text-sm rounded-lg border ${t.searchBg} focus:outline-none focus:ring-1 focus:ring-zinc-500`}
          />
          {searchPath && (
            <button onClick={handleClearSearch} className={`absolute right-3 top-1/2 -translate-y-1/2 ${t.textFaint}`}>
              <X size={14} />
            </button>
          )}
        </div>
        <button
          onClick={handleSearch}
          className={`text-xs px-4 py-2 rounded-lg ${t.btnPrimary} transition-colors`}
        >
          Search
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className={`p-4 border text-sm rounded-lg ${t.errorBg}`}>{error}</div>
      )}

      {/* Empty */}
      {items.length === 0 && !error ? (
        <div className={`${t.emptyBg} text-center py-20`}>
          <div className={`w-12 h-12 rounded-full ${t.skeletonFaint} flex items-center justify-center mx-auto mb-4`}>
            <AlertTriangle size={20} className={t.emptyIcon} />
          </div>
          <p className={`text-sm ${t.emptyText}`}>
            {activeSearch ? 'No errors matching this filter' : 'No errors logged'}
          </p>
        </div>
      ) : (
        <div className={`${t.card} border ${t.border} overflow-hidden`}>
          <div className={`divide-y ${t.divide}`}>
            {items.map((item) => {
              const expanded = expandedId === item.id;
              return (
                <div key={item.id}>
                  <button
                    onClick={() => setExpandedId(expanded ? null : item.id)}
                    className={`w-full text-left px-4 py-3 flex items-start gap-3 ${t.rowHover} transition-colors`}
                  >
                    <div className="shrink-0 mt-0.5">
                      {expanded ? (
                        <ChevronDown size={14} className={t.textFaint} />
                      ) : (
                        <ChevronRight size={14} className={t.textFaint} />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`text-xs font-mono font-semibold ${METHOD_COLORS[item.method] || t.textMuted}`}>
                          {item.method}
                        </span>
                        <span className={`text-sm font-mono truncate ${t.textMain}`}>
                          {item.path}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${t.methodBadge}`}>
                          {item.error_type}
                        </span>
                        <span className={`text-xs ${t.textMuted} truncate`}>
                          {item.error_message.length > 120
                            ? item.error_message.slice(0, 120) + '...'
                            : item.error_message}
                        </span>
                      </div>
                    </div>
                    <span className={`text-xs ${t.textFaint} shrink-0 font-mono`}>
                      {relativeTime(item.timestamp)}
                    </span>
                  </button>

                  {/* Expanded detail */}
                  {expanded && (
                    <div className={`px-4 pb-4 pl-11 space-y-3`}>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <div>
                          <span className={t.textFaint}>Status</span>
                          <p className={`font-mono ${t.textMain}`}>{item.status_code}</p>
                        </div>
                        <div>
                          <span className={t.textFaint}>Time</span>
                          <p className={`font-mono ${t.textMain}`}>
                            {new Date(item.timestamp).toLocaleString()}
                          </p>
                        </div>
                        {item.user_role && (
                          <div>
                            <span className={t.textFaint}>User Role</span>
                            <p className={`font-mono ${t.textMain}`}>{item.user_role}</p>
                          </div>
                        )}
                        {item.query_params && (
                          <div>
                            <span className={t.textFaint}>Query</span>
                            <p className={`font-mono ${t.textMain} truncate`}>{item.query_params}</p>
                          </div>
                        )}
                      </div>

                      <div>
                        <span className={`text-xs ${t.textFaint}`}>Error Message</span>
                        <p className={`text-sm font-mono ${t.textMain} mt-1 break-all`}>
                          {item.error_message}
                        </p>
                      </div>

                      {item.traceback && (
                        <div>
                          <span className={`text-xs ${t.textFaint}`}>Traceback</span>
                          <pre className={`mt-1 p-3 rounded-lg border text-xs font-mono overflow-x-auto max-h-80 ${t.traceback}`}>
                            {item.traceback}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Load more */}
      {hasMore && (
        <div className="text-center pt-2">
          <button
            onClick={() => fetchLogs(items.length, true)}
            disabled={loadingMore}
            className={`text-xs px-6 py-2 rounded-lg ${t.btnPrimary} transition-colors`}
          >
            {loadingMore ? 'Loading...' : `Load More (${items.length} of ${total})`}
          </button>
        </div>
      )}
    </div>
  );
}

export default ErrorLogs;
