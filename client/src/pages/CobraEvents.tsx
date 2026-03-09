import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock,
  Mail,
  Plus,
  RefreshCw,
  Send,
  Shield,
  Users,
  X,
} from 'lucide-react';
import { cobra } from '../api/client';
import type {
  CobraEvent,
  CobraEventCreate,
  CobraEventType,
  CobraDashboard,
  CobraStatus,
} from '../types';
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-xl',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  statBg: 'bg-stone-200',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  select: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',
  rowBg: 'bg-stone-100',
  rowHover: 'hover:bg-stone-50',
  emptyBg: 'border border-dashed border-stone-200 bg-stone-100 rounded-2xl',
  tabActive: 'bg-zinc-900 border-zinc-900 text-zinc-50 rounded-xl',
  tabInactive: 'bg-transparent border-transparent text-stone-500 hover:text-zinc-900 hover:border-stone-300 rounded-xl',
  overdueCard: 'bg-red-50 border border-red-200 rounded-2xl',
  overdueText: 'text-red-700',
  overdueMuted: 'text-red-500',
  modalBg: 'bg-stone-100',
  modalBorder: 'border border-stone-300',
  checkboxBg: 'accent-zinc-900',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100 rounded-xl',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  statBg: 'bg-zinc-900',
  input: 'bg-zinc-800 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:border-white/20',
  select: 'bg-zinc-800 border border-white/10 rounded-xl text-zinc-100 focus:border-white/20',
  rowBg: 'bg-zinc-900',
  rowHover: 'hover:bg-white/5',
  emptyBg: 'border border-dashed border-white/10 bg-white/5 rounded-2xl',
  tabActive: 'bg-zinc-800 border-zinc-700 text-white rounded-xl',
  tabInactive: 'bg-transparent border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-800 rounded-xl',
  overdueCard: 'bg-red-500/10 border border-red-500/20 rounded-2xl',
  overdueText: 'text-red-300',
  overdueMuted: 'text-red-400/60',
  modalBg: 'bg-zinc-950',
  modalBorder: 'border border-zinc-800',
  checkboxBg: 'accent-zinc-400',
} as const;

// ─── constants ────────────────────────────────────────────────────────────────

const EVENT_TYPE_OPTIONS: CobraEventType[] = [
  'termination',
  'reduction_in_hours',
  'divorce',
  'dependent_aging_out',
  'medicare_enrollment',
  'employee_death',
];

const STATUS_OPTIONS: CobraStatus[] = [
  'pending_notice',
  'notice_sent',
  'election_pending',
  'elected',
  'waived',
  'expired',
  'terminated',
];

type TabKey = 'dashboard' | 'events' | 'overdue';

const TABS: { label: string; value: TabKey }[] = [
  { label: 'Dashboard', value: 'dashboard' },
  { label: 'Events', value: 'events' },
  { label: 'Overdue', value: 'overdue' },
];

// ─── helpers ──────────────────────────────────────────────────────────────────

function formatLabel(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function statusStyle(status: string, isLight: boolean): string {
  if (isLight) {
    switch (status) {
      case 'elected':
      case 'notice_sent':
        return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'expired':
      case 'terminated':
      case 'waived':
        return 'bg-stone-200 text-stone-600 border-stone-300';
      case 'pending_notice':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'election_pending':
        return 'bg-blue-100 text-blue-800 border-blue-200';
      default:
        return 'bg-stone-200 text-stone-600 border-stone-300';
    }
  }
  switch (status) {
    case 'elected':
    case 'notice_sent':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'expired':
    case 'terminated':
    case 'waived':
      return 'bg-zinc-600/20 text-zinc-300 border-zinc-600/30';
    case 'pending_notice':
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'election_pending':
      return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    default:
      return 'bg-zinc-600/20 text-zinc-300 border-zinc-600/30';
  }
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr);
  const now = new Date();
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function employeeName(event: CobraEvent): string {
  if (event.employee_first_name || event.employee_last_name) {
    return `${event.employee_first_name ?? ''} ${event.employee_last_name ?? ''}`.trim();
  }
  return event.employee_id;
}

// ─── component ────────────────────────────────────────────────────────────────

export default function CobraEvents() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  // ─── state ──────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');
  const [events, setEvents] = useState<CobraEvent[]>([]);
  const [overdueEvents, setOverdueEvents] = useState<CobraEvent[]>([]);
  const [dashboard, setDashboard] = useState<CobraDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // filters
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('');

  // create modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createPayload, setCreatePayload] = useState<CobraEventCreate>({
    employee_id: '',
    event_type: 'termination',
    event_date: '',
    beneficiary_count: 1,
    notes: '',
  });

  // detail/edit modal
  const [selectedEvent, setSelectedEvent] = useState<CobraEvent | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // ─── data fetching ──────────────────────────────────────────────────────────

  const loadDashboard = useCallback(async () => {
    try {
      const data = await cobra.getDashboard();
      setDashboard(data);
    } catch {
      // dashboard load failure is non-critical
    }
  }, []);

  const loadEvents = useCallback(
    async (silent = false) => {
      if (silent) setRefreshing(true);
      else setLoading(true);
      try {
        const params: { status?: string; overdue?: boolean } = {};
        if (statusFilter) params.status = statusFilter;
        const data = await cobra.listEvents(params);
        const filtered = eventTypeFilter
          ? data.filter((e) => e.event_type === eventTypeFilter)
          : data;
        setEvents(filtered);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load COBRA events');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [statusFilter, eventTypeFilter],
  );

  const loadOverdue = useCallback(async () => {
    try {
      const data = await cobra.getOverdue();
      setOverdueEvents(data);
    } catch {
      setOverdueEvents([]);
    }
  }, []);

  const loadAll = useCallback(
    async (silent = false) => {
      await Promise.all([loadEvents(silent), loadDashboard(), loadOverdue()]);
    },
    [loadEvents, loadDashboard, loadOverdue],
  );

  // Initial load — run once on mount
  const [initialized, setInitialized] = useState(false);
  useEffect(() => {
    if (!initialized) {
      setInitialized(true);
      loadAll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-fetch events when filters change (after initial load)
  useEffect(() => {
    if (initialized) {
      loadEvents();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, eventTypeFilter]);

  // clear success messages after 4 seconds
  useEffect(() => {
    if (!successMessage) return;
    const timer = setTimeout(() => setSuccessMessage(null), 4000);
    return () => clearTimeout(timer);
  }, [successMessage]);

  // ─── handlers ───────────────────────────────────────────────────────────────

  const handleCreate = async () => {
    if (!createPayload.employee_id.trim() || !createPayload.event_date) return;
    setSaving(true);
    setCreateError(null);
    try {
      const body: CobraEventCreate = {
        employee_id: createPayload.employee_id.trim(),
        event_type: createPayload.event_type,
        event_date: createPayload.event_date,
        beneficiary_count: createPayload.beneficiary_count || undefined,
        notes: createPayload.notes?.trim() || undefined,
      };
      await cobra.createEvent(body);
      setShowCreateModal(false);
      setCreatePayload({ employee_id: '', event_type: 'termination', event_date: '', beneficiary_count: 1, notes: '' });
      await loadAll(true);
      setSuccessMessage('COBRA qualifying event created.');
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create event');
    } finally {
      setSaving(false);
    }
  };

  const handleNoticeToggle = async (
    event: CobraEvent,
    field: 'employer_notice_sent' | 'administrator_notified' | 'election_received',
  ) => {
    const newValue = !event[field];
    const dateField = field === 'employer_notice_sent'
      ? 'employer_notice_sent_date'
      : field === 'administrator_notified'
        ? 'administrator_notified_date'
        : 'election_received_date';

    try {
      const updated = await cobra.updateEvent(event.id, {
        [field]: newValue,
        [dateField]: newValue ? new Date().toISOString().split('T')[0] : undefined,
      });
      // update in local state
      setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      setOverdueEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      if (selectedEvent?.id === updated.id) setSelectedEvent(updated);
      if (dashboard) loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update event');
    }
  };

  const handleStatusUpdate = async (event: CobraEvent, newStatus: CobraStatus) => {
    try {
      const updated = await cobra.updateEvent(event.id, { status: newStatus });
      setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      setOverdueEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      if (selectedEvent?.id === updated.id) setSelectedEvent(updated);
      setSuccessMessage('Status updated.');
      loadDashboard();
      loadOverdue();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update status');
    }
  };

  const handleNotesUpdate = async (event: CobraEvent, notes: string) => {
    try {
      const updated = await cobra.updateEvent(event.id, { notes });
      setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      if (selectedEvent?.id === updated.id) setSelectedEvent(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update notes');
    }
  };

  const handleMarkNoticeSent = async (event: CobraEvent) => {
    try {
      const updated = await cobra.updateEvent(event.id, {
        employer_notice_sent: true,
        employer_notice_sent_date: new Date().toISOString().split('T')[0],
        status: 'notice_sent',
      });
      setOverdueEvents((prev) => prev.filter((e) => e.id !== updated.id));
      setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      setSuccessMessage('Employer notice marked as sent.');
      loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update event');
    }
  };

  const openDetail = async (eventId: string) => {
    try {
      const detail = await cobra.getEvent(eventId);
      setSelectedEvent(detail);
      setShowDetailModal(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load event details');
    }
  };

  // ─── loading state ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className={`text-xs uppercase tracking-wider animate-pulse ${t.textMuted}`}>
          Loading COBRA events...
        </div>
      </div>
    );
  }

  // ─── render ─────────────────────────────────────────────────────────────────

  return (
    <div className={`max-w-7xl mx-auto space-y-6 ${t.pageBg} min-h-screen p-6`}>
      {/* header */}
      <div className={`flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 border-b ${t.border} pb-6`}>
        <div>
          <h1 className={`text-4xl font-bold tracking-tighter uppercase ${t.textMain}`}>COBRA Events</h1>
          <p className={`text-xs mt-2 font-mono tracking-wide uppercase ${t.textMuted}`}>
            Qualifying event tracking &amp; notice management
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => loadAll(true)}
            disabled={refreshing}
            className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider ${t.btnSecondary}`}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} /> Refresh
          </button>
          <button
            onClick={() => { setCreateError(null); setShowCreateModal(true); }}
            className={`inline-flex items-center gap-2 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary}`}
          >
            <Plus size={14} /> New Event
          </button>
        </div>
      </div>

      {/* tabs */}
      <div className="flex items-center gap-1">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`px-4 py-2 text-xs uppercase tracking-wider font-medium border transition-colors ${
              activeTab === tab.value ? t.tabActive : t.tabInactive
            }`}
          >
            {tab.label}
            {tab.value === 'overdue' && overdueEvents.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 text-[9px] bg-red-500 text-white rounded-full">
                {overdueEvents.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* alerts */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="text-red-400 shrink-0" size={16} />
          <p className="text-sm text-red-300">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-300">
            <X size={14} />
          </button>
        </div>
      )}
      {successMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 flex items-center gap-3">
          <CheckCircle2 className="text-emerald-400 shrink-0" size={16} />
          <p className="text-sm text-emerald-300">{successMessage}</p>
        </div>
      )}

      {/* ─── dashboard tab ───────────────────────────────────────────────────── */}
      {activeTab === 'dashboard' && (
        <div className="space-y-6">
          {/* stat cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className={`${t.card} p-5`}>
              <div className="flex items-center gap-3 mb-3">
                <div className={`p-2 rounded-xl ${t.statBg}`}>
                  <Mail size={18} className={t.textMuted} />
                </div>
                <p className={t.label}>Pending Notices</p>
              </div>
              <p className={`text-3xl font-bold tracking-tight ${t.textMain}`}>
                {dashboard?.pending_notices ?? 0}
              </p>
            </div>
            <div className={`${t.card} p-5`}>
              <div className="flex items-center gap-3 mb-3">
                <div className={`p-2 rounded-xl ${t.statBg}`}>
                  <AlertTriangle size={18} className="text-red-400" />
                </div>
                <p className={t.label}>Overdue</p>
              </div>
              <p className={`text-3xl font-bold tracking-tight ${dashboard?.overdue_count ? 'text-red-400' : t.textMain}`}>
                {dashboard?.overdue_count ?? 0}
              </p>
            </div>
            <div className={`${t.card} p-5`}>
              <div className="flex items-center gap-3 mb-3">
                <div className={`p-2 rounded-xl ${t.statBg}`}>
                  <Users size={18} className={t.textMuted} />
                </div>
                <p className={t.label}>Total Active</p>
              </div>
              <p className={`text-3xl font-bold tracking-tight ${t.textMain}`}>
                {dashboard?.total_active ?? 0}
              </p>
            </div>
          </div>

          {/* upcoming deadlines */}
          <div className={`${t.card} p-5`}>
            <div className="flex items-center gap-2 mb-4">
              <Clock size={16} className={t.textMuted} />
              <h3 className={`text-sm font-semibold uppercase tracking-wider ${t.textMain}`}>
                Upcoming Deadlines
              </h3>
            </div>
            {(!dashboard?.upcoming_deadlines || dashboard.upcoming_deadlines.length === 0) ? (
              <div className={`${t.emptyBg} p-8 text-center`}>
                <p className={`text-sm ${t.textMuted}`}>No upcoming deadlines within 30 days.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {dashboard.upcoming_deadlines.map((evt) => {
                  const days = daysUntil(evt.employer_notice_deadline);
                  const urgent = days <= 7;
                  return (
                    <button
                      key={evt.id}
                      onClick={() => openDetail(evt.id)}
                      className={`w-full text-left px-4 py-3 ${t.rowBg} ${t.rowHover} rounded-xl transition-colors flex items-center justify-between gap-4`}
                    >
                      <div className="min-w-0">
                        <p className={`text-sm font-medium ${t.textMain} truncate`}>
                          {employeeName(evt)}
                        </p>
                        <p className={`text-xs ${t.textMuted} mt-0.5`}>
                          {formatLabel(evt.event_type)}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className={`text-xs ${t.textMuted}`}>
                          {formatDate(evt.employer_notice_deadline)}
                        </p>
                        <p className={`text-xs font-medium mt-0.5 ${urgent ? 'text-red-400' : t.textFaint}`}>
                          {days <= 0 ? 'Today' : `${days} day${days === 1 ? '' : 's'} left`}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── events tab ──────────────────────────────────────────────────────── */}
      {activeTab === 'events' && (
        <div className="space-y-4">
          {/* filters */}
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className={`px-3 py-2 text-sm ${t.select}`}
            >
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{formatLabel(s)}</option>
              ))}
            </select>
            <select
              value={eventTypeFilter}
              onChange={(e) => setEventTypeFilter(e.target.value)}
              className={`px-3 py-2 text-sm ${t.select}`}
            >
              <option value="">All Event Types</option>
              {EVENT_TYPE_OPTIONS.map((et) => (
                <option key={et} value={et}>{formatLabel(et)}</option>
              ))}
            </select>
          </div>

          {/* table */}
          {events.length === 0 ? (
            <div className={`${t.emptyBg} p-10 text-center`}>
              <Shield size={24} className={`mx-auto mb-3 ${t.textFaint}`} />
              <p className={`text-sm ${t.textMuted}`}>No COBRA events found.</p>
            </div>
          ) : (
            <div className={`${t.card} overflow-hidden`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={`border-b ${t.border}`}>
                      <th className={`text-left px-4 py-3 ${t.label}`}>Employee</th>
                      <th className={`text-left px-4 py-3 ${t.label}`}>Event Type</th>
                      <th className={`text-left px-4 py-3 ${t.label}`}>Event Date</th>
                      <th className={`text-left px-4 py-3 ${t.label}`}>Status</th>
                      <th className={`text-left px-4 py-3 ${t.label}`}>Notice Deadline</th>
                      <th className={`text-left px-4 py-3 ${t.label}`}>Election Deadline</th>
                    </tr>
                  </thead>
                  <tbody className={`divide-y ${t.border}`}>
                    {events.map((evt) => (
                      <tr
                        key={evt.id}
                        onClick={() => openDetail(evt.id)}
                        className={`${t.rowHover} cursor-pointer transition-colors`}
                      >
                        <td className={`px-4 py-3 font-medium ${t.textMain}`}>
                          {employeeName(evt)}
                        </td>
                        <td className={`px-4 py-3 ${t.textMuted}`}>
                          {formatLabel(evt.event_type)}
                        </td>
                        <td className={`px-4 py-3 ${t.textMuted}`}>
                          {formatDate(evt.event_date)}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border ${statusStyle(evt.status, isLight)}`}>
                            {formatLabel(evt.status)}
                          </span>
                        </td>
                        <td className={`px-4 py-3 ${t.textMuted}`}>
                          {formatDate(evt.employer_notice_deadline)}
                        </td>
                        <td className={`px-4 py-3 ${t.textMuted}`}>
                          {formatDate(evt.election_deadline)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── overdue tab ─────────────────────────────────────────────────────── */}
      {activeTab === 'overdue' && (
        <div className="space-y-4">
          {overdueEvents.length === 0 ? (
            <div className={`${t.emptyBg} p-10 text-center`}>
              <CheckCircle2 size={24} className={`mx-auto mb-3 ${t.textFaint}`} />
              <p className={`text-sm ${t.textMuted}`}>No overdue events. All notices are current.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {overdueEvents.map((evt) => (
                <div key={evt.id} className={`${t.overdueCard} p-5`}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <AlertTriangle size={14} className="text-red-400 shrink-0" />
                        <p className={`text-sm font-semibold ${t.overdueText}`}>
                          {employeeName(evt)}
                        </p>
                      </div>
                      <p className={`text-xs ${t.overdueMuted} mb-2`}>
                        {formatLabel(evt.event_type)}
                      </p>
                      <div className="flex flex-wrap gap-x-6 gap-y-1">
                        <div>
                          <span className={`text-[10px] uppercase tracking-wider ${t.overdueMuted}`}>
                            Notice Deadline
                          </span>
                          <p className={`text-xs font-medium ${t.overdueText}`}>
                            {formatDate(evt.employer_notice_deadline)}
                          </p>
                        </div>
                        <div>
                          <span className={`text-[10px] uppercase tracking-wider ${t.overdueMuted}`}>
                            Days Overdue
                          </span>
                          <p className="text-xs font-bold text-red-400">
                            {evt.days_overdue ?? Math.abs(daysUntil(evt.employer_notice_deadline))}
                          </p>
                        </div>
                        <div>
                          <span className={`text-[10px] uppercase tracking-wider ${t.overdueMuted}`}>
                            Beneficiaries
                          </span>
                          <p className={`text-xs ${t.overdueText}`}>{evt.beneficiary_count}</p>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleMarkNoticeSent(evt)}
                      className="inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider bg-red-500 text-white hover:bg-red-600 rounded-xl shrink-0"
                    >
                      <Send size={12} /> Mark Sent
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ─── create modal ────────────────────────────────────────────────────── */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center">
          <div className={`w-full max-w-lg ${t.modalBg} ${t.modalBorder} rounded-xl`}>
            <div className={`flex items-center justify-between p-5 border-b ${t.border}`}>
              <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                New COBRA Qualifying Event
              </h3>
              <button onClick={() => setShowCreateModal(false)} className={t.btnGhost}>
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className={`block mb-1 ${t.label}`}>Employee ID</label>
                <input
                  value={createPayload.employee_id}
                  onChange={(e) => setCreatePayload((prev) => ({ ...prev, employee_id: e.target.value }))}
                  placeholder="Enter employee ID"
                  className={`w-full px-3 py-2 ${t.input}`}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className={`block mb-1 ${t.label}`}>Event Type</label>
                  <select
                    value={createPayload.event_type}
                    onChange={(e) => setCreatePayload((prev) => ({ ...prev, event_type: e.target.value as CobraEventType }))}
                    className={`w-full px-3 py-2 ${t.select}`}
                  >
                    {EVENT_TYPE_OPTIONS.map((et) => (
                      <option key={et} value={et}>{formatLabel(et)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={`block mb-1 ${t.label}`}>Event Date</label>
                  <input
                    type="date"
                    value={createPayload.event_date}
                    onChange={(e) => setCreatePayload((prev) => ({ ...prev, event_date: e.target.value }))}
                    className={`w-full px-3 py-2 ${t.input}`}
                  />
                </div>
              </div>
              <div>
                <label className={`block mb-1 ${t.label}`}>Beneficiary Count</label>
                <input
                  type="number"
                  min={1}
                  value={createPayload.beneficiary_count ?? 1}
                  onChange={(e) => setCreatePayload((prev) => ({ ...prev, beneficiary_count: parseInt(e.target.value) || 1 }))}
                  className={`w-full px-3 py-2 ${t.input}`}
                />
              </div>
              <div>
                <label className={`block mb-1 ${t.label}`}>Notes (optional)</label>
                <textarea
                  rows={3}
                  value={createPayload.notes ?? ''}
                  onChange={(e) => setCreatePayload((prev) => ({ ...prev, notes: e.target.value }))}
                  placeholder="Additional context..."
                  className={`w-full px-3 py-2 resize-none ${t.input}`}
                />
              </div>
            </div>
            <div className={`p-5 border-t ${t.border} flex justify-end gap-2`}>
              <button
                onClick={() => { setCreateError(null); setShowCreateModal(false); }}
                className={`px-3 py-2 text-xs uppercase tracking-wider ${t.btnGhost}`}
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={saving || !createPayload.employee_id.trim() || !createPayload.event_date}
                className={`px-3 py-2 text-xs uppercase tracking-wider disabled:opacity-50 ${t.btnPrimary}`}
              >
                {saving ? 'Creating...' : 'Create Event'}
              </button>
            </div>
            {createError && (
              <div className="px-5 pb-5">
                <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-xs px-3 py-2 rounded-xl">
                  {createError}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── detail / edit modal ─────────────────────────────────────────────── */}
      {showDetailModal && selectedEvent && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center">
          <div className={`w-full max-w-2xl max-h-[90vh] overflow-y-auto ${t.modalBg} ${t.modalBorder} rounded-xl`}>
            <div className={`flex items-center justify-between p-5 border-b ${t.border} sticky top-0 ${t.modalBg} z-10`}>
              <div>
                <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>
                  Event Details
                </h3>
                <p className={`text-xs mt-0.5 ${t.textMuted}`}>{selectedEvent.id}</p>
              </div>
              <button onClick={() => setShowDetailModal(false)} className={t.btnGhost}>
                <X size={18} />
              </button>
            </div>
            <div className="p-5 space-y-5">
              {/* summary */}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={`text-xl font-semibold ${t.textMain}`}>{employeeName(selectedEvent)}</p>
                  {selectedEvent.employee_email && (
                    <p className={`text-xs ${t.textMuted} mt-0.5`}>{selectedEvent.employee_email}</p>
                  )}
                </div>
                <span className={`text-[10px] px-2 py-1 uppercase tracking-widest border ${statusStyle(selectedEvent.status, isLight)}`}>
                  {formatLabel(selectedEvent.status)}
                </span>
              </div>

              {/* info grid */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <p className={t.label}>Event Type</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{formatLabel(selectedEvent.event_type)}</p>
                </div>
                <div>
                  <p className={t.label}>Event Date</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{formatDate(selectedEvent.event_date)}</p>
                </div>
                <div>
                  <p className={t.label}>Beneficiaries</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{selectedEvent.beneficiary_count}</p>
                </div>
                <div>
                  <p className={t.label}>Employer Notice Deadline</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{formatDate(selectedEvent.employer_notice_deadline)}</p>
                </div>
                <div>
                  <p className={t.label}>Admin Notice Deadline</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{formatDate(selectedEvent.administrator_notice_deadline)}</p>
                </div>
                <div>
                  <p className={t.label}>Election Deadline</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{formatDate(selectedEvent.election_deadline)}</p>
                </div>
                <div>
                  <p className={t.label}>Continuation Months</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{selectedEvent.continuation_months}</p>
                </div>
                <div>
                  <p className={t.label}>Continuation End</p>
                  <p className={`text-sm mt-1 ${t.textMain}`}>{formatDate(selectedEvent.continuation_end_date)}</p>
                </div>
              </div>

              {/* status update */}
              <div>
                <p className={`mb-1 ${t.label}`}>Update Status</p>
                <select
                  value={selectedEvent.status}
                  onChange={(e) => handleStatusUpdate(selectedEvent, e.target.value as CobraStatus)}
                  className={`w-full px-3 py-2 ${t.select}`}
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>{formatLabel(s)}</option>
                  ))}
                </select>
              </div>

              {/* notice tracking checkboxes */}
              <div className={`${t.card} p-4 space-y-3`}>
                <p className={`${t.label} mb-2`}>Notice Tracking</p>
                <label className={`flex items-center gap-3 cursor-pointer ${t.textMain}`}>
                  <input
                    type="checkbox"
                    checked={selectedEvent.employer_notice_sent}
                    onChange={() => handleNoticeToggle(selectedEvent, 'employer_notice_sent')}
                    className={`w-4 h-4 rounded ${t.checkboxBg}`}
                  />
                  <div>
                    <span className="text-sm">Employer Notice Sent</span>
                    {selectedEvent.employer_notice_sent_date && (
                      <span className={`text-xs ml-2 ${t.textMuted}`}>
                        ({formatDate(selectedEvent.employer_notice_sent_date)})
                      </span>
                    )}
                  </div>
                </label>
                <label className={`flex items-center gap-3 cursor-pointer ${t.textMain}`}>
                  <input
                    type="checkbox"
                    checked={selectedEvent.administrator_notified}
                    onChange={() => handleNoticeToggle(selectedEvent, 'administrator_notified')}
                    className={`w-4 h-4 rounded ${t.checkboxBg}`}
                  />
                  <div>
                    <span className="text-sm">Administrator Notified</span>
                    {selectedEvent.administrator_notified_date && (
                      <span className={`text-xs ml-2 ${t.textMuted}`}>
                        ({formatDate(selectedEvent.administrator_notified_date)})
                      </span>
                    )}
                  </div>
                </label>
                <label className={`flex items-center gap-3 cursor-pointer ${t.textMain}`}>
                  <input
                    type="checkbox"
                    checked={selectedEvent.election_received}
                    onChange={() => handleNoticeToggle(selectedEvent, 'election_received')}
                    className={`w-4 h-4 rounded ${t.checkboxBg}`}
                  />
                  <div>
                    <span className="text-sm">Election Received</span>
                    {selectedEvent.election_received_date && (
                      <span className={`text-xs ml-2 ${t.textMuted}`}>
                        ({formatDate(selectedEvent.election_received_date)})
                      </span>
                    )}
                  </div>
                </label>
              </div>

              {/* notes */}
              <div>
                <p className={`mb-1 ${t.label}`}>Notes</p>
                <textarea
                  rows={3}
                  key={selectedEvent.id}
                  defaultValue={selectedEvent.notes ?? ''}
                  onBlur={(e) => {
                    if (e.target.value !== (selectedEvent.notes ?? '')) {
                      handleNotesUpdate(selectedEvent, e.target.value);
                    }
                  }}
                  placeholder="Add notes..."
                  className={`w-full px-3 py-2 resize-none ${t.input}`}
                />
              </div>

              {/* metadata */}
              <div className={`flex flex-wrap gap-x-6 gap-y-1 pt-2 border-t ${t.border}`}>
                <div>
                  <span className={t.label}>Created</span>
                  <p className={`text-xs ${t.textMuted}`}>{formatDate(selectedEvent.created_at)}</p>
                </div>
                <div>
                  <span className={t.label}>Updated</span>
                  <p className={`text-xs ${t.textMuted}`}>{formatDate(selectedEvent.updated_at)}</p>
                </div>
                {selectedEvent.offboarding_case_id && (
                  <div>
                    <span className={t.label}>Offboarding Case</span>
                    <p className={`text-xs ${t.textMuted}`}>{selectedEvent.offboarding_case_id}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
