import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { clientNotifications, adminNotifications } from '../api/client';
import type { ClientNotificationItem, AdminNotificationItem } from '../api/client';
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
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';

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

const TYPE_ICON_COLOR: Record<AllTypes, string> = {
  incident:         'text-zinc-300',
  employee:         'text-zinc-500',
  offer_letter:     'text-zinc-500',
  er_case:          'text-zinc-300',
  handbook:         'text-zinc-500',
  compliance_alert: 'text-zinc-300',
  registration:     'text-zinc-500',
};

const TYPE_STRIP: Record<AllTypes, string> = {
  incident:         'bg-zinc-400',
  employee:         'bg-zinc-700',
  offer_letter:     'bg-zinc-700',
  er_case:          'bg-zinc-400',
  handbook:         'bg-zinc-700',
  compliance_alert: 'bg-zinc-400',
  registration:     'bg-zinc-700',
};

// ─── Filters ──────────────────────────────────────────────────────────────────

type FilterType = AllTypes | 'all';

const CLIENT_FILTERS: { key: FilterType; label: string }[] = [
  { key: 'all',              label: 'All' },
  { key: 'incident',         label: 'Incidents' },
  { key: 'compliance_alert', label: 'Compliance' },
  { key: 'er_case',          label: 'ER Cases' },
  { key: 'employee',         label: 'HR' },
  { key: 'offer_letter',     label: 'Offers' },
  { key: 'handbook',         label: 'Policies' },
];

const ADMIN_FILTERS: { key: FilterType; label: string }[] = [
  ...CLIENT_FILTERS,
  { key: 'registration', label: 'Registrations' },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relativeTime(dateStr: string): string {
  const diffSec = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return `${Math.floor(diffDay / 30)}mo ago`;
}

function getTimeGroup(dateStr: string): string {
  const diffHr = (Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60);
  if (diffHr < 24)  return 'Today';
  if (diffHr < 48)  return 'Yesterday';
  if (diffHr < 168) return 'This Week';
  return 'Earlier';
}

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
  const { hasRole } = useAuth();
  const isAdmin     = hasRole('admin');

  const [tab, setTab] = useState<TabValue>('company');

  const [clientItems,       setClientItems]       = useState<ClientNotificationItem[]>([]);
  const [clientTotal,       setClientTotal]       = useState(0);
  const [clientLoading,     setClientLoading]     = useState(true);
  const [clientLoadingMore, setClientLoadingMore] = useState(false);
  const [clientError,       setClientError]       = useState<string | null>(null);

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
  useEffect(() => { if (tab === 'platform' && isAdmin && !adminLoaded) fetchAdmin(); }, [tab, isAdmin, adminLoaded, fetchAdmin]);
  useEffect(() => { setFilter('all'); }, [tab]);

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

  // ── Loading skeleton ───────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto py-6 px-4 sm:px-6 space-y-5">
        <div className="pb-4 border-b border-stone-200 space-y-2">
          <div className="h-5 w-32 bg-stone-200 animate-pulse rounded-md" />
          <div className="h-3.5 w-56 bg-stone-200/60 animate-pulse rounded-md" />
          <div className="flex gap-2 mt-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-7 w-20 bg-stone-200/60 animate-pulse rounded-lg" />
            ))}
          </div>
        </div>
        <div className="bg-zinc-900 rounded-xl overflow-hidden">
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className={`flex items-center gap-4 px-5 py-4 ${i > 0 ? 'border-t border-zinc-800' : ''}`}
              style={{ opacity: 1 - i * 0.1 }}
            >
              <div className="w-0.5 self-stretch rounded-full bg-zinc-700 shrink-0" />
              <div className="w-8 h-8 bg-zinc-800 animate-pulse rounded-lg shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-3.5 bg-zinc-800 animate-pulse rounded-md" style={{ width: `${50 + (i % 4) * 12}%` }} />
                <div className="h-3 bg-zinc-800/60 animate-pulse rounded-md w-1/4" />
              </div>
              <div className="h-6 w-16 bg-zinc-800/60 animate-pulse rounded-lg shrink-0" />
              <div className="h-3 w-12 bg-zinc-800/60 animate-pulse rounded-md shrink-0" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Full render ────────────────────────────────────────────────────────────

  return (
    <div className="max-w-6xl mx-auto py-4 px-4 sm:px-6 space-y-5">

      <PageHeader
        title={
          <span className="flex items-center gap-2">
            Notifications
            {total > 0 && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-stone-300 font-mono text-stone-500">
                {total}
              </span>
            )}
          </span>
        }
        subtitle={isCompany ? 'Compliance alerts, incidents, and activity log' : 'Activity across all companies'}
      >
        <button
          onClick={() => {}}
          className="flex items-center gap-1.5 text-[10px] font-bold font-mono uppercase tracking-wider px-2.5 py-1 rounded border border-stone-300 text-stone-600 hover:border-stone-400 hover:text-zinc-900 transition-colors"
        >
          <CheckCheck size={11} />
          Mark all read
        </button>
      </PageHeader>

      {/* Admin tab switcher */}
      {isAdmin && (
        <div className="flex items-center gap-2">
          {(['company', 'platform'] as TabValue[]).map((key) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-2.5 py-1 text-[10px] font-bold font-mono uppercase tracking-wider rounded border transition-colors ${
                tab === key
                  ? 'bg-zinc-900 text-zinc-50 border-zinc-900'
                  : 'bg-stone-200 text-stone-500 border-stone-200 hover:text-zinc-900'
              }`}
            >
              {key === 'company' ? 'Company' : 'Platform'}
            </button>
          ))}
        </div>
      )}

      {/* Filter pills */}
      <div className="flex items-center gap-1 flex-wrap">
        {filters.map(({ key, label }) => {
          const count = key === 'all' ? items.length : items.filter(i => i.type === key).length;
          return (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`inline-flex items-center gap-1.5 px-2 py-1 text-[10px] font-bold font-mono uppercase tracking-wider rounded border transition-colors ${
                filter === key
                  ? 'bg-zinc-900 text-zinc-50 border-zinc-900'
                  : 'bg-stone-200 text-stone-500 border-stone-200 hover:text-zinc-900'
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

      {error && (
        <ErrorBanner
          message={error}
          onDismiss={() => isCompany ? setClientError(null) : setAdminError(null)}
        />
      )}

      {/* Empty state */}
      {filtered.length === 0 && !error && (
        <div className="bg-zinc-900 rounded-xl text-center py-12">
          <div className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center mx-auto mb-3">
            <Bell size={14} className="text-zinc-500" />
          </div>
          <p className="text-sm font-semibold text-zinc-100 mb-1">No notifications</p>
          <p className="text-xs text-zinc-400">
            {filter === 'all' ? "You're all caught up." : `No ${TYPE_LABEL[filter as AllTypes] ?? filter} activity.`}
          </p>
        </div>
      )}

      {/* Feed */}
      {groups.length > 0 && (
        <div className="space-y-4">
          {groups.map((group) => (
            <div key={group.label}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[9px] font-bold font-mono uppercase tracking-widest text-stone-400">
                  {group.label}
                </span>
                <div className="flex-1 h-px bg-stone-200" />
              </div>

              <div className="bg-zinc-900 rounded-xl overflow-hidden">
                {group.items.map((item, idx) => (
                  <div
                    key={item.id}
                    onClick={() => item.link && navigate(item.link)}
                    className={`group relative flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors hover:bg-zinc-800 ${
                      idx > 0 ? 'border-t border-zinc-800/60' : ''
                    }`}
                  >
                    <div className={`w-0.5 self-stretch shrink-0 ${TYPE_STRIP[item.type]}`} />

                    <div className="w-7 h-7 flex items-center justify-center shrink-0 rounded-lg bg-zinc-800">
                      <span className={TYPE_ICON_COLOR[item.type]}>{TYPE_ICONS[item.type]}</span>
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-[9px] font-bold font-mono uppercase tracking-widest text-zinc-500">
                          {TYPE_LABEL[item.type]}
                        </span>
                        {!isCompany && item.company_name && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] font-bold font-mono rounded-sm bg-zinc-800 text-zinc-400">
                            <Building2 size={9} className="text-zinc-500" />
                            {item.company_name}
                          </span>
                        )}
                      </div>
                      <div className="text-[12px] font-semibold leading-tight truncate text-zinc-100">
                        {item.title}
                      </div>
                      {item.subtitle && (
                        <div className="text-[11px] text-zinc-400 truncate mt-0.5">{item.subtitle}</div>
                      )}
                    </div>

                    {(item.severity || item.status) && (
                      <div className="flex items-center gap-1.5 shrink-0">
                        {item.severity && (
                          <span className="text-[9px] font-bold font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-zinc-800 text-zinc-300">
                            {item.severity}
                          </span>
                        )}
                        {item.status && (
                          <span className="text-[9px] font-bold font-mono uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-zinc-800 text-zinc-400">
                            {item.status.replace('_', ' ')}
                          </span>
                        )}
                      </div>
                    )}

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] font-mono tabular-nums text-zinc-400">
                        {relativeTime(item.created_at)}
                      </span>
                      {item.link && (
                        <ChevronRight size={12} className="text-zinc-500 opacity-0 group-hover:opacity-100" />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {hasMore && (
        <div className="flex justify-center pt-2">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="px-4 py-1.5 text-[10px] font-bold font-mono uppercase tracking-wider rounded border border-stone-300 text-stone-600 hover:border-stone-400 hover:text-zinc-900 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loadingMore ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  );
}

export default ClientNotifications;
