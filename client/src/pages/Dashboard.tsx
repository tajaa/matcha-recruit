import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Users, FileText, CheckCircle2, Clock, Activity, ShieldAlert, Calendar, Building, UserPlus, LayoutDashboard, History, AlertTriangle, MapPin, ChevronRight, TriangleAlert, X, ExternalLink, Sparkles, Circle, Check, Pin } from 'lucide-react';
import { useIsLightMode } from '../hooks/useIsLightMode';
import { getAccessToken, credentialExpirations } from '../api/client';
import type { CredentialExpiration, CredentialExpirationSummary } from '../api/client';
import { OnboardingWizard } from '../components/OnboardingWizard';
import { Collapsible } from '../components/Collapsible';
import { Tabs } from '../components/Tabs';
import { WidgetContainer } from '../components/WidgetContainer';
import { complianceAPI, COMPLIANCE_CATEGORY_LABELS } from '../api/compliance';
import type { ComplianceDashboard, ComplianceDashboardItem, ComplianceActionPlanUpdate, AssignableUser, PinnedRequirement } from '../api/compliance';
import { useAuth } from '../context/AuthContext';
import type { ClientProfile } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

// ─── theme ────────────────────────────────────────────────────────────────────

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
  kpiGap: 'bg-stone-300',
  kpiCell: 'bg-stone-200',
  kpiValActive: 'text-zinc-900',
  kpiValEmpty: 'text-stone-400',
  kpiLabelCls: 'text-stone-500',
  horizonActive: 'bg-zinc-900 text-zinc-50',
  horizonInactive: 'bg-stone-200 text-stone-500 hover:text-zinc-900',
  spinner: 'border-stone-300 border-t-zinc-900',
  modalBg: 'bg-stone-100 rounded-lg',
  descBox: 'bg-stone-200 rounded-lg',
  selectCls: 'bg-white border border-stone-300 rounded-lg text-zinc-900 text-xs px-3 py-2 focus:outline-none focus:border-stone-400',
  pillActive: 'bg-zinc-900 text-zinc-50',
  pillInactive: 'bg-stone-200 text-stone-500 hover:text-zinc-900',
  sevDot: { critical: 'bg-zinc-900 animate-pulse', warning: 'bg-stone-400', info: 'bg-stone-300' },
  sevBadge: { critical: 'bg-stone-200 text-zinc-900 rounded-full', warning: 'bg-stone-200 text-stone-600 rounded-full', info: 'bg-stone-200 text-stone-500 rounded-full' },
  sla: {
    overdue:    { badge: 'bg-stone-200 text-zinc-900 rounded-full',  due: 'text-zinc-900' },
    due_soon:   { badge: 'bg-stone-200 text-stone-600 rounded-full', due: 'text-stone-600' },
    completed:  { badge: 'bg-stone-100 text-stone-400 rounded-full', due: 'text-stone-400' },
    unassigned: { badge: 'bg-stone-100 text-stone-400 rounded-full', due: 'text-stone-400' },
    on_track:   { badge: 'bg-stone-100 text-stone-400 rounded-full', due: 'text-stone-400' },
  },
  daysColor: (d: number | null | undefined) =>
    d != null && d <= 30 ? 'text-zinc-900 font-semibold' : d != null && d <= 60 ? 'text-stone-600' : 'text-stone-400',
  cardDark: 'bg-zinc-900 rounded-xl',
  cardDarkHover: 'hover:bg-zinc-800',
  cardDarkGhost: 'text-zinc-800',
  cardDarkTrack: 'text-zinc-800',
  cardDarkTrackBg: 'bg-zinc-800',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900',
  livePill: 'bg-stone-200 text-stone-600',
  dateBadge: 'bg-stone-200 text-stone-500',
  recentBadge: 'bg-stone-200 text-stone-600',
  innerBg: 'bg-stone-300 rounded-md',
  footerLink: 'text-stone-500 hover:text-zinc-900',
  activityDot: { success: 'bg-zinc-900', warning: 'bg-stone-400 animate-pulse', def: 'bg-stone-300' },
  incidentSev: [
    { text: 'text-zinc-900', dot: 'bg-zinc-900' },
    { text: 'text-stone-700', dot: 'bg-stone-700' },
    { text: 'text-stone-500', dot: 'bg-stone-500' },
    { text: 'text-stone-400', dot: 'bg-stone-400' },
  ],
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
  kpiGap: 'bg-zinc-950',
  kpiCell: 'bg-zinc-900',
  kpiValActive: 'text-zinc-100',
  kpiValEmpty: 'text-zinc-600',
  kpiLabelCls: 'text-zinc-500',
  horizonActive: 'bg-zinc-700 text-zinc-100',
  horizonInactive: 'bg-zinc-800 text-zinc-500 hover:text-zinc-100',
  spinner: 'border-zinc-800 border-t-zinc-100',
  modalBg: 'bg-zinc-900 border border-white/10 rounded-lg',
  descBox: 'bg-zinc-800 rounded-lg',
  selectCls: 'bg-zinc-800 border border-white/10 rounded-lg text-zinc-100 text-xs px-3 py-2 focus:outline-none focus:border-white/20',
  pillActive: 'bg-zinc-700 text-zinc-100',
  pillInactive: 'bg-zinc-800 text-zinc-500 hover:text-zinc-100',
  sevDot: { critical: 'bg-zinc-100 animate-pulse', warning: 'bg-zinc-400', info: 'bg-zinc-600' },
  sevBadge: { critical: 'bg-zinc-800 text-zinc-100 rounded-full', warning: 'bg-zinc-800 text-zinc-400 rounded-full', info: 'bg-zinc-800 text-zinc-600 rounded-full' },
  sla: {
    overdue:    { badge: 'bg-zinc-800 text-zinc-100 rounded-full',  due: 'text-zinc-100' },
    due_soon:   { badge: 'bg-zinc-800 text-zinc-400 rounded-full',  due: 'text-zinc-400' },
    completed:  { badge: 'bg-zinc-800 text-zinc-600 rounded-full',  due: 'text-zinc-600' },
    unassigned: { badge: 'bg-zinc-800 text-zinc-600 rounded-full',  due: 'text-zinc-600' },
    on_track:   { badge: 'bg-zinc-800 text-zinc-600 rounded-full',  due: 'text-zinc-600' },
  },
  daysColor: (d: number | null | undefined) =>
    d != null && d <= 30 ? 'text-zinc-100 font-semibold' : d != null && d <= 60 ? 'text-zinc-400' : 'text-zinc-600',
  cardDark: 'bg-zinc-800 rounded-xl',
  cardDarkHover: 'hover:bg-zinc-700',
  cardDarkGhost: 'text-zinc-700',
  cardDarkTrack: 'text-zinc-700',
  cardDarkTrackBg: 'bg-zinc-700',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100',
  livePill: 'bg-zinc-800 text-zinc-400',
  dateBadge: 'bg-zinc-800 text-zinc-500',
  recentBadge: 'bg-zinc-800 text-zinc-400',
  innerBg: 'bg-zinc-700 rounded-md',
  footerLink: 'text-zinc-500 hover:text-zinc-100',
  activityDot: { success: 'bg-zinc-100', warning: 'bg-zinc-400 animate-pulse', def: 'bg-zinc-600' },
  incidentSev: [
    { text: 'text-zinc-100', dot: 'bg-zinc-100' },
    { text: 'text-zinc-400', dot: 'bg-zinc-400' },
    { text: 'text-zinc-500', dot: 'bg-zinc-500' },
    { text: 'text-zinc-600', dot: 'bg-zinc-600' },
  ],
} as const;

interface PTOSummary {
  pending_count: number;
  upcoming_time_off: number;
}

interface PendingIncident {
  id: string;
  incident_number: string;
  title: string;
  severity: string;
}

interface ActivityItem {
  action: string;
  timestamp: string;
  type: string;
}

interface IncidentSummary {
  total_open: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  recent_7_days: number;
}

interface WageAlertSummary {
  hourly_violations: number;
  salary_violations: number;
  locations_affected: number;
}

interface ERCaseSummary {
  open_cases: number;
  investigating: number;
  pending_action: number;
}

interface StalePolicySummary {
  stale_count: number;
  oldest_days: number;
}

interface DashboardStats {
  active_policies: number;
  pending_signatures: number;
  total_employees: number;
  compliance_rate: number;
  pending_incidents: PendingIncident[];
  recent_activity: ActivityItem[];
  incident_summary?: IncidentSummary;
  wage_alerts?: WageAlertSummary;
  critical_compliance_alerts: number;
  warning_compliance_alerts: number;
  er_case_summary?: ERCaseSummary;
  stale_policies?: StalePolicySummary;
}

type HorizonDays = 30 | 60 | 90;

const SEVERITY_LABELS: Record<string, string> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
};

const TURNAROUND_OPTIONS = [
  { label: '1 day', days: 1 },
  { label: '2 days', days: 2 },
  { label: '3 days', days: 3 },
  { label: '5 days', days: 5 },
  { label: '1 week', days: 7 },
  { label: '2 weeks', days: 14 },
];

const PROFILE_DISMISS_KEY = 'company_profile_banner_dismissed';

/** Key fields that indicate the profile is "complete enough" for AI context. */
const PROFILE_CHECK_FIELDS = ['headquarters_state', 'benefits_summary', 'default_employment_type'] as const;

function CompanyProfileBanner() {
  const navigate = useNavigate();
  const { profile, user } = useAuth();
  const t = useIsLightMode() ? LT : DK;
  const clientProfile = profile as ClientProfile | null;
  const companyId = clientProfile?.company_id;

  const [visible, setVisible] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!companyId || user?.role === 'admin') {
      setChecked(true);
      return;
    }

    // Don't show if previously dismissed
    const dismissed = localStorage.getItem(PROFILE_DISMISS_KEY);
    if (dismissed === companyId) {
      setChecked(true);
      return;
    }

    // Fetch company and check for missing profile fields
    const token = getAccessToken();
    fetch(`${API_BASE}/companies/${companyId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        const missing = PROFILE_CHECK_FIELDS.filter((f) => !data[f]);
        if (missing.length > 0) {
          setVisible(true);
        }
      })
      .catch(() => {})
      .finally(() => setChecked(true));
  }, [companyId, user?.role]);

  if (!checked || !visible) return null;

  const dismiss = () => {
    if (companyId) localStorage.setItem(PROFILE_DISMISS_KEY, companyId);
    setVisible(false);
  };

  return (
    <div className={`relative ${t.cardLight} p-5 mb-4 animate-in fade-in slide-in-from-top-2 duration-500`}>
      <button
        onClick={dismiss}
        className={`absolute top-4 right-4 ${t.icon} hover:${t.textMain} transition-colors`}
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
      <div className="flex items-start gap-3">
        <div className={`p-2 ${t.innerEl} shrink-0`}>
          <Sparkles className={`w-5 h-5 ${t.textMain}`} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className={`text-base font-medium ${t.textMain} mb-0.5`}>Complete your company profile</h3>
          <p className={`text-xs ${t.textMuted} leading-relaxed mb-2.5`}>
            Add your headquarters location, benefits, and employment defaults so the AI can pre-fill offer letters,
            give jurisdiction-aware guidance, and generate better documents without extra questions.
          </p>
          <button
            onClick={() => { dismiss(); navigate('/app/matcha/company'); }}
            className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 ${t.btnPrimary} rounded-lg text-[11px] font-bold transition-colors`}
          >
            Set Up Profile
            <ChevronRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

const getGettingStartedDismissKey = (userId: string) => `getting_started_dismissed_${userId}`;

const CHECKLIST_ITEMS = [
  { key: 'company_profile', label: 'Complete company profile', path: '/app/matcha/company', featureGate: null },
  { key: 'compliance', label: 'Add business locations', path: '/app/matcha/compliance', featureGate: 'compliance' },
  { key: 'employees', label: 'Add your first employee', path: '/app/matcha/employees', featureGate: 'employees' },
  { key: 'policies', label: 'Create a policy', path: '/app/matcha/policies/new', featureGate: 'policies' },
  { key: 'offer_letters', label: 'Create an offer letter', path: '/app/matcha/offer-letters', featureGate: 'offer_letters' },
  { key: 'integrations', label: 'Set up integrations', path: '/app/matcha/setup', featureGate: 'onboarding' },
] as const;

function GettingStartedChecklist() {
  const navigate = useNavigate();
  const { user, hasFeature, onboardingNeeded } = useAuth();
  const t = useIsLightMode() ? LT : DK;
  const dismissKey = user?.id ? getGettingStartedDismissKey(user.id) : null;
  const [dismissed, setDismissed] = useState(() =>
    dismissKey ? localStorage.getItem(dismissKey) === 'true' : false
  );

  if (user?.role !== 'client' || dismissed) return null;

  const visibleItems = CHECKLIST_ITEMS.filter(
    item => !item.featureGate || hasFeature(item.featureGate)
  );

  const completedCount = visibleItems.filter(item => !onboardingNeeded[item.key]).length;
  const totalCount = visibleItems.length;

  if (totalCount === 0 || completedCount === totalCount) return null;

  const pct = Math.round((completedCount / totalCount) * 100);

  return (
    <div className={`${t.cardLight} p-5 mb-4 animate-in fade-in slide-in-from-top-2 duration-500`}>
      <div className="flex items-center justify-between mb-3.5">
        <div>
          <h2 className={`text-sm font-semibold ${t.textMain}`}>Getting Started</h2>
          <p className={`text-[10px] ${t.textMuted} mt-0.5`}>{completedCount} of {totalCount} complete</p>
        </div>
        <button
          onClick={() => { if (dismissKey) localStorage.setItem(dismissKey, 'true'); setDismissed(true); }}
          className={`${t.icon} hover:${t.textMain} transition-colors`}
          aria-label="Dismiss checklist"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Progress bar */}
      <div className={`h-1 ${t.innerEl} mb-3.5 overflow-hidden`}>
        <div
          className="h-full bg-emerald-500 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="space-y-0.5">
        {visibleItems.map(item => {
          const done = !onboardingNeeded[item.key];
          return (
            <button
              key={item.key}
              onClick={() => !done && navigate(item.path)}
              disabled={done}
              className={`w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-left transition-colors ${
                done ? 'opacity-60 cursor-default' : `${t.rowHover} cursor-pointer`
              }`}
            >
              {done ? (
                <Check className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
              ) : (
                <Circle className={`w-3.5 h-3.5 ${t.textFaint} flex-shrink-0`} />
              )}
              <span className={`text-[11px] font-medium flex-1 ${done ? `line-through ${t.textMuted}` : t.textMain}`}>
                {item.label}
              </span>
              {!done && <ChevronRight className={`w-3 h-3 ${t.textFaint}`} />}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function PinnedComplianceWidget() {
  const navigate = useNavigate();
  const t = useIsLightMode() ? LT : DK;
  const [items, setItems] = useState<PinnedRequirement[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    complianceAPI.getPinnedRequirements()
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const unpin = (id: string) => {
    complianceAPI.pinRequirement(id, false)
      .then(() => load())
      .catch(() => {});
  };

  const categoryLabel = (cat: string) => COMPLIANCE_CATEGORY_LABELS[cat] ?? cat.replace(/_/g, ' ');
  const levelLabel = (lv: string) => ({ federal: 'Federal', state: 'State', county: 'County', city: 'City' }[lv] ?? lv);

  return (
    <div className={`${t.cardLight} overflow-hidden`}>
      <div className={`p-4 border-b ${t.border} flex justify-between items-center`}>
        <div className={t.label}>Pinned Compliance</div>
        <Pin className={`w-4 h-4 ${t.icon}`} />
      </div>
      <div className="p-4">
        {loading ? (
          <div className="flex justify-center py-6">
            <div className={`w-5 h-5 border-2 rounded-full animate-spin ${t.spinner}`} />
          </div>
        ) : items.length === 0 ? (
          <p className={`text-xs ${t.textMuted} text-center py-6`}>No pinned requirements — pin items from the Compliance page</p>
        ) : (
          <div className="space-y-3">
            {items.map(item => (
              <div key={item.id} className={`${t.innerEl} p-3`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className={`text-xs font-medium ${t.textMain} truncate`}>{item.title}</p>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <span className={`text-[9px] px-1.5 py-0.5 rounded ${t.innerHover} ${t.textMuted} font-mono uppercase tracking-wider`}>
                        {categoryLabel(item.category)}
                      </span>
                      <span className={`text-[9px] px-1.5 py-0.5 rounded ${t.innerHover} ${t.textMuted} font-mono uppercase tracking-wider`}>
                        {levelLabel(item.jurisdiction_level)}
                      </span>
                    </div>
                    {item.current_value && (
                      <p className={`text-[10px] font-mono mt-1.5 ${t.textDim}`}>{item.current_value}</p>
                    )}
                    <p className={`text-[9px] mt-1 ${t.textFaint}`}>
                      {item.location_name || `${item.city}, ${item.state}`}
                    </p>
                  </div>
                  <button
                    onClick={() => unpin(item.id)}
                    title="Unpin from dashboard"
                    className="text-amber-500 hover:text-amber-400 transition-colors shrink-0 mt-0.5"
                  >
                    <Pin size={12} className="fill-amber-500" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className={`px-4 py-3 ${t.footerBg}`}>
        <button onClick={() => navigate('/app/matcha/compliance')} className={`text-[10px] ${t.footerLink} font-medium uppercase tracking-wider`}>
          View all compliance →
        </button>
      </div>
    </div>
  );
}

function ComplianceDashboardWidget() {
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();
  const t = useIsLightMode() ? LT : DK;
  const [horizon, setHorizon] = useState<HorizonDays>(90);
  const [data, setData] = useState<ComplianceDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Modal state
  const [selectedItem, setSelectedItem] = useState<ComplianceDashboardItem | null>(null);
  const [assignableUsers, setAssignableUsers] = useState<AssignableUser[]>([]);
  const [modalOwnerId, setModalOwnerId] = useState<string>('');
  const [modalTurnaround, setModalTurnaround] = useState<number | null>(null);
  const [modalSaving, setModalSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const loadDashboard = (windowDays: HorizonDays) => {
    setLoading(true);
    setError(false);
    complianceAPI.getDashboard(windowDays)
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadDashboard(horizon);
  }, [horizon]);

  const handleItemClick = (item: ComplianceDashboardItem) => {
    setSelectedItem(item);
    setModalOwnerId(item.action_owner_id ?? '');
    setModalTurnaround(null);
    setModalError(null);
    if (assignableUsers.length === 0) {
      complianceAPI.getAssignableUsers()
        .then(setAssignableUsers)
        .catch(() => {/* non-fatal */});
    }
  };

  const closeModal = () => {
    setSelectedItem(null);
    setModalError(null);
  };

  const ensureAlertId = async (item: ComplianceDashboardItem): Promise<string> => {
    if (item.alert_id) return item.alert_id;
    const result = await complianceAPI.assignLegislation(item.legislation_id, {
      location_id: item.location_id,
    });
    setSelectedItem(prev => prev ? { ...prev, alert_id: result.alert_id } : prev);
    return result.alert_id;
  };

  const saveModalChanges = async () => {
    if (!selectedItem) return;
    setModalSaving(true);
    setModalError(null);
    try {
      const ownerChanged = modalOwnerId !== (selectedItem.action_owner_id ?? '');
      const hasTurnaround = modalTurnaround !== null;

      if (!selectedItem.alert_id) {
        const dueDate = hasTurnaround ? (() => {
          const d = new Date();
          d.setDate(d.getDate() + modalTurnaround!);
          return d.toISOString().slice(0, 10);
        })() : undefined;
        await complianceAPI.assignLegislation(selectedItem.legislation_id, {
          location_id: selectedItem.location_id,
          action_owner_id: modalOwnerId || undefined,
          action_due_date: dueDate,
        });
      } else {
        const payload: ComplianceActionPlanUpdate = {};
        if (ownerChanged) payload.action_owner_id = modalOwnerId || null;
        if (hasTurnaround) {
          const due = new Date();
          due.setDate(due.getDate() + modalTurnaround!);
          payload.action_due_date = due.toISOString().slice(0, 10);
        }
        if (Object.keys(payload).length > 0) {
          await complianceAPI.updateAlertActionPlan(selectedItem.alert_id, payload);
        }
      }
      loadDashboard(horizon);
      closeModal();
    } catch {
      setModalError('Could not save changes');
    } finally {
      setModalSaving(false);
    }
  };

  const markActioned = async (item: ComplianceDashboardItem) => {
    setModalSaving(true);
    setModalError(null);
    try {
      const alertId = await ensureAlertId(item);
      await complianceAPI.updateAlertActionPlan(alertId, { mark_actioned: true });
      loadDashboard(horizon);
      closeModal();
    } catch {
      setModalError('Could not mark as actioned');
    } finally {
      setModalSaving(false);
    }
  };

  const formatDateLabel = (isoDate: string | null): string => {
    if (!isoDate) return 'No due date';
    const parsed = new Date(`${isoDate}T00:00:00`);
    if (Number.isNaN(parsed.getTime())) return isoDate;
    return parsed.toLocaleDateString();
  };

  const getSlaStyle = (slaState: ComplianceDashboardItem['sla_state']) => {
    const labels: Record<string, string> = { overdue: 'Overdue', due_soon: 'Due Soon', completed: 'Completed', unassigned: 'Unassigned', on_track: 'On Track' };
    const s = t.sla[slaState] ?? t.sla.on_track;
    return { label: labels[slaState] ?? 'On Track', badge: s.badge, dueText: s.due };
  };

  const criticalCount = data?.coming_up.filter(i => i.severity === 'critical').length ?? 0;
  const warningCount = data?.coming_up.filter(i => i.severity === 'warning').length ?? 0;

  return (
    <div className={`${t.cardLight} overflow-hidden`}>
      {/* Header */}
      <div className={`p-4 ${t.border} border-b flex items-center justify-between`}>
        <div className="flex items-center gap-2.5">
          <ShieldAlert className={`w-4 h-4 ${t.icon}`} />
          <div className={t.label}>Compliance Impact</div>
          {criticalCount > 0 && (
            <span className={`px-2 py-0.5 text-[10px] font-bold ${t.sevBadge.critical}`}>
              {criticalCount} critical
            </span>
          )}
        </div>
        <div className="flex gap-1.5">
          {([30, 60, 90] as HorizonDays[]).map(d => (
            <button
              key={d}
              onClick={() => setHorizon(d)}
              className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                horizon === d ? t.horizonActive : t.horizonInactive
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* KPI row */}
      {data && (
        <div className={`grid grid-cols-3 md:grid-cols-7 gap-px ${t.kpiGap} ${t.border} border-b`}>
          {[
            { label: 'Locations', value: data.kpis.total_locations },
            { label: 'Unread Alerts', value: data.kpis.unread_alerts },
            { label: 'Critical', value: data.kpis.critical_alerts },
            { label: 'At Risk', value: data.kpis.employees_at_risk },
            { label: 'Overdue', value: data.kpis.overdue_actions },
            { label: 'Assigned', value: data.kpis.assigned_actions },
            { label: 'Unassigned', value: data.kpis.unassigned_actions },
          ].map(kpi => (
            <div key={kpi.label} className={`${t.kpiCell} p-2.5 text-center`}>
              <div className={`text-lg font-light tabular-nums ${kpi.value > 0 ? t.kpiValActive : t.kpiValEmpty}`}>{kpi.value}</div>
              <div className={`text-[9px] font-semibold ${t.kpiLabelCls} mt-0.5`}>{kpi.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Coming up list */}
      <div className="p-3 space-y-2">
        {loading && (
          <div className="p-6 text-center">
            <div className={`w-4 h-4 border-2 ${t.spinner} rounded-full animate-spin mx-auto mb-2`} />
            <p className={`text-xs ${t.textMuted}`}>Loading</p>
          </div>
        )}

        {error && !loading && (
          <div className="p-4 text-center">
            <TriangleAlert className={`w-4 h-4 ${t.icon} mx-auto mb-1.5`} />
            <p className={`text-xs ${t.textMuted}`}>Failed to load</p>
          </div>
        )}

        {!loading && !error && data && data.coming_up.length === 0 && (
          <div className="p-4 text-center">
            <CheckCircle2 className={`w-4 h-4 ${t.icon} mx-auto mb-1.5`} />
            <p className={`text-xs ${t.textMuted}`}>No upcoming changes in {horizon}d window</p>
          </div>
        )}

        {!loading && !error && data && data.coming_up.map((item) => {
          const sevDot = t.sevDot[item.severity as keyof typeof t.sevDot] ?? t.sevDot.info;
          const sevBadge = t.sevBadge[item.severity as keyof typeof t.sevBadge] ?? t.sevBadge.info;
          const sevLabel = SEVERITY_LABELS[item.severity] ?? 'Info';
          const categoryLabel = item.category ? (COMPLIANCE_CATEGORY_LABELS[item.category] ?? item.category) : null;
          const daysLabel = item.days_until != null
            ? item.days_until <= 0 ? 'Today' : `${item.days_until}d`
            : '—';
          const daysColor = t.daysColor(item.days_until);
          const sla = getSlaStyle(item.sla_state);
          const dueLabel = formatDateLabel(item.action_due_date);

          return (
            <div
              key={item.legislation_id}
              onClick={() => handleItemClick(item)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  handleItemClick(item);
                }
              }}
              role="button"
              tabIndex={0}
              className={`w-full text-left p-3.5 ${t.innerHover} transition-all group cursor-pointer`}
            >
              <div className="flex items-start gap-2.5">
                <div className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${sevDot}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className={`text-sm ${t.textMain} font-medium leading-tight truncate`}>
                      {item.title}
                    </span>
                    <span className={`text-xs font-mono tabular-nums flex-shrink-0 ${daysColor}`}>
                      {daysLabel}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <div className={`flex items-center gap-1 ${t.textMuted}`}>
                      <MapPin className="w-2.5 h-2.5" />
                      <span className="text-[10px]">{item.location_name}</span>
                    </div>

                    {categoryLabel && (
                      <span className={`text-[10px] ${t.textDim} ${t.innerEl} px-1.5 py-px`}>
                        {categoryLabel}
                      </span>
                    )}

                    <span className={`text-[10px] px-1.5 py-px ${sevBadge}`}>
                      {sevLabel}
                    </span>
                    <span className={`text-[10px] px-1.5 py-px ${sla.badge}`}>
                      {sla.label}
                    </span>
                  </div>

                  <div className="mt-1.5 space-y-1">
                    <div className={`text-xs ${t.textMuted}`}>
                      <span className={t.textFaint}>Next:</span> {item.next_action || 'Review legal impact and assign an owner.'}
                    </div>
                    <div className={`flex items-center gap-3 flex-wrap text-[10px] ${t.textMuted}`}>
                      <span>Owner: <span className={t.textMain}>{item.action_owner_name || 'Unassigned'}</span></span>
                      <span className={sla.dueText}>Due: {dueLabel}</span>
                    </div>

                    {item.estimated_financial_impact && (
                      <div className={`text-[10px] ${t.textDim}`}>
                        Exposure: {item.estimated_financial_impact}
                      </div>
                    )}

                    {item.affected_employee_count > 0 && (
                      <div className="mt-1 flex items-center gap-1.5">
                        <Users className={`w-2.5 h-2.5 ${t.icon}`} />
                        <span className={`text-[10px] ${t.textMuted}`}>
                          {item.affected_employee_count} employee{item.affected_employee_count !== 1 ? 's' : ''}
                          {item.affected_employee_sample.length > 0 && (
                            <span className={t.textFaint}>
                              {' '}— {item.affected_employee_sample.slice(0, 3).join(', ')}
                              {item.affected_employee_count > 3 ? ` +${item.affected_employee_count - 3} more` : ''}
                            </span>
                          )}
                        </span>
                        <span className={`text-[9px] ${t.textFaint} font-mono`}>~est</span>
                      </div>
                    )}
                  </div>
                </div>

                <ChevronRight className={`w-3.5 h-3.5 ${t.arrow} transition-colors flex-shrink-0 mt-0.5`} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      {data && data.coming_up.length > 0 && (
        <div className={`p-3 ${t.footerBg} flex items-center justify-between`}>
          {(criticalCount > 0 || warningCount > 0) && (
            <span className={`text-[10px] ${t.textMuted}`}>
              {criticalCount > 0 && `${criticalCount} critical`}
              {criticalCount > 0 && warningCount > 0 && ' · '}
              {warningCount > 0 && `${warningCount} warning`}
            </span>
          )}
          <button
            onClick={() => navigate('/app/matcha/compliance?tab=upcoming')}
            className={`ml-auto text-xs ${t.textMuted} hover:${t.textMain} transition-colors`}
          >
            Full Compliance View
          </button>
        </div>
      )}

      {/* Compliance Action Modal */}
      {selectedItem && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
          onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}
        >
          <div className={`w-full max-w-lg ${t.modalBg} shadow-2xl flex flex-col max-h-[90vh]`}>
            {/* Modal header */}
            <div className={`flex items-start justify-between p-5 ${t.border} border-b flex-shrink-0`}>
              <div className="flex items-center gap-2 min-w-0">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${t.sevDot[selectedItem.severity as keyof typeof t.sevDot] ?? t.sevDot.info}`} />
                <span className={`text-sm font-semibold ${t.textMain} leading-tight`}>{selectedItem.title}</span>
              </div>
              <button onClick={closeModal} className={`ml-3 flex-shrink-0 ${t.icon} hover:${t.textMain} transition-colors`}>
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="overflow-y-auto flex-1 p-5 space-y-4">
              {/* Meta badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <div className={`flex items-center gap-1 ${t.textMuted}`}>
                  <MapPin className="w-2.5 h-2.5" />
                  <span className="text-[10px]">{selectedItem.location_name}</span>
                </div>
                {selectedItem.category && (
                  <span className={`text-[10px] ${t.textMuted} ${t.innerEl} px-1.5 py-px`}>
                    {COMPLIANCE_CATEGORY_LABELS[selectedItem.category] ?? selectedItem.category}
                  </span>
                )}
                <span className={`text-[10px] px-1.5 py-px ${t.sevBadge[selectedItem.severity as keyof typeof t.sevBadge] ?? t.sevBadge.info}`}>
                  {SEVERITY_LABELS[selectedItem.severity] ?? 'Info'}
                </span>
                {selectedItem.effective_date && (
                  <span className={`text-[10px] ${t.textMuted} ${t.innerEl} px-1.5 py-px`}>
                    Effective {new Date(`${selectedItem.effective_date}T00:00:00`).toLocaleDateString()}
                    {selectedItem.days_until != null && (
                      <span className={t.daysColor(selectedItem.days_until)}>
                        {' '}· {selectedItem.days_until <= 0 ? 'Today' : `${selectedItem.days_until}d`}
                      </span>
                    )}
                  </span>
                )}
              </div>

              {/* Description */}
              {selectedItem.description && (
                <div className={`${t.descBox} p-3`}>
                  <p className={`text-xs ${t.textMuted} leading-relaxed`}>{selectedItem.description}</p>
                </div>
              )}

              {/* Next action / playbook */}
              {(selectedItem.next_action || selectedItem.recommended_playbook) && (
                <div className="space-y-2">
                  {selectedItem.next_action && (
                    <div className={`text-xs ${t.textMuted}`}>
                      <span className={`text-[10px] ${t.textFaint} block mb-0.5`}>Recommended Action</span>
                      {selectedItem.next_action}
                    </div>
                  )}
                  {selectedItem.recommended_playbook && (
                    <div className={`text-xs ${t.textMuted}`}>
                      <span className={`text-[10px] ${t.textFaint} block mb-0.5`}>Playbook</span>
                      {selectedItem.recommended_playbook}
                    </div>
                  )}
                </div>
              )}

              {/* Affected employees */}
              {selectedItem.affected_employee_count > 0 && (
                <div className="flex items-center gap-1.5">
                  <Users className={`w-3 h-3 ${t.icon}`} />
                  <span className={`text-[10px] ${t.textMuted}`}>
                    {selectedItem.affected_employee_count} employee{selectedItem.affected_employee_count !== 1 ? 's' : ''} affected
                    {selectedItem.affected_employee_sample.length > 0 && (
                      <span className={t.textFaint}> — {selectedItem.affected_employee_sample.slice(0, 3).join(', ')}{selectedItem.affected_employee_count > 3 ? ` +${selectedItem.affected_employee_count - 3} more` : ''}</span>
                    )}
                  </span>
                </div>
              )}

              {/* Financial exposure */}
              {selectedItem.estimated_financial_impact && (
                <div className={`text-xs ${t.textDim} ${t.descBox} px-3 py-2`}>
                  Exposure: {selectedItem.estimated_financial_impact}
                </div>
              )}

              {/* Source link */}
              {selectedItem.source_url && (
                <a
                  href={selectedItem.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`flex items-center gap-1 text-xs ${t.textFaint} hover:${t.textMain} transition-colors`}
                >
                  <ExternalLink className="w-3 h-3" />
                  View source
                </a>
              )}

              {/* Divider */}
              <div className={`${t.border} border-t`} />

              {/* Assign */}
              <div className="space-y-3">
                <div>
                  <label className={`block text-[10px] ${t.textMuted} mb-1.5`}>Assign To</label>
                  <select
                    value={modalOwnerId}
                    onChange={(e) => setModalOwnerId(e.target.value)}
                    className={`w-full ${t.selectCls}`}
                  >
                    <option value="">— Unassigned —</option>
                    {assignableUsers.map(u => (
                      <option key={u.id} value={u.id}>{u.name}{u.name !== u.email ? ` (${u.email})` : ''}</option>
                    ))}
                    {currentUser && !assignableUsers.find(u => u.id === currentUser.id) && (
                      <option value={currentUser.id}>Me</option>
                    )}
                  </select>
                </div>

                <div>
                  <label className={`block text-[10px] ${t.textMuted} mb-1.5`}>Turnaround Time</label>
                  <div className="flex flex-wrap gap-1.5">
                    {TURNAROUND_OPTIONS.map(opt => (
                      <button
                        key={opt.days}
                        onClick={() => setModalTurnaround(modalTurnaround === opt.days ? null : opt.days)}
                        className={`px-3 py-1.5 text-xs rounded-lg transition-colors ${
                          modalTurnaround === opt.days ? t.pillActive : t.pillInactive
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                  {modalTurnaround !== null && (
                    <p className={`mt-1.5 text-xs ${t.textMuted}`}>
                      Due date will be set to {(() => {
                        const d = new Date();
                        d.setDate(d.getDate() + modalTurnaround);
                        return d.toLocaleDateString();
                      })()} · reminder email sent when due approaches
                    </p>
                  )}
                </div>
              </div>

              {modalError && (
                <p className={`text-xs ${t.textMain}`}>{modalError}</p>
              )}
            </div>

            {/* Modal footer */}
            <div className={`p-5 ${t.footerBg} flex items-center justify-between gap-2 flex-shrink-0`}>
              <div className="flex items-center gap-2">
                {selectedItem.action_status !== 'actioned' && (
                  <button
                    onClick={() => void markActioned(selectedItem)}
                    disabled={modalSaving}
                    className={`px-4 py-2 text-xs rounded-lg ${t.innerEl} ${t.textDim} hover:${t.textMain} disabled:opacity-50 transition-colors`}
                  >
                    Mark Actioned
                  </button>
                )}
                <button
                  onClick={() => {
                    const params = new URLSearchParams({ location_id: selectedItem.location_id, tab: 'upcoming', legislation_id: selectedItem.legislation_id });
                    navigate(`/app/matcha/compliance?${params.toString()}`);
                  }}
                  className={`px-4 py-2 text-xs ${t.textFaint} hover:${t.textMain} transition-colors`}
                >
                  Full View
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={closeModal}
                  className={`px-4 py-2 text-xs rounded-lg ${t.innerEl} ${t.textMuted} hover:${t.textMain} transition-colors`}
                >
                  Cancel
                </button>
                <button
                  onClick={() => void saveModalChanges()}
                  disabled={modalSaving || (modalOwnerId === (selectedItem.action_owner_id ?? '') && modalTurnaround === null)}
                  className={`px-4 py-2 text-xs rounded-lg ${t.btnPrimary} disabled:opacity-40 disabled:cursor-not-allowed transition-colors`}
                >
                  {modalSaving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function Dashboard() {
  const navigate = useNavigate();
  const { user, hasFeature, platformFeatures, profile } = useAuth();
  const [ptoSummary, setPtoSummary] = useState<PTOSummary | null>(null);
  const [dashStats, setDashStats] = useState<DashboardStats | null>(null);
  const [compliancePendingActions, setCompliancePendingActions] = useState<ComplianceDashboardItem[]>([]);
  const [credExpiry, setCredExpiry] = useState<{ summary: CredentialExpirationSummary; expirations: CredentialExpiration[] } | null>(null);

  const isHealthcare = user?.role === 'client'
    ? (profile as ClientProfile | null)?.industry?.toLowerCase() === 'healthcare'
    : false;

  useEffect(() => {
    const token = getAccessToken();
    const headers = { Authorization: `Bearer ${token}` };
    const canUsePlatformFeature = (feature: string) =>
      platformFeatures.size === 0 || platformFeatures.has(feature);

    if (hasFeature('time_off') && canUsePlatformFeature('time_off')) {
      fetch(`${API_BASE}/employees/pto/summary`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(data => data && setPtoSummary(data))
        .catch(err => console.error('Failed to fetch PTO summary:', err));
    }

    fetch(`${API_BASE}/dashboard/stats`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setDashStats(data))
      .catch(err => console.error('Failed to fetch dashboard stats:', err));

    if (isHealthcare) {
      credentialExpirations.get()
        .then(data => setCredExpiry(data))
        .catch(err => console.error('Failed to fetch credential expirations:', err));
    }
  }, [hasFeature, platformFeatures, isHealthcare]);

  const showComplianceImpact =
    user?.role === 'client' &&
    hasFeature('compliance') &&
    (platformFeatures.size === 0 || platformFeatures.has('compliance'));
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  useEffect(() => {
    if (!showComplianceImpact) {
      setCompliancePendingActions([]);
      return;
    }

    complianceAPI.getDashboard(90)
      .then((dashboardData) => {
        const severityScore: Record<ComplianceDashboardItem['severity'], number> = {
          critical: 50,
          warning: 20,
          info: 5,
        };
        const slaScore: Record<ComplianceDashboardItem['sla_state'], number> = {
          overdue: 100,
          due_soon: 50,
          unassigned: 30,
          on_track: 10,
          completed: 0,
        };

        const prioritized = [...dashboardData.coming_up]
          .filter(item => item.sla_state !== 'completed')
          .sort((a, b) => {
            const aTime = a.days_until ?? 365;
            const bTime = b.days_until ?? 365;
            const aScore = (severityScore[a.severity] ?? 0) + (slaScore[a.sla_state] ?? 0) + Math.max(0, 30 - aTime);
            const bScore = (severityScore[b.severity] ?? 0) + (slaScore[b.sla_state] ?? 0) + Math.max(0, 30 - bTime);
            return bScore - aScore;
          })
          .slice(0, 3);

        setCompliancePendingActions(prioritized);
      })
      .catch((err) => {
        console.error('Failed to fetch compliance pending actions:', err);
        setCompliancePendingActions([]);
      });
  }, [showComplianceImpact]);

  const totalAlerts = (dashStats?.critical_compliance_alerts ?? 0) + (dashStats?.warning_compliance_alerts ?? 0);
  const erOpen = dashStats?.er_case_summary?.open_cases ?? 0;
  const irOpen = dashStats?.incident_summary?.total_open ?? 0;
  const staleCount = dashStats?.stale_policies?.stale_count ?? 0;

  const stats = [
    {
      label: 'Compliance Alerts',
      value: dashStats ? String(totalAlerts) : '-',
      change: dashStats
        ? totalAlerts === 0
          ? 'All clear'
          : `${dashStats.critical_compliance_alerts} critical · ${dashStats.warning_compliance_alerts} warning`
        : '',
      icon: ShieldAlert,
      path: '/app/matcha/compliance',
      urgent: (dashStats?.critical_compliance_alerts ?? 0) > 0,
    },
    {
      label: 'Open ER Cases',
      value: dashStats ? String(erOpen) : '-',
      change: dashStats
        ? erOpen === 0
          ? 'No open cases'
          : `${dashStats.er_case_summary?.investigating ?? 0} investigating · ${dashStats.er_case_summary?.pending_action ?? 0} pending`
        : '',
      icon: Users,
      path: '/app/matcha/er-copilot',
      urgent: erOpen > 0,
    },
    {
      label: 'Open Incidents',
      value: dashStats ? String(irOpen) : '-',
      change: dashStats
        ? irOpen === 0
          ? 'No open incidents'
          : `${dashStats.incident_summary?.critical ?? 0} critical · ${dashStats.incident_summary?.high ?? 0} high`
        : '',
      icon: AlertTriangle,
      path: '/app/ir/incidents',
      urgent: (dashStats?.incident_summary?.critical ?? 0) > 0,
    },
    {
      label: 'Stale Policies',
      value: dashStats ? String(staleCount) : '-',
      change: dashStats
        ? staleCount === 0
          ? 'All up to date'
          : `Oldest: ${dashStats.stale_policies?.oldest_days ?? 0}d ago`
        : '',
      icon: FileText,
      path: '/app/matcha/policies',
      urgent: staleCount > 0,
    },
  ];

  const complianceRate = dashStats?.compliance_rate ?? 0;

  const dashboardWidgets = [
    { id: 'stats', label: 'Key Metrics', icon: Activity },
    { id: 'compliance', label: 'Compliance Health', icon: ShieldAlert },
    { id: 'pinned_compliance', label: 'Pinned Compliance', icon: Pin },
    { id: 'compliance_impact', label: 'Compliance Impact', icon: ShieldAlert },
    { id: 'actions', label: 'Pending Actions', icon: Clock },
    ...(isHealthcare ? [{ id: 'credential_alerts', label: 'Credential Alerts', icon: AlertTriangle }] : []),
    { id: 'activity', label: 'System Activity', icon: History },
    { id: 'incidents', label: 'Incident Reports', icon: AlertTriangle },
    { id: 'pto', label: 'Upcoming Time Off', icon: Calendar },
    { id: 'setup', label: 'Quick Setup', icon: Building },
  ];

  return (
    <>
    <OnboardingWizard />
    <div className="max-w-5xl mx-auto py-4">
    <CompanyProfileBanner />
    <GettingStartedChecklist />
    <div className="space-y-5 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex justify-between items-start mb-8 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-3xl font-bold tracking-tight ${t.textMain}`}>
              Command Center
            </h1>
            <div className={`px-2.5 py-0.5 ${t.livePill} text-[10px] font-bold rounded-full`}>
              Live
            </div>
          </div>
          <p className={`text-[10px] ${t.textMuted} mt-1.5 font-mono tracking-wide`}>Operations Dashboard</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => navigate('/app/matcha/policies/new')}
            className={`px-4 py-2 ${t.btnSecondary} rounded-lg text-[10px] font-bold transition-all`}
          >
            New Policy
          </button>
          <button
            onClick={() => navigate('/app/matcha/offer-letters')}
            className={`px-4 py-2 ${t.btnPrimary} rounded-lg text-[10px] font-bold transition-all`}
          >
            Create Offer
          </button>
        </div>
      </div>

      <WidgetContainer widgets={dashboardWidgets}>
        {(visibleWidgets) => (
          <div className="space-y-5">
            {/* Stats Grid */}
            {visibleWidgets.has('stats') && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {stats.map((stat) => (
                  <button
                    key={stat.label}
                    onClick={() => navigate(stat.path)}
                    className={`${t.cardDark} p-5 ${t.cardDarkHover} transition-all group relative overflow-hidden text-left ${stat.urgent ? 'ring-1 ring-red-500/30' : ''}`}
                  >
                    <div className={`absolute top-0 right-0 p-3 ${stat.urgent ? 'text-red-500/20' : t.cardDarkGhost} group-hover:scale-110 transition-all duration-500`}>
                       <stat.icon className="w-8 h-8" strokeWidth={0.5} />
                    </div>

                    <div className="relative z-10">
                      <div className={`${t.labelOnDark} mb-2`}>{stat.label}</div>
                      <div className={`text-3xl font-light font-mono mb-0.5 tabular-nums ${stat.urgent ? 'text-red-400' : 'text-zinc-50'}`}>{stat.value}</div>
                      <div className={`text-[9px] ${stat.urgent ? 'text-red-400/70' : t.textMuted} font-mono`}>
                         {stat.change}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}


            {/* Quick Setup — shown for new businesses with no employees and no policies */}
            {visibleWidgets.has('setup') && dashStats && dashStats.total_employees === 0 && dashStats.active_policies === 0 && (
              <Collapsible title="Quick Setup" icon={Activity} variant="light">
                <div className="p-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <button
                      onClick={() => navigate('/app/matcha/company')}
                      className={`flex items-center gap-3 p-4 ${t.innerHover} transition-all group text-left`}
                    >
                      <div className={`p-2 ${t.innerBg}`}>
                        <Building className={`w-4 h-4 ${t.textMain}`} />
                      </div>
                      <div className="flex-1">
                        <div className={`text-sm ${t.textMain} font-medium`}>Company Profile</div>
                        <div className={`text-xs ${t.textMuted} mt-0.5`}>Set up company info</div>
                      </div>
                      <ArrowUpRight className={`w-3.5 h-3.5 ${t.arrow} transition-colors`} />
                    </button>
                    <button
                      onClick={() => navigate('/app/matcha/employees')}
                      className={`flex items-center gap-3 p-4 ${t.innerHover} transition-all group text-left`}
                    >
                      <div className={`p-2 ${t.innerBg}`}>
                        <UserPlus className={`w-4 h-4 ${t.textMain}`} />
                      </div>
                      <div className="flex-1">
                        <div className={`text-sm ${t.textMain} font-medium`}>Add Employees</div>
                        <div className={`text-xs ${t.textMuted} mt-0.5`}>Import team via CSV</div>
                      </div>
                      <ArrowUpRight className={`w-3.5 h-3.5 ${t.arrow} transition-colors`} />
                    </button>
                  </div>
                </div>
              </Collapsible>
            )}

            <Tabs
              tabs={[
                { id: 'overview', label: 'Overview', icon: LayoutDashboard },
                { id: 'operations', label: 'Operations', icon: History },
              ]}
              variant="light"
            >
              {(activeTab) => (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  {activeTab === 'overview' && (
                    <>
                      <div className="lg:col-span-2 space-y-4">
                        {visibleWidgets.has('actions') && (
                          <div className={`${t.cardLight} p-6 h-fit`}>
                            <div className={`${t.label} mb-4`}>Pending Actions</div>
                            <div className="space-y-2">
                              {ptoSummary && ptoSummary.pending_count > 0 && (
                                <div
                                  onClick={() => navigate('/app/matcha/pto')}
                                  className={`${t.innerHover} p-4 flex items-start gap-3 cursor-pointer transition-colors group`}
                                >
                                    <Calendar className={`w-4 h-4 ${t.textMuted} mt-0.5`} />
                                    <div className="flex-1">
                                      <div className={`text-sm ${t.textMain} font-medium mb-0.5`}>PTO Requests Pending</div>
                                      <div className={`text-xs ${t.textMuted}`}>{ptoSummary.pending_count} request{ptoSummary.pending_count !== 1 ? 's' : ''} awaiting approval</div>
                                    </div>
                                    <ArrowUpRight className={`w-3.5 h-3.5 ${t.arrow} ml-auto transition-colors`} />
                                </div>
                              )}
                              {dashStats?.pending_incidents.map((incident) => (
                                <div
                                  key={incident.id}
                                  onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
                                  className={`${t.innerHover} p-4 flex items-start gap-3 cursor-pointer transition-colors group`}
                                >
                                    <div className={`mt-1.5 w-1.5 h-1.5 rounded-full ${t.activityDot.warning} flex-shrink-0`} />
                                    <div className="flex-1">
                                      <div className={`text-sm ${t.textMain} font-medium mb-0.5`}>{incident.title}</div>
                                      <div className={`text-xs ${t.textMuted}`}>{incident.incident_number} &bull; {incident.severity.charAt(0).toUpperCase() + incident.severity.slice(1)} Priority</div>
                                    </div>
                                    <ArrowUpRight className={`w-3.5 h-3.5 ${t.arrow} ml-auto transition-colors`} />
                                </div>
                              ))}
                              {showComplianceImpact && compliancePendingActions.map((item) => {
                                const isCritical = item.severity === 'critical' || item.sla_state === 'overdue';
                                return (
                                  <div
                                    key={`compliance-action-${item.legislation_id}`}
                                    onClick={() => {
                                      const params = new URLSearchParams({
                                        location_id: item.location_id,
                                        tab: 'upcoming',
                                        legislation_id: item.legislation_id,
                                      });
                                      navigate(`/app/matcha/compliance?${params.toString()}`);
                                    }}
                                    className={`${t.innerHover} p-4 flex items-start gap-3 cursor-pointer transition-colors group`}
                                  >
                                      <div className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${isCritical ? t.activityDot.success + ' animate-pulse' : t.activityDot.def}`} />
                                      <div className="flex-1">
                                        <div className={`text-sm ${t.textMain} font-medium mb-0.5`}>{item.title}</div>
                                        <div className={`text-xs ${t.textMuted}`}>
                                          Compliance &bull; {item.action_owner_name || 'Unassigned'} &bull; {item.sla_state.replace('_', ' ')}
                                        </div>
                                      </div>
                                      <ArrowUpRight className={`w-3.5 h-3.5 ${t.arrow} ml-auto transition-colors`} />
                                  </div>
                                );
                              })}
                              {dashStats?.wage_alerts && (
                                <div
                                  onClick={() => navigate('/app/risk-assessment')}
                                  className={`${t.innerHover} p-4 flex items-start gap-3 cursor-pointer transition-colors group`}
                                >
                                    <div className={`mt-1.5 w-1.5 h-1.5 rounded-full ${t.activityDot.warning} animate-pulse flex-shrink-0`} />
                                    <div className="flex-1">
                                      <div className={`text-sm ${t.textMain} font-medium mb-0.5`}>Employee Wage Compliance Alerts</div>
                                      <div className={`text-xs ${t.textMuted}`}>
                                        {[
                                          dashStats.wage_alerts.hourly_violations > 0 && `${dashStats.wage_alerts.hourly_violations} below min wage`,
                                          dashStats.wage_alerts.salary_violations > 0 && `${dashStats.wage_alerts.salary_violations} below exempt salary threshold`,
                                        ].filter(Boolean).join(' · ')}
                                        {' · '}{dashStats.wage_alerts.locations_affected} location{dashStats.wage_alerts.locations_affected !== 1 ? 's' : ''}
                                      </div>
                                    </div>
                                    <ArrowUpRight className={`w-3.5 h-3.5 ${t.arrow} ml-auto transition-colors`} />
                                </div>
                              )}
                              {credExpiry && credExpiry.expirations.length > 0 && (
                                <div
                                  onClick={() => navigate('/app/matcha/employees')}
                                  className={`${t.innerHover} p-4 flex items-start gap-3 cursor-pointer transition-colors group`}
                                >
                                    <div className={`mt-1.5 w-1.5 h-1.5 rounded-full ${credExpiry.summary.expired > 0 ? t.activityDot.warning : t.activityDot.def} flex-shrink-0`} />
                                    <div className="flex-1">
                                      <div className={`text-sm ${t.textMain} font-medium mb-0.5`}>Credential Alerts</div>
                                      <div className={`text-xs ${t.textMuted}`}>
                                        {[
                                          credExpiry.summary.expired > 0 && `${credExpiry.summary.expired} expired`,
                                          credExpiry.summary.critical > 0 && `${credExpiry.summary.critical} expiring soon`,
                                          credExpiry.summary.warning > 0 && `${credExpiry.summary.warning} upcoming`,
                                        ].filter(Boolean).join(' · ')}
                                      </div>
                                    </div>
                                    <ArrowUpRight className={`w-3.5 h-3.5 ${t.arrow} ml-auto transition-colors`} />
                                </div>
                              )}
                              {(!ptoSummary || ptoSummary.pending_count === 0)
                                && (!dashStats || dashStats.pending_incidents.length === 0)
                                && (!showComplianceImpact || compliancePendingActions.length === 0)
                                && !dashStats?.wage_alerts
                                && (!credExpiry || credExpiry.expirations.length === 0) && (
                                <div className="p-4 text-center">
                                  <CheckCircle2 className={`w-5 h-5 ${t.icon} mx-auto mb-1.5`} />
                                  <p className={`text-sm ${t.textFaint}`}>All caught up</p>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {visibleWidgets.has('pto') && ptoSummary && ptoSummary.upcoming_time_off > 0 && (
                          <div className={`${t.cardLight} p-6`}>
                              <div className="flex items-center justify-between mb-4">
                                <div className={t.label}>Upcoming Time Off</div>
                                <Calendar className={`w-4 h-4 ${t.icon}`} />
                              </div>
                              <div className={`text-4xl font-light font-mono ${t.textMain} mb-1 tabular-nums`}>{ptoSummary.upcoming_time_off}</div>
                              <div className={`text-[10px] ${t.textMuted} font-mono`}>employees out (30d)</div>
                              <button
                                onClick={() => navigate('/app/matcha/pto')}
                                className={`mt-4 ${t.btnPrimary} rounded-lg px-4 py-2 text-xs font-bold transition-colors`}
                              >
                                View Calendar
                              </button>
                          </div>
                        )}

                        {visibleWidgets.has('credential_alerts') && credExpiry && credExpiry.expirations.length > 0 && (
                          <div className={`${t.cardLight} overflow-hidden`}>
                            <div className={`p-4 border-b ${t.border} flex justify-between items-center`}>
                              <div className={t.label}>Credential Alerts</div>
                              <AlertTriangle className={`w-4 h-4 ${t.icon}`} />
                            </div>
                            <div className="p-5">
                              <div className="flex items-center gap-3 mb-4">
                                {credExpiry.summary.expired > 0 && (
                                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${isLight ? 'bg-red-100 text-red-700' : 'bg-red-900/30 text-red-400'}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${isLight ? 'bg-red-500' : 'bg-red-400'} animate-pulse`} />
                                    {credExpiry.summary.expired} Expired
                                  </span>
                                )}
                                {credExpiry.summary.critical > 0 && (
                                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${isLight ? 'bg-amber-100 text-amber-700' : 'bg-amber-900/30 text-amber-400'}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${isLight ? 'bg-amber-500' : 'bg-amber-400'}`} />
                                    {credExpiry.summary.critical} Critical
                                  </span>
                                )}
                                {credExpiry.summary.warning > 0 && (
                                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold ${isLight ? 'bg-yellow-100 text-yellow-700' : 'bg-yellow-900/30 text-yellow-400'}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${isLight ? 'bg-yellow-500' : 'bg-yellow-400'}`} />
                                    {credExpiry.summary.warning} Warning
                                  </span>
                                )}
                              </div>
                              <div className={`divide-y ${t.divide}`}>
                                {credExpiry.expirations.map((item, i) => {
                                  const expDate = new Date(item.expiry_date + 'T00:00:00');
                                  const dateStr = expDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
                                  const sevColor = item.severity === 'expired'
                                    ? (isLight ? 'text-red-600' : 'text-red-400')
                                    : item.severity === 'critical'
                                    ? (isLight ? 'text-amber-600' : 'text-amber-400')
                                    : (isLight ? 'text-yellow-600' : 'text-yellow-400');
                                  const sevDot = item.severity === 'expired'
                                    ? (isLight ? 'bg-red-500' : 'bg-red-400')
                                    : item.severity === 'critical'
                                    ? (isLight ? 'bg-amber-500' : 'bg-amber-400')
                                    : (isLight ? 'bg-yellow-500' : 'bg-yellow-400');
                                  return (
                                    <div
                                      key={`${item.employee_id}-${item.credential_type}-${i}`}
                                      onClick={() => navigate(`/app/matcha/employees`)}
                                      className={`py-3 flex items-center gap-3 cursor-pointer ${t.rowHover} transition-colors group`}
                                    >
                                      <div className={`w-1.5 h-1.5 rounded-full ${sevDot} flex-shrink-0 ${item.severity === 'expired' ? 'animate-pulse' : ''}`} />
                                      <div className="flex-1 min-w-0">
                                        <div className={`text-sm ${t.textMain} font-medium truncate`}>{item.employee_name}</div>
                                        <div className={`text-xs ${t.textMuted} truncate`}>{item.credential_label}</div>
                                      </div>
                                      <div className={`text-xs font-mono ${sevColor} whitespace-nowrap`}>
                                        {item.severity === 'expired' ? 'Expired ' : 'Expires '}{dateStr}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                            <div className={`p-3 ${t.footerBg}`}>
                              <button
                                onClick={() => navigate('/app/matcha/employees')}
                                className={`w-full text-center text-xs ${t.footerLink} transition-colors`}
                              >
                                View All Employees
                              </button>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="space-y-4">
                        {visibleWidgets.has('compliance') && (
                          <div className={`${t.cardDark} p-6 relative overflow-hidden group h-fit`}>
                            <div className="flex items-center justify-between mb-4">
                                <div className={t.labelOnDark}>Policy Signature Coverage</div>
                                <ShieldAlert className="w-4 h-4 text-zinc-600" />
                            </div>

                            <div className="relative w-32 h-32 mx-auto mb-4">
                                <svg className="w-full h-full transform -rotate-90">
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent" className={t.cardDarkTrack} />
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent"
                                    strokeDasharray={2 * Math.PI * 58}
                                    strokeDashoffset={(2 * Math.PI * 58) - (complianceRate / 100) * (2 * Math.PI * 58)}
                                    className="text-zinc-100 transition-all duration-1000"
                                  />
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                  <span className="text-2xl font-light text-zinc-50">{complianceRate > 0 ? `${complianceRate}%` : '--'}</span>
                                  <span className="text-xs text-zinc-500 mt-0.5">{complianceRate > 0 ? 'Signed' : 'No data'}</span>
                                </div>
                            </div>

                            {dashStats && dashStats.active_policies > 0 ? (
                              <div className="space-y-2">
                                <div className="flex justify-between text-xs text-zinc-400">
                                    <span>Signatures</span>
                                    <span className="text-zinc-100">{complianceRate}%</span>
                                </div>
                                <div className={`w-full ${t.cardDarkTrackBg} h-1 rounded-full overflow-hidden`}>
                                    <div className="bg-zinc-100 h-full transition-all duration-1000" style={{ width: `${complianceRate}%` }} />
                                </div>
                              </div>
                            ) : (
                              <p className="text-xs text-zinc-500 text-center">Create policies to track</p>
                            )}
                          </div>
                        )}
                      </div>

                      {visibleWidgets.has('pinned_compliance') && (
                        <div className="lg:col-span-3">
                          <PinnedComplianceWidget />
                        </div>
                      )}

                      {visibleWidgets.has('compliance_impact') && showComplianceImpact && (
                        <div className="lg:col-span-3">
                          <ComplianceDashboardWidget />
                        </div>
                      )}
                    </>
                  )}

                  {activeTab === 'operations' && (
                    <div className="lg:col-span-3 space-y-4">
                      {visibleWidgets.has('activity') && (
                        <div className={`${t.cardLight} overflow-hidden`}>
                          <div className={`p-4 border-b ${t.border} flex justify-between items-center`}>
                            <div className={t.label}>System Activity</div>
                            <Activity className={`w-4 h-4 ${t.icon}`} />
                          </div>
                          <div className={`divide-y ${t.divide}`}>
                            {dashStats && dashStats.recent_activity.length > 0 ? (
                              dashStats.recent_activity.map((item, i) => {
                                const ts = new Date(item.timestamp);
                                const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
                                const isToday = new Date().toDateString() === ts.toDateString();
                                const dateLabel = isToday ? 'TODAY' : ts.toLocaleDateString([], { month: 'short', day: 'numeric' }).toUpperCase();
                                return (
                                  <div key={i} className={`p-3 flex items-center justify-between ${t.rowHover} transition-colors group`}>
                                    <div className="flex items-center gap-3">
                                      <div className={`font-mono text-xs ${t.textFaint} w-12`}>
                                        {timeStr}
                                      </div>
                                      <div className="flex items-center gap-2.5">
                                        <div className={`w-1.5 h-1.5 rounded-full ${
                                            item.type === 'success' ? t.activityDot.success :
                                            item.type === 'warning' ? t.activityDot.warning : t.activityDot.def
                                        }`} />
                                        <span className={`text-sm ${t.textMain}`}>{item.action}</span>
                                      </div>
                                    </div>
                                    <div className={`hidden sm:block text-xs ${t.dateBadge} px-2 py-0.5 rounded-full`}>
                                      {dateLabel}
                                    </div>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="p-6 text-center">
                                <Activity className={`w-5 h-5 ${t.icon} mx-auto mb-1.5`} />
                                <p className={`text-sm ${t.textMuted}`}>No recent activity</p>
                              </div>
                            )}
                          </div>
                          {dashStats && dashStats.recent_activity.length > 0 && (
                            <div className={`p-3 ${t.footerBg}`}>
                              <button className={`w-full text-center text-xs ${t.footerLink} transition-colors`}>
                                  Full Log
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {visibleWidgets.has('incidents') && dashStats?.incident_summary && dashStats.incident_summary.total_open > 0 && (
                        <div className={`${t.cardLight} overflow-hidden`}>
                          <div className={`p-4 border-b ${t.border} flex justify-between items-center`}>
                            <div className={t.label}>Incidents</div>
                            <ShieldAlert className={`w-4 h-4 ${t.icon}`} />
                          </div>
                          <div className="p-5">
                            <div className="flex items-baseline gap-2.5 mb-4">
                              <span className={`text-3xl font-light ${t.textMain} tabular-nums`}>{dashStats.incident_summary.total_open}</span>
                              <span className={`text-xs ${t.textMuted} font-medium`}>Open Incident{dashStats.incident_summary.total_open !== 1 ? 's' : ''}</span>
                              {dashStats.incident_summary.recent_7_days > 0 && (
                                <span className={`ml-auto text-xs ${t.recentBadge} px-2 py-0.5 rounded-full`}>
                                  +{dashStats.incident_summary.recent_7_days}
                                </span>
                              )}
                            </div>
                            <div className="grid grid-cols-4 gap-3">
                              {[
                                { label: 'Crit', count: dashStats.incident_summary.critical, color: t.incidentSev[0].text, dot: t.incidentSev[0].dot },
                                { label: 'High', count: dashStats.incident_summary.high, color: t.incidentSev[1].text, dot: t.incidentSev[1].dot },
                                { label: 'Med', count: dashStats.incident_summary.medium, color: t.incidentSev[2].text, dot: t.incidentSev[2].dot },
                                { label: 'Low', count: dashStats.incident_summary.low, color: t.incidentSev[3].text, dot: t.incidentSev[3].dot },
                              ].map((sev) => (
                                <div key={sev.label} className={`${t.innerEl} p-3 text-center`}>
                                  <div className={`text-xl font-light tabular-nums ${sev.count > 0 ? sev.color : t.textFaint}`}>{sev.count}</div>
                                  <div className="flex items-center justify-center gap-1 mt-1">
                                    <span className={`w-1.5 h-1.5 rounded-full ${sev.count > 0 ? sev.dot : t.activityDot.def}`} />
                                    <span className={`text-[10px] ${t.textMuted}`}>{sev.label}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                          <div className={`p-3 ${t.footerBg}`}>
                            <button
                              onClick={() => navigate('/app/ir/incidents')}
                              className={`w-full text-center text-xs ${t.footerLink} transition-colors`}
                            >
                              View All
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </Tabs>
          </div>
        )}
      </WidgetContainer>
    </div>
    </div>
    </>
  );
}

export default Dashboard;
