import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminNotifications } from '../../api/client';
import type { AdminNotificationItem } from '../../api/client';
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
  registration: <Building2 size={15} className="text-zinc-300" />,
};

const TYPE_BG: Record<AdminNotificationItem['type'], string> = {
  incident: 'bg-red-900/30 border-red-500/20',
  employee: 'bg-emerald-900/30 border-emerald-500/20',
  offer_letter: 'bg-sky-900/30 border-sky-500/20',
  er_case: 'bg-violet-900/30 border-violet-500/20',
  handbook: 'bg-amber-900/30 border-amber-500/20',
  compliance_alert: 'bg-orange-900/30 border-orange-500/20',
  registration: 'bg-zinc-800 border-zinc-700',
};

const SEVERITY_CLASSES: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
  high: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  medium: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
  low: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
};

const STATUS_CLASSES: Record<string, string> = {
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
      <div className="max-w-7xl mx-auto space-y-8">
        <div className="border-b border-white/10 pb-6 md:pb-8">
          <div className="h-8 w-64 bg-zinc-800 animate-pulse" />
          <div className="h-4 w-96 bg-zinc-800/50 animate-pulse mt-3" />
        </div>
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="border border-white/10 bg-zinc-900/30 p-4 flex items-center gap-4">
              <div className="w-8 h-8 bg-zinc-800 animate-pulse shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-48 bg-zinc-800 animate-pulse" />
                <div className="h-3 w-32 bg-zinc-800/50 animate-pulse" />
              </div>
              <div className="h-3 w-16 bg-zinc-800/50 animate-pulse" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-6 md:pb-8">
        <h1 className="text-2xl md:text-4xl font-bold tracking-tighter text-white uppercase">Notifications</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Recent activity across all companies &mdash; {total} total
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Feed */}
      {items.length === 0 && !error ? (
        <div className="border border-white/10 bg-zinc-900/30 text-center py-24">
          <Bell size={24} className="text-zinc-600 mx-auto mb-3" />
          <div className="text-zinc-500 font-mono text-sm uppercase tracking-wider">
            No notifications yet
          </div>
        </div>
      ) : (
        <div className="border border-white/10 bg-zinc-900/30 divide-y divide-white/5">
          {items.map((item) => (
            <div
              key={item.id}
              onClick={() => item.link && navigate(item.link)}
              className="p-4 md:px-6 md:py-4 hover:bg-white/5 transition-colors cursor-pointer active:bg-white/10 flex items-start gap-3 md:gap-4"
            >
              {/* Type Icon */}
              <div className={`w-8 h-8 border flex items-center justify-center shrink-0 mt-0.5 ${TYPE_BG[item.type]}`}>
                {TYPE_ICONS[item.type]}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm text-white font-bold truncate">{item.title}</div>
                    {item.subtitle && (
                      <div className="text-[11px] text-zinc-500 font-mono mt-0.5 truncate">{item.subtitle}</div>
                    )}
                  </div>
                  <div className="text-[10px] text-zinc-600 font-mono tracking-wide whitespace-nowrap shrink-0 mt-0.5">
                    {relativeTime(item.created_at)}
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  {/* Company badge */}
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-zinc-800 border border-zinc-700 text-[10px] text-zinc-400 font-mono uppercase tracking-wider">
                    <Building2 size={10} className="text-zinc-500" />
                    {item.company_name}
                  </span>

                  {/* Severity badge */}
                  {item.severity && (
                    <span className={`inline-flex items-center px-2 py-0.5 border text-[10px] uppercase tracking-wider font-bold ${SEVERITY_CLASSES[item.severity] || 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20'}`}>
                      {item.severity}
                    </span>
                  )}

                  {/* Status badge */}
                  {item.status && (
                    <span className={`inline-flex items-center px-2 py-0.5 border text-[10px] uppercase tracking-wider font-bold ${STATUS_CLASSES[item.status] || 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20'}`}>
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
            className="px-8 py-3 bg-white text-black border border-white text-[10px] uppercase tracking-widest font-bold disabled:opacity-50 disabled:cursor-not-allowed hover:bg-zinc-200 transition-colors"
          >
            {loadingMore ? 'Loading...' : `Load More (${items.length} of ${total})`}
          </button>
        </div>
      )}
    </div>
  );
}

export default AdminNotifications;
