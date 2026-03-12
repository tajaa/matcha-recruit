import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { clientNotifications } from '../api/client';
import type { ClientNotificationItem } from '../api/client';
import { useIsLightMode } from '../hooks/useIsLightMode';
import {
  AlertTriangle,
  UserPlus,
  FileText,
  Scale,
  BookOpen,
  AlertCircle,
  Bell,
} from 'lucide-react';

const TYPE_ICONS: Record<ClientNotificationItem['type'], React.ReactNode> = {
  incident: <AlertTriangle size={15} className="text-red-400" />,
  employee: <UserPlus size={15} className="text-emerald-400" />,
  offer_letter: <FileText size={15} className="text-sky-400" />,
  er_case: <Scale size={15} className="text-violet-400" />,
  handbook: <BookOpen size={15} className="text-amber-400" />,
  compliance_alert: <AlertCircle size={15} className="text-orange-400" />,
};

const TYPE_BG_DARK: Record<ClientNotificationItem['type'], string> = {
  incident: 'bg-red-900/30 border-red-500/20',
  employee: 'bg-emerald-900/30 border-emerald-500/20',
  offer_letter: 'bg-sky-900/30 border-sky-500/20',
  er_case: 'bg-violet-900/30 border-violet-500/20',
  handbook: 'bg-amber-900/30 border-amber-500/20',
  compliance_alert: 'bg-orange-900/30 border-orange-500/20',
};

const TYPE_BG_LIGHT: Record<ClientNotificationItem['type'], string> = {
  incident: 'bg-red-50 border-red-200',
  employee: 'bg-emerald-50 border-emerald-200',
  offer_letter: 'bg-sky-50 border-sky-200',
  er_case: 'bg-violet-50 border-violet-200',
  handbook: 'bg-amber-50 border-amber-200',
  compliance_alert: 'bg-orange-50 border-orange-200',
};

const SEVERITY_DARK: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
  high: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  low: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
};

const SEVERITY_LIGHT: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-amber-100 text-amber-700 border-amber-200',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  low: 'bg-sky-100 text-sky-700 border-sky-200',
};

const STATUS_DARK: Record<string, string> = {
  investigating: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  pending: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  draft: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  onboarded: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  approved: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  resolved: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  closed: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  rejected: 'bg-red-500/10 text-red-400 border-red-500/20',
  sent: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  open: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
};

const STATUS_LIGHT: Record<string, string> = {
  investigating: 'bg-amber-100 text-amber-700 border-amber-200',
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
  draft: 'bg-stone-100 text-stone-600 border-stone-200',
  onboarded: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  approved: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  active: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  resolved: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  closed: 'bg-stone-100 text-stone-600 border-stone-200',
  rejected: 'bg-red-100 text-red-700 border-red-200',
  sent: 'bg-sky-100 text-sky-700 border-sky-200',
  open: 'bg-sky-100 text-sky-700 border-sky-200',
};

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
  subtitleMono: 'text-stone-400',
  badgeBg: 'bg-stone-200 border-stone-300 text-stone-500',
  typeBg: TYPE_BG_LIGHT,
  severity: SEVERITY_LIGHT,
  status: STATUS_LIGHT,
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
  subtitleMono: 'text-zinc-500',
  badgeBg: 'bg-zinc-500/10 border-zinc-500/20 text-zinc-400',
  typeBg: TYPE_BG_DARK,
  severity: SEVERITY_DARK,
  status: STATUS_DARK,
} as const;

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

const PAGE_SIZE = 30;

export function ClientNotifications() {
  const navigate = useNavigate();
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const [items, setItems] = useState<ClientNotificationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchNotifications = useCallback(async (offset = 0, append = false) => {
    try {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      const data = await clientNotifications.get(PAGE_SIZE, offset);
      if (append) {
        setItems(prev => [...prev, ...data.items]);
      } else {
        setItems(data.items);
      }
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to fetch notifications:', err);
      setError('Failed to load notifications');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const handleLoadMore = () => {
    fetchNotifications(items.length, true);
  };

  const hasMore = items.length < total;

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6 py-8 px-4 sm:px-6">
        <div className={`border-b ${t.border} pb-6`}>
          <div className={`h-8 w-64 ${t.skeleton} animate-pulse rounded-md`} />
          <div className={`h-4 w-48 ${t.skeletonFaint} animate-pulse mt-3 rounded-md`} />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className={`border ${t.border} ${t.card} p-5 flex items-start gap-4`}>
              <div className={`w-8 h-8 ${t.skeleton} animate-pulse shrink-0 rounded-md`} />
              <div className="flex-1 space-y-2.5 mt-0.5">
                <div className={`h-4 w-3/4 ${t.skeleton} animate-pulse rounded-md`} />
                <div className={`h-3 w-1/3 ${t.skeletonFaint} animate-pulse rounded-md`} />
              </div>
              <div className={`h-3 w-16 ${t.skeletonFaint} animate-pulse rounded-md mt-1`} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 py-8 px-4 sm:px-6">
      {/* Header */}
      <div className={`border-b ${t.border} pb-6 flex items-end justify-between`}>
        <div>
          <h1 className={`text-2xl font-bold tracking-tight ${t.textMain}`}>Notifications</h1>
          <p className={`text-xs ${t.textMuted} mt-1.5`}>
            Recent activity
          </p>
        </div>
        <div className={`text-xs ${t.textMuted} font-mono`}>
          {total} total
        </div>
      </div>

        {/* Error */}
        {error && (
          <div className={`p-4 border text-sm rounded-lg ${t.errorBg}`}>
            {error}
          </div>
        )}

        {/* Feed */}
        {items.length === 0 && !error ? (
          <div className={`${t.emptyBg} text-center py-20`}>
            <div className={`w-12 h-12 rounded-full ${t.skeletonFaint} flex items-center justify-center mx-auto mb-4`}>
              <Bell size={20} className={t.emptyIcon} />
            </div>
            <div className={`text-sm font-medium ${t.textMain} mb-1`}>No notifications</div>
            <div className={`text-xs ${t.textMuted}`}>You're all caught up.</div>
          </div>
        ) : (
          <div className={`${t.card} overflow-hidden shadow-sm`}>
            <div className={`divide-y ${t.divide}`}>
              {items.map((item) => (
                <div
                  key={item.id}
                  onClick={() => item.link && navigate(item.link)}
                  className={`p-4 md:p-5 ${t.rowHover} transition-colors cursor-pointer group flex items-start gap-4`}
                >
                  {/* Type Icon */}
                  <div className={`w-9 h-9 border flex items-center justify-center shrink-0 rounded-lg ${t.typeBg[item.type]}`}>
                    {TYPE_ICONS[item.type]}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0 pt-0.5">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className={`text-sm ${t.textMain} font-medium group-hover:text-emerald-500 transition-colors truncate`}>
                          {item.title}
                        </div>
                        {item.subtitle && (
                          <div className={`text-xs ${t.textMuted} mt-1 truncate`}>{item.subtitle}</div>
                        )}
                      </div>
                      <div className={`text-[11px] ${t.textFaint} font-medium shrink-0`}>
                        {relativeTime(item.created_at)}
                      </div>
                    </div>

                    {(item.severity || item.status) && (
                      <div className="flex items-center gap-2 mt-2.5">
                        {/* Severity badge */}
                        {item.severity && (
                          <span className={`inline-flex items-center px-2 py-0.5 border text-[10px] font-semibold rounded-md ${t.severity[item.severity] || t.badgeBg}`}>
                            {item.severity.charAt(0).toUpperCase() + item.severity.slice(1)}
                          </span>
                        )}

                        {/* Status badge */}
                        {item.status && (
                          <span className={`inline-flex items-center px-2 py-0.5 border text-[10px] font-semibold rounded-md ${t.status[item.status] || t.badgeBg}`}>
                            {item.status.charAt(0).toUpperCase() + item.status.slice(1).replace('_', ' ')}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Load More */}
        {hasMore && (
          <div className="flex justify-center pt-4">
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className={`px-6 py-2 border text-xs font-semibold rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${t.btnPrimary}`}
            >
              {loadingMore ? 'Loading...' : 'Load More'}
            </button>
          </div>
        )}
    </div>
  );
}

export default ClientNotifications;
