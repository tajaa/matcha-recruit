import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminNotifications } from '../../api/client';
import type { AdminNotificationItem } from '../../api/client';
import { useIsLightMode } from '../../hooks/useIsLightMode';
import {
  AlertTriangle,
  UserPlus,
  FileText,
  Scale,
  BookOpen,
  AlertCircle,
  Building2,
  Bell,
} from 'lucide-react';

const TYPE_ICONS: Record<AdminNotificationItem['type'], React.ReactNode> = {
  incident: <AlertTriangle size={15} className="text-red-400" />,
  employee: <UserPlus size={15} className="text-emerald-400" />,
  offer_letter: <FileText size={15} className="text-sky-400" />,
  er_case: <Scale size={15} className="text-violet-400" />,
  handbook: <BookOpen size={15} className="text-amber-400" />,
  compliance_alert: <AlertCircle size={15} className="text-orange-400" />,
  registration: <Building2 size={15} className="text-zinc-400" />,
};

const TYPE_BG_DARK: Record<AdminNotificationItem['type'], string> = {
  incident: 'bg-red-900/30 border-red-500/20',
  employee: 'bg-emerald-900/30 border-emerald-500/20',
  offer_letter: 'bg-sky-900/30 border-sky-500/20',
  er_case: 'bg-violet-900/30 border-violet-500/20',
  handbook: 'bg-amber-900/30 border-amber-500/20',
  compliance_alert: 'bg-orange-900/30 border-orange-500/20',
  registration: 'bg-zinc-800 border-zinc-700',
};

const TYPE_BG_LIGHT: Record<AdminNotificationItem['type'], string> = {
  incident: 'bg-red-50 border-red-200',
  employee: 'bg-emerald-50 border-emerald-200',
  offer_letter: 'bg-sky-50 border-sky-200',
  er_case: 'bg-violet-50 border-violet-200',
  handbook: 'bg-amber-50 border-amber-200',
  compliance_alert: 'bg-orange-50 border-orange-200',
  registration: 'bg-stone-100 border-stone-300',
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
  textMuted: 'text-stone-50',
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
  companyBadge: 'bg-stone-200 border-stone-300 text-stone-500',
  companyIcon: 'text-stone-400',
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
  companyBadge: 'bg-zinc-800 border-zinc-700 text-zinc-400',
  companyIcon: 'text-zinc-500',
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

export function AdminNotifications() {
  const navigate = useNavigate();
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const [items, setItems] = useState<AdminNotificationItem[]>([]);
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
      const data = await adminNotifications.get(PAGE_SIZE, offset);
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
      <div className="max-w-5xl mx-auto space-y-8 py-4">
        <div className={`border-b ${t.border} pb-6 md:pb-8`}>
          <div className={`h-8 w-64 ${t.skeleton} animate-pulse rounded`} />
          <div className={`h-4 w-96 ${t.skeletonFaint} animate-pulse mt-3 rounded`} />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className={`border ${t.border} ${t.card} p-4 flex items-center gap-4`}>
              <div className={`w-8 h-8 ${t.skeleton} animate-pulse shrink-0 rounded`} />
              <div className="flex-1 space-y-2">
                <div className={`h-4 w-48 ${t.skeleton} animate-pulse rounded`} />
                <div className={`h-3 w-32 ${t.skeletonFaint} animate-pulse rounded`} />
              </div>
              <div className={`h-3 w-16 ${t.skeletonFaint} animate-pulse rounded`} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8 py-4">
      {/* Header */}
      <div className={`border-b ${t.border} pb-6 md:pb-8`}>
        <h1 className={`text-3xl font-bold tracking-tight ${t.textMain}`}>Notifications</h1>
        <p className={`text-[11px] ${t.textMuted} mt-1.5`}>
          Recent activity across all companies &mdash; {total} total
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className={`p-4 border text-sm rounded-lg ${t.errorBg}`}>
          {error}
        </div>
      )}

      {/* Feed */}
      {items.length === 0 && !error ? (
        <div className={`${t.emptyBg} text-center py-24`}>
          <Bell size={24} className={`${t.emptyIcon} mx-auto mb-3`} />
          <div className={`${t.emptyText} font-mono text-sm uppercase tracking-wider`}>
            No notifications yet
          </div>
        </div>
      ) : (
        <div className={`${t.card} divide-y ${t.divide} overflow-hidden shadow-sm`}>
          {items.map((item) => (
            <div
              key={item.id}
              onClick={() => item.link && navigate(item.link)}
              className={`p-4 md:px-5 md:py-4 ${t.rowHover} transition-colors cursor-pointer active:opacity-80 flex items-start gap-3 md:gap-4`}
            >
              {/* Type Icon */}
              <div className={`w-8 h-8 border flex items-center justify-center shrink-0 mt-0.5 rounded-lg ${t.typeBg[item.type]}`}>
                {TYPE_ICONS[item.type]}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className={`text-sm ${t.textMain} font-semibold truncate`}>{item.title}</div>
                    {item.subtitle && (
                      <div className={`text-[11px] ${t.subtitleMono} font-mono mt-0.5 truncate opacity-70`}>{item.subtitle}</div>
                    )}
                  </div>
                  <div className={`text-[10px] ${t.textFaint} font-mono whitespace-nowrap shrink-0 mt-0.5`}>
                    {relativeTime(item.created_at)}
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  {/* Company badge */}
                  {item.company_name && (
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 border text-[10px] font-semibold rounded-md ${t.companyBadge}`}>
                      <Building2 size={10} className={t.companyIcon} />
                      {item.company_name}
                    </span>
                  )}

                  {/* Severity badge */}
                  {item.severity && (
                    <span className={`inline-flex items-center px-2 py-0.5 border text-[10px] font-semibold rounded-md ${t.severity[item.severity] || t.badgeBg}`}>
                      {item.severity}
                    </span>
                  )}

                  {/* Status badge */}
                  {item.status && (
                    <span className={`inline-flex items-center px-2 py-0.5 border text-[10px] font-semibold rounded-md ${t.status[item.status] || t.badgeBg}`}>
                      {item.status}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Load More */}
      {hasMore && (
        <div className="flex justify-center pt-2">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className={`px-6 py-2 border text-[10px] font-bold rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors ${t.btnPrimary}`}
          >
            {loadingMore ? 'Loading...' : `Load More (${items.length} of ${total})`}
          </button>
        </div>
      )}
    </div>
  );
}

export default AdminNotifications;
