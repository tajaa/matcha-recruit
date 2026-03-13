import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { clientNotifications, adminNotifications } from '../api/client';
import type { ClientNotificationItem, AdminNotificationItem } from '../api/client';
import { useIsLightMode } from '../hooks/useIsLightMode';
import { useAuth } from '../context/AuthContext';
import {
  AlertTriangle,
  UserPlus,
  FileText,
  Scale,
  BookOpen,
  AlertCircle,
  Building2,
  Bell,
  CheckCheck,
  ChevronRight,
} from 'lucide-react';

// ─── Type metadata ────────────────────────────────────────────────────────────

type AllTypes = ClientNotificationItem['type'] | 'registration';

const TYPE_ICONS: Record<AllTypes, React.ReactNode> = {
  incident:         <AlertTriangle size={14} />,
  employee:         <UserPlus size={14} />,
  offer_letter:     <FileText size={14} />,
  er_case:          <Scale size={14} />,
  handbook:         <BookOpen size={14} />,
  compliance_alert: <AlertCircle size={14} />,
  registration:     <Building2 size={14} />,
};

const TYPE_LABEL: Record<AllTypes, string> = {
  incident:         'Incident',
  employee:         'HR',
  offer_letter:     'Offer Letter',
  er_case:          'ER Case',
  handbook:         'Policy',
  compliance_alert: 'Compliance',
  registration:     'Registration',
};

// Icon colors
const TYPE_ICON_COLOR_DK: Record<AllTypes, string> = {
  incident:         'text-zinc-300',
  employee:         'text-zinc-500',
  offer_letter:     'text-zinc-500',
  er_case:          'text-zinc-300',
  handbook:         'text-zinc-500',
  compliance_alert: 'text-zinc-300',
  registration:     'text-zinc-500',
};

const TYPE_ICON_COLOR_LT: Record<AllTypes, string> = {
  incident:         'text-stone-700',
  employee:         'text-stone-500',
  offer_letter:     'text-stone-500',
  er_case:          'text-stone-700',
  handbook:         'text-stone-500',
  compliance_alert: 'text-stone-700',
  registration:     'text-stone-500',
};

// Left accent strip color
const TYPE_STRIP_DK: Record<AllTypes, string> = {
  incident:         'bg-zinc-400',
  employee:         'bg-zinc-700',
  offer_letter:     'bg-zinc-700',
  er_case:          'bg-zinc-400',
  handbook:         'bg-zinc-700',
  compliance_alert: 'bg-zinc-400',
  registration:     'bg-zinc-700',
};

const TYPE_STRIP_LT: Record<AllTypes, string> = {
  incident:         'bg-stone-500',
  employee:         'bg-stone-300',
  offer_letter:     'bg-stone-300',
  er_case:          'bg-stone-500',
  handbook:         'bg-stone-300',
  compliance_alert: 'bg-stone-500',
  registration:     'bg-stone-300',
};

// ─── Badge color maps ─────────────────────────────────────────────────────────

const SEVERITY_DK: Record<string, string> = {
  critical: 'bg-zinc-800 text-zinc-100',
  high:     'bg-zinc-800 text-zinc-300',
  medium:   'bg-zinc-800 text-zinc-400',
  low:      'bg-zinc-800 text-zinc-500',
};

const SEVERITY_LT: Record<string, string> = {
  critical: 'bg-stone-200 text-zinc-900',
  high:     'bg-stone-200 text-stone-700',
  medium:   'bg-stone-200 text-stone-600',
  low:      'bg-stone-200 text-stone-500',
};

const STATUS_DK: Record<string, string> = {
  investigating: 'bg-zinc-800 text-zinc-100',
  pending:       'bg-zinc-800 text-zinc-400',
  draft:         'bg-zinc-800 text-zinc-500',
  onboarded:     'bg-zinc-800 text-zinc-400',
  approved:      'bg-zinc-800 text-zinc-400',
  active:        'bg-zinc-800 text-zinc-400',
  resolved:      'bg-zinc-800 text-zinc-400',
  closed:        'bg-zinc-800 text-zinc-600',
  rejected:      'bg-zinc-800 text-zinc-100',
  sent:          'bg-zinc-800 text-zinc-400',
  open:          'bg-zinc-800 text-zinc-400',
};

const STATUS_LT: Record<string, string> = {
  investigating: 'bg-stone-200 text-zinc-900',
  pending:       'bg-stone-200 text-stone-600',
  draft:         'bg-stone-100 text-stone-400',
  onboarded:     'bg-stone-100 text-stone-400',
  approved:      'bg-stone-100 text-stone-400',
  active:        'bg-stone-100 text-stone-400',
  resolved:      'bg-stone-100 text-stone-400',
  closed:        'bg-stone-100 text-stone-400',
  rejected:      'bg-stone-200 text-zinc-900',
  sent:          'bg-stone-100 text-stone-400',
  open:          'bg-stone-100 text-stone-400',
};

// ─── Theme tokens (Matched to Dashboard.tsx) ──────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  cardLight: 'bg-stone-100 rounded-xl',
  innerHover: 'bg-stone-200 rounded-lg hover:bg-stone-300',
  innerEl: 'bg-stone-200 rounded-lg',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  footerBg: 'border-t border-stone-200 bg-stone-200',
  rowHover: 'hover:bg-stone-50',
  icon: 'text-stone-400',
  arrow: 'text-stone-400 group-hover:text-zinc-900',
  label: 'text-xs text-stone-500 font-semibold',
  labelOnDark: 'text-xs text-zinc-500 font-semibold',
  cardDark: 'bg-zinc-900 rounded-xl',
  cardDarkHover: 'hover:bg-zinc-800',
  cardDarkGhost: 'text-zinc-800',
  cardDarkText: 'text-zinc-100',
  cardDarkMuted: 'text-zinc-400',
  cardDarkBorder: 'border-zinc-800',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900',
  livePill: 'bg-stone-200 text-stone-600',
  skeleton: 'bg-stone-200',
  skeletonFaint: 'bg-stone-100',
  emptyBg: 'bg-stone-100',
  emptyIcon: 'text-stone-300',
  emptyText: 'text-stone-400',
  errorBg: 'bg-stone-200 text-stone-700',
  filterActive: 'bg-zinc-900 text-zinc-50',
  filterIdle: 'bg-stone-200 text-stone-500 hover:text-zinc-900',
  countBadge: 'bg-stone-200 text-stone-600',
  typeLabel: 'text-stone-500',
  subtitle: 'text-stone-600',
  time: 'text-stone-400',
  iconColor: TYPE_ICON_COLOR_LT,
  strip: TYPE_STRIP_LT,
  severity: SEVERITY_LT,
  status: STATUS_LT,
  companyBadge: 'bg-stone-200 text-stone-500',
  companyIcon: 'text-stone-400',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  cardLight: 'bg-zinc-900/50 border border-white/10 rounded-xl',
  innerHover: 'bg-zinc-800 rounded-lg hover:bg-zinc-700',
  innerEl: 'bg-zinc-800 rounded-lg',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  divide: 'divide-white/10',
  footerBg: 'border-t border-white/10 bg-white/5',
  rowHover: 'hover:bg-white/5',
  icon: 'text-zinc-600',
  arrow: 'text-zinc-600 group-hover:text-zinc-100',
  label: 'text-xs text-zinc-500 font-semibold',
  labelOnDark: 'text-xs text-zinc-500 font-semibold',
  cardDark: 'bg-zinc-800 rounded-xl',
  cardDarkHover: 'hover:bg-zinc-700',
  cardDarkGhost: 'text-zinc-700',
  cardDarkText: 'text-zinc-100',
  cardDarkMuted: 'text-zinc-400',
  cardDarkBorder: 'border-white/10',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100',
  livePill: 'bg-zinc-800 text-zinc-400',
  skeleton: 'bg-zinc-800',
  skeletonFaint: 'bg-zinc-800/40',
  emptyBg: 'bg-zinc-900/50 border border-white/10',
  emptyIcon: 'text-zinc-700',
  emptyText: 'text-zinc-500',
  errorBg: 'bg-zinc-800 border border-white/10 text-zinc-100',
  filterActive: 'bg-zinc-700 text-zinc-100',
  filterIdle: 'bg-zinc-800 text-zinc-500 hover:text-zinc-100',
  countBadge: 'bg-zinc-800 text-zinc-300',
  typeLabel: 'text-zinc-500',
  subtitle: 'text-zinc-400',
  time: 'text-zinc-500',
  iconColor: TYPE_ICON_COLOR_DK,
  strip: TYPE_STRIP_DK,
  severity: SEVERITY_DK,
  status: STATUS_DK,
  companyBadge: 'bg-zinc-800 text-zinc-400',
  companyIcon: 'text-zinc-500',
} as const;

// ─── Filters ──────────────────────────────────────────────────────────────────

type FilterType = AllTypes | 'all';

const CLIENT_FILTERS: { key: FilterType; label: string }[] = [
  { key: 'all',             label: 'All' },
  { key: 'incident',        label: 'Incidents' },
  { key: 'compliance_alert',label: 'Compliance' },
  { key: 'er_case',         label: 'ER Cases' },
  { key: 'employee',        label: 'HR' },
  { key: 'offer_letter',    label: 'Offers' },
  { key: 'handbook',        label: 'Policies' },
];

const ADMIN_FILTERS: { key: FilterType; label: string }[] = [
  ...CLIENT_FILTERS,
  { key: 'registration',    label: 'Registrations' },
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

// Unified item shape for rendering
interface UnifiedItem {
  id: string;
  type: AllTypes;
  title: string;
  subtitle: string | null;
  severity: string | null;
  status: string | null;
  created_at: string;
  link: string | null;
  company_name?: string;
}

function groupItems(items: UnifiedItem[]) {
  const order = ['Today', 'Yesterday', 'This Week', 'Earlier'];
  const map: Record<string, UnifiedItem[]> = {};
  for (const item of items) {
    const g = getTimeGroup(item.created_at);
    if (!map[g]) map[g] = [];
    map[g].push(item);
  }
  return order.filter(g => map[g]).map(label => ({ label, items: map[label] }));
}

// ─── Component ────────────────────────────────────────────────────────────────

type TabValue = 'company' | 'platform';
const PAGE_SIZE = 30;

export function ClientNotifications() {
  const navigate    = useNavigate();
  const isLight     = useIsLightMode();
  const { hasRole } = useAuth();
  const isAdmin     = hasRole('admin');
  const tk          = isLight ? LT : DK;

  const [tab, setTab] = useState<TabValue>('company');

  // Company state
  const [clientItems,       setClientItems]       = useState<ClientNotificationItem[]>([]);
  const [clientTotal,       setClientTotal]       = useState(0);
  const [clientLoading,     setClientLoading]     = useState(true);
  const [clientLoadingMore, setClientLoadingMore] = useState(false);
  const [clientError,       setClientError]       = useState<string | null>(null);

  // Platform state
  const [adminItems,       setAdminItems]       = useState<AdminNotificationItem[]>([]);
  const [adminTotal,       setAdminTotal]       = useState(0);
  const [adminLoading,     setAdminLoading]     = useState(true);
  const [adminLoadingMore, setAdminLoadingMore] = useState(false);
  const [adminError,       setAdminError]       = useState<string | null>(null);
  const [adminLoaded,      setAdminLoaded]      = useState(false);

  const [filter, setFilter] = useState<FilterType>('all');

  const fetchClient = useCallback(async (offset = 0, append = false) => {
    try {
      if (append) setClientLoadingMore(true);
      else        setClientLoading(true);
      const data = await clientNotifications.get(PAGE_SIZE, offset);
      if (append) setClientItems(prev => [...prev, ...data.items]);
      else        setClientItems(data.items);
      setClientTotal(data.total);
    } catch {
      setClientError('Failed to load notifications');
    } finally {
      setClientLoading(false);
      setClientLoadingMore(false);
    }
  }, []);

  const fetchAdmin = useCallback(async (offset = 0, append = false) => {
    try {
      if (append) setAdminLoadingMore(true);
      else        setAdminLoading(true);
      const data = await adminNotifications.get(PAGE_SIZE, offset);
      if (append) setAdminItems(prev => [...prev, ...data.items]);
      else        setAdminItems(data.items);
      setAdminTotal(data.total);
      setAdminLoaded(true);
    } catch {
      setAdminError('Failed to load notifications');
    } finally {
      setAdminLoading(false);
      setAdminLoadingMore(false);
    }
  }, []);

  useEffect(() => { fetchClient(); }, [fetchClient]);

  // Lazy-load admin tab on first switch
  useEffect(() => {
    if (tab === 'platform' && isAdmin && !adminLoaded) fetchAdmin();
  }, [tab, isAdmin, adminLoaded, fetchAdmin]);

  // Reset filter when switching tabs
  useEffect(() => { setFilter('all'); }, [tab]);

  // Current tab data
  const isCompany   = tab === 'company';
  const items: UnifiedItem[] = isCompany ? clientItems : adminItems;
  const total       = isCompany ? clientTotal : adminTotal;
  const loading     = isCompany ? clientLoading : adminLoading;
  const loadingMore = isCompany ? clientLoadingMore : adminLoadingMore;
  const error       = isCompany ? clientError : adminError;
  const hasMore     = items.length < total;
  const filters     = isCompany ? CLIENT_FILTERS : ADMIN_FILTERS;

  const handleLoadMore = () => {
    if (isCompany) fetchClient(clientItems.length, true);
    else           fetchAdmin(adminItems.length, true);
  };

  const filtered = filter === 'all' ? items : items.filter(i => i.type === filter);
  const groups   = groupItems(filtered);

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
        <div className={`${tk.cardDark} border ${tk.cardDarkBorder} rounded-xl overflow-hidden`}>
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
    <div className="max-w-5xl mx-auto py-4 px-4 sm:px-6">

      {/* ── Header ── */}
      <div className={`pb-4 mb-4 border-b ${tk.border}`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <h1 className={`text-base font-semibold ${tk.textMain}`}>Notifications</h1>
              {total > 0 && (
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-sm border font-mono ${tk.countBadge}`}>
                  {total}
                </span>
              )}
            </div>
            <p className={`text-xs ${tk.textMuted}`}>
              {isCompany ? 'Compliance alerts, incidents, and activity log' : 'Activity across all companies'}
            </p>
          </div>
          <button
            onClick={() => {}}
            className={`flex items-center gap-1.5 text-[10px] font-bold font-mono uppercase tracking-wider px-2.5 py-1 rounded-sm border transition-colors shrink-0 ${tk.btnSecondary}`}
          >
            <CheckCheck size={11} />
            Mark all read
          </button>
        </div>

        {/* Tab switcher (only show if admin) */}
        {isAdmin && (
          <div className="flex items-center gap-2 mt-3">
            {([
              { key: 'company' as const, label: 'Company', hint: 'Your company' },
              { key: 'platform' as const, label: 'Platform', hint: 'All companies' },
            ]).map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-1.5 px-2 py-1 text-[10px] font-bold font-mono uppercase tracking-wider rounded-sm border transition-colors ${
                  tab === t.key ? tk.filterActive : tk.filterIdle
                }`}
              >
                {t.label}
                <span className={`font-normal normal-case tracking-normal ${tab === t.key ? 'opacity-50' : 'opacity-40'}`}>
                  {t.hint}
                </span>
              </button>
            ))}
          </div>
        )}

        {/* Filter tabs */}
        <div className="flex items-center gap-1 mt-3 flex-wrap">
          {filters.map(({ key, label }) => {
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
        <div className={`${tk.cardDark} rounded-sm text-center py-12`}>
          <div className={`w-8 h-8 rounded-sm ${tk.innerEl} flex items-center justify-center mx-auto mb-3`}>
            <Bell size={14} className={tk.cardDarkMuted} />
          </div>
          <p className={`text-sm font-semibold ${tk.cardDarkText} mb-1`}>No notifications</p>
          <p className={`text-xs ${tk.cardDarkMuted}`}>
            {filter === 'all' ? "You're all caught up." : `No ${TYPE_LABEL[filter as AllTypes] ?? filter} activity.`}
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
              <div className={`${tk.cardDark} border ${tk.cardDarkBorder} rounded-sm overflow-hidden`}>
                {group.items.map((item, idx) => (
                  <div
                    key={item.id}
                    onClick={() => item.link && navigate(item.link)}
                    className={`relative flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors ${tk.cardDarkHover} ${
                      idx > 0 ? `border-t ${isLight ? 'border-stone-100' : 'border-white/[0.04]'}` : ''
                    }`}
                  >
                    {/* Left type strip */}
                    <div className={`w-0.5 self-stretch shrink-0 ${tk.strip[item.type]}`} />

                    {/* Icon */}
                    <div className={`w-7 h-7 flex items-center justify-center shrink-0 rounded-sm ${tk.innerEl}`}>
                      <span className={tk.iconColor[item.type]}>
                        {TYPE_ICONS[item.type]}
                      </span>
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-[9px] font-bold font-mono uppercase tracking-widest ${tk.cardDarkMuted}`}>
                          {TYPE_LABEL[item.type]}
                        </span>
                        {/* Company badge for platform tab */}
                        {!isCompany && item.company_name && (
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold font-mono rounded-sm ${tk.companyBadge}`}>
                            <Building2 size={9} className={tk.companyIcon} />
                            {item.company_name}
                          </span>
                        )}
                      </div>
                      <div className={`text-[12px] font-semibold leading-tight truncate ${tk.cardDarkText}`}>
                        {item.title}
                      </div>
                      {item.subtitle && (
                        <div className={`text-[11px] ${tk.cardDarkMuted} truncate mt-0.5`}>
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
                      <span className={`text-[10px] font-mono tabular-nums ${tk.cardDarkMuted}`}>
                        {relativeTime(item.created_at)}
                      </span>
                      {item.link && (
                        <ChevronRight size={12} className={`${tk.cardDarkMuted} opacity-0 group-hover:opacity-100`} />
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
            className={`px-4 py-1.5 text-[10px] font-bold font-mono uppercase tracking-wider rounded-sm border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${tk.btnSecondary}`}
          >
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}

export default ClientNotifications;
