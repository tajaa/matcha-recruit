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
  CheckCheck,
  ChevronRight,
} from 'lucide-react';

// ─── Type metadata ────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<ClientNotificationItem['type'], React.ReactNode> = {
  incident:         <AlertTriangle size={14} />,
  employee:         <UserPlus size={14} />,
  offer_letter:     <FileText size={14} />,
  er_case:          <Scale size={14} />,
  handbook:         <BookOpen size={14} />,
  compliance_alert: <AlertCircle size={14} />,
};

const TYPE_LABEL: Record<ClientNotificationItem['type'], string> = {
  incident:         'Incident',
  employee:         'HR',
  offer_letter:     'Offer Letter',
  er_case:          'ER Case',
  handbook:         'Policy',
  compliance_alert: 'Compliance',
};

// Icon colors
const TYPE_ICON_COLOR_DK: Record<ClientNotificationItem['type'], string> = {
  incident:         'text-zinc-300',
  employee:         'text-zinc-500',
  offer_letter:     'text-zinc-500',
  er_case:          'text-zinc-300',
  handbook:         'text-zinc-500',
  compliance_alert: 'text-zinc-300',
};

const TYPE_ICON_COLOR_LT: Record<ClientNotificationItem['type'], string> = {
  incident:         'text-stone-700',
  employee:         'text-stone-500',
  offer_letter:     'text-stone-500',
  er_case:          'text-stone-700',
  handbook:         'text-stone-500',
  compliance_alert: 'text-stone-700',
};

// Left accent strip color
const TYPE_STRIP_DK: Record<ClientNotificationItem['type'], string> = {
  incident:         'bg-zinc-400',
  employee:         'bg-zinc-700',
  offer_letter:     'bg-zinc-700',
  er_case:          'bg-zinc-400',
  handbook:         'bg-zinc-700',
  compliance_alert: 'bg-zinc-400',
};

const TYPE_STRIP_LT: Record<ClientNotificationItem['type'], string> = {
  incident:         'bg-stone-500',
  employee:         'bg-stone-300',
  offer_letter:     'bg-stone-300',
  er_case:          'bg-stone-500',
  handbook:         'bg-stone-300',
  compliance_alert: 'bg-stone-500',
};

// ─── Badge color maps ─────────────────────────────────────────────────────────

const SEVERITY_DK: Record<string, string> = {
  critical: 'bg-zinc-700 text-zinc-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_1px_2px_rgba(0,0,0,0.2)]',
  high:     'bg-zinc-800 text-zinc-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_1px_2px_rgba(0,0,0,0.2)]',
  medium:   'bg-zinc-800/60 text-zinc-400',
  low:      'bg-zinc-900/50 text-zinc-500',
};

const SEVERITY_LT: Record<string, string> = {
  critical: 'bg-stone-800 text-stone-50 shadow-[0_1px_2px_rgba(0,0,0,0.1)]',
  high:     'bg-stone-600 text-stone-100 shadow-[0_1px_2px_rgba(0,0,0,0.05)]',
  medium:   'bg-stone-300 text-stone-800',
  low:      'bg-stone-200 text-stone-600',
};

const STATUS_DK: Record<string, string> = {
  investigating: 'bg-zinc-800 text-zinc-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_1px_2px_rgba(0,0,0,0.2)]',
  pending:       'bg-zinc-800/60 text-zinc-300',
  draft:         'bg-zinc-900/50 text-zinc-500',
  onboarded:     'bg-zinc-900 text-zinc-400',
  approved:      'bg-zinc-900 text-zinc-400',
  active:        'bg-zinc-900 text-zinc-400',
  resolved:      'bg-zinc-900 text-zinc-400',
  closed:        'bg-zinc-950/80 text-zinc-600',
  rejected:      'bg-zinc-800 text-zinc-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_1px_2px_rgba(0,0,0,0.2)]',
  sent:          'bg-zinc-900 text-zinc-400',
  open:          'bg-zinc-900 text-zinc-400',
};

const STATUS_LT: Record<string, string> = {
  investigating: 'bg-stone-700 text-stone-100 shadow-[0_1px_2px_rgba(0,0,0,0.1)]',
  pending:       'bg-stone-400 text-stone-900',
  draft:         'bg-stone-200 text-stone-500',
  onboarded:     'bg-stone-300 text-stone-800',
  approved:      'bg-stone-300 text-stone-800',
  active:        'bg-stone-300 text-stone-800',
  resolved:      'bg-stone-300 text-stone-800',
  closed:        'bg-stone-200 text-stone-500',
  rejected:      'bg-stone-700 text-stone-100 shadow-[0_1px_2px_rgba(0,0,0,0.1)]',
  sent:          'bg-stone-300 text-stone-800',
  open:          'bg-stone-300 text-stone-800',
};

// ─── Theme tokens ─────────────────────────────────────────────────────────────

const DK = {
  page:          'bg-zinc-950',
  heading:       'text-zinc-100',
  subheading:    'text-zinc-500',
  border:        'border-white/[0.07]',
  divider:       'divide-white/[0.05]',
  surface:       'bg-zinc-900 shadow-sm',
  surfaceBorder: 'border-white/[0.05]',
  rowHover:      'hover:bg-white/[0.03]',
  iconBg:        'bg-gradient-to-b from-zinc-700 to-zinc-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_2px_4px_rgba(0,0,0,0.4)]',
  iconBgBorder:  '',
  typeLabel:     'text-zinc-600',
  time:          'text-zinc-600',
  subtitle:      'text-zinc-500',
  skeleton:      'bg-zinc-800',
  skeletonFaint: 'bg-zinc-800/40',
  emptyBg:       'bg-zinc-900/40 border border-white/[0.07]',
  emptyIcon:     'text-zinc-700',
  emptyText:     'text-zinc-500',
  errorBg:       'bg-zinc-900/80 border border-zinc-600/50 text-zinc-300',
  filterActive:  'bg-zinc-200 text-zinc-900 shadow-[inset_0_-1px_0_rgba(0,0,0,0.1)] border-transparent',
  filterIdle:    'bg-transparent text-zinc-500 border-white/[0.08] hover:text-zinc-200 hover:border-white/20',
  markRead:      'text-zinc-600 border-white/[0.08] hover:text-zinc-200 hover:border-white/20',
  loadMore:      'bg-zinc-900 border-white/[0.08] text-zinc-400 hover:border-white/20 hover:text-zinc-200 shadow-sm',
  countBadge:    'bg-zinc-800 text-zinc-300 border-transparent shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_1px_2px_rgba(0,0,0,0.2)]',
  iconColor:     TYPE_ICON_COLOR_DK,
  strip:         TYPE_STRIP_DK,
  severity:      SEVERITY_DK,
  status:        STATUS_DK,
} as const;

const LT = {
  page:          'bg-stone-100',
  heading:       'text-zinc-900',
  subheading:    'text-stone-500',
  border:        'border-stone-200',
  divider:       'divide-stone-200',
  surface:       'bg-white shadow-sm',
  surfaceBorder: 'border-stone-200',
  rowHover:      'hover:bg-stone-50',
  iconBg:        'bg-gradient-to-b from-stone-50 to-stone-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.8),0_1px_2px_rgba(0,0,0,0.1)]',
  iconBgBorder:  '',
  typeLabel:     'text-stone-400',
  time:          'text-stone-400',
  subtitle:      'text-stone-500',
  skeleton:      'bg-stone-200',
  skeletonFaint: 'bg-stone-100',
  emptyBg:       'bg-white border border-stone-200',
  emptyIcon:     'text-stone-300',
  emptyText:     'text-stone-400',
  errorBg:       'bg-stone-100 border border-stone-300 text-stone-700',
  filterActive:  'bg-stone-800 text-stone-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] border-transparent',
  filterIdle:    'bg-white text-stone-500 border-stone-200 hover:text-zinc-700 hover:border-stone-300',
  markRead:      'text-stone-500 border-stone-200 hover:text-zinc-700 hover:border-stone-300',
  loadMore:      'bg-white border-stone-200 text-stone-600 hover:border-stone-300 hover:text-zinc-700 shadow-sm',
  countBadge:    'bg-stone-200 text-stone-600 border-transparent shadow-[inset_0_1px_0_rgba(255,255,255,0.5),0_1px_2px_rgba(0,0,0,0.05)]',
  iconColor:     TYPE_ICON_COLOR_LT,
  strip:         TYPE_STRIP_LT,
  severity:      SEVERITY_LT,
  status:        STATUS_LT,
} as const;

// ─── Filters ──────────────────────────────────────────────────────────────────

type FilterType = ClientNotificationItem['type'] | 'all';

const FILTERS: { key: FilterType; label: string }[] = [
  { key: 'all',             label: 'All' },
  { key: 'incident',        label: 'Incidents' },
  { key: 'compliance_alert',label: 'Compliance' },
  { key: 'er_case',         label: 'ER Cases' },
  { key: 'employee',        label: 'HR' },
  { key: 'offer_letter',    label: 'Offers' },
  { key: 'handbook',        label: 'Policies' },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

function getTimeGroup(dateStr: string): string {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const diffHr = diffMs / (1000 * 60 * 60);
  if (diffHr < 24)  return 'Today';
  if (diffHr < 48)  return 'Yesterday';
  if (diffHr < 168) return 'This Week';
  return 'Earlier';
}

function groupItems(items: ClientNotificationItem[]) {
  const order = ['Today', 'Yesterday', 'This Week', 'Earlier'];
  const map: Record<string, ClientNotificationItem[]> = {};
  for (const item of items) {
    const g = getTimeGroup(item.created_at);
    if (!map[g]) map[g] = [];
    map[g].push(item);
  }
  return order.filter(g => map[g]).map(label => ({ label, items: map[label] }));
}

// ─── Component ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 30;

export function ClientNotifications() {
  const navigate    = useNavigate();
  const isLight     = useIsLightMode();
  const tk          = isLight ? LT : DK;

  const [items,       setItems]       = useState<ClientNotificationItem[]>([]);
  const [total,       setTotal]       = useState(0);
  const [loading,     setLoading]     = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  const [filter,      setFilter]      = useState<FilterType>('all');

  const fetchNotifications = useCallback(async (offset = 0, append = false) => {
    try {
      if (append) setLoadingMore(true);
      else        setLoading(true);
      const data = await clientNotifications.get(PAGE_SIZE, offset);
      if (append) setItems(prev => [...prev, ...data.items]);
      else        setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to fetch notifications:', err);
      setError('Failed to load notifications');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => { fetchNotifications(); }, [fetchNotifications]);

  const handleLoadMore = () => fetchNotifications(items.length, true);

  const filtered = filter === 'all' ? items : items.filter(i => i.type === filter);
  const groups   = groupItems(filtered);
  const hasMore  = items.length < total;

  // ── Loading skeleton ──────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto py-8 px-4 sm:px-6">
        <div className={`pb-6 mb-6 border-b ${tk.border}`}>
          <div className={`h-5 w-40 ${tk.skeleton} animate-pulse rounded-md mb-2`} />
          <div className={`h-3.5 w-64 ${tk.skeletonFaint} animate-pulse rounded-md`} />
          <div className="flex gap-2 mt-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className={`h-7 w-20 ${tk.skeletonFaint} animate-pulse rounded-lg`} />
            ))}
          </div>
        </div>
        <div className={`${tk.surface} border ${tk.surfaceBorder} rounded-xl overflow-hidden`}>
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className={`flex items-center gap-4 px-5 py-4 ${i > 0 ? `border-t ${tk.border}` : ''}`}
              style={{ opacity: 1 - i * 0.1 }}
            >
              <div className="w-1 self-stretch rounded-full bg-zinc-800/60 shrink-0" />
              <div className={`w-8 h-8 ${tk.skeleton} animate-pulse rounded-lg shrink-0`} />
              <div className="flex-1 space-y-2">
                <div className={`h-3.5 ${tk.skeleton} animate-pulse rounded-md`} style={{ width: `${50 + (i % 4) * 12}%` }} />
                <div className={`h-3 ${tk.skeletonFaint} animate-pulse rounded-md w-1/4`} />
              </div>
              <div className={`h-6 w-16 ${tk.skeletonFaint} animate-pulse rounded-lg shrink-0`} />
              <div className={`h-3 w-12 ${tk.skeletonFaint} animate-pulse rounded-md shrink-0`} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Full render ───────────────────────────────────────────────────────────

  return (
    <div className="max-w-4xl mx-auto py-6 px-4 sm:px-6">

      {/* ── Header ── */}
      <div className={`pb-4 mb-4 border-b ${tk.border}`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <h1 className={`text-base font-semibold ${tk.heading}`}>Notifications</h1>
              {total > 0 && (
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-sm border font-mono ${tk.countBadge}`}>
                  {total}
                </span>
              )}
            </div>
            <p className={`text-xs ${tk.subheading}`}>
              Compliance alerts, incidents, and activity log
            </p>
          </div>
          <button
            onClick={() => {}}
            className={`flex items-center gap-1.5 text-[10px] font-bold font-mono uppercase tracking-wider px-2.5 py-1 rounded-sm border transition-colors shrink-0 ${tk.markRead}`}
          >
            <CheckCheck size={11} />
            Mark all read
          </button>
        </div>

        {/* Filter tabs */}
        <div className="flex items-center gap-1 mt-4 flex-wrap">
          {FILTERS.map(({ key, label }) => {
            const count = key === 'all'
              ? items.length
              : items.filter(i => i.type === key).length;
            return (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`inline-flex items-center gap-1.5 px-2 py-1 text-[10px] font-bold font-mono uppercase tracking-wider rounded-sm border transition-colors ${
                  filter === key ? tk.filterActive : tk.filterIdle
                }`}
              >
                {label}
                {count > 0 && (
                  <span className={`text-[9px] font-bold tabular-nums ${filter === key ? 'opacity-60' : 'opacity-40'}`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className={`p-3 text-sm rounded-sm mb-4 ${tk.errorBg}`}>
          {error}
        </div>
      )}

      {/* Empty state */}
      {filtered.length === 0 && !error && (
        <div className={`${tk.emptyBg} rounded-sm text-center py-12`}>
          <div className={`w-8 h-8 rounded-sm bg-zinc-800/50 flex items-center justify-center mx-auto mb-3`}>
            <Bell size={14} className={tk.emptyIcon} />
          </div>
          <p className={`text-sm font-semibold ${tk.heading} mb-1`}>No notifications</p>
          <p className={`text-xs ${tk.emptyText}`}>
            {filter === 'all' ? "You're all caught up." : `No ${TYPE_LABEL[filter as ClientNotificationItem['type']] ?? filter} activity.`}
          </p>
        </div>
      )}

      {/* Feed */}
      {groups.length > 0 && (
        <div className="space-y-4">
          {groups.map((group) => (
            <div key={group.label}>
              {/* Group label */}
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-[9px] font-bold font-mono uppercase tracking-widest ${tk.typeLabel}`}>
                  {group.label}
                </span>
                <div className={`flex-1 h-px ${isLight ? 'bg-stone-200' : 'bg-white/[0.05]'}`} />
              </div>

              {/* Rows */}
              <div className={`${tk.surface} border ${tk.surfaceBorder} rounded-sm overflow-hidden`}>
                {group.items.map((item, idx) => (
                  <div
                    key={item.id}
                    onClick={() => item.link && navigate(item.link)}
                    className={`relative flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors ${tk.rowHover} ${
                      idx > 0 ? `border-t ${isLight ? 'border-stone-100' : 'border-white/[0.04]'}` : ''
                    }`}
                  >
                    {/* Left type strip */}
                    <div className={`w-0.5 self-stretch shrink-0 ${tk.strip[item.type]}`} />

                    {/* Icon */}
                    <div className={`w-7 h-7 flex items-center justify-center shrink-0 rounded-sm ${tk.iconBg}`}>
                      <span className={tk.iconColor[item.type]}>
                        {TYPE_ICONS[item.type]}
                      </span>
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-[9px] font-bold font-mono uppercase tracking-widest ${tk.typeLabel}`}>
                          {TYPE_LABEL[item.type]}
                        </span>
                      </div>
                      <div className={`text-[12px] font-semibold leading-tight truncate ${tk.heading}`}>
                        {item.title}
                      </div>
                      {item.subtitle && (
                        <div className={`text-[11px] ${tk.subtitle} truncate mt-0.5`}>
                          {item.subtitle}
                        </div>
                      )}
                    </div>

                    {/* Badges */}
                    {(item.severity || item.status) && (
                      <div className="flex items-center gap-1.5 shrink-0">
                        {item.severity && (
                          <span className={`text-[9px] font-bold font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-sm ${tk.severity[item.severity] ?? ''}`}>
                            {item.severity}
                          </span>
                        )}
                        {item.status && (
                          <span className={`text-[9px] font-bold font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-sm ${tk.status[item.status] ?? ''}`}>
                            {item.status.replace('_', ' ')}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Time + chevron */}
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`text-[10px] font-mono tabular-nums ${tk.time}`}>
                        {relativeTime(item.created_at)}
                      </span>
                      {item.link && (
                        <ChevronRight size={12} className={`${tk.typeLabel} opacity-0 group-hover:opacity-100`} />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Load More */}
      {hasMore && (
        <div className="flex justify-center pt-4">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className={`px-4 py-1.5 text-[10px] font-bold font-mono uppercase tracking-wider rounded-sm border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${tk.loadMore}`}
          >
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}

export default ClientNotifications;
