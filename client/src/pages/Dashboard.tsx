import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Users, FileText, CheckCircle2, Clock, Activity, ShieldAlert, Calendar, Building, UserPlus, LayoutDashboard, History, AlertTriangle, MapPin, ChevronRight, TriangleAlert, X, ExternalLink, Sparkles } from 'lucide-react';
import { getAccessToken } from '../api/client';
import { OnboardingWizard } from '../components/OnboardingWizard';
import { Collapsible } from '../components/Collapsible';
import { Tabs } from '../components/Tabs';
import { WidgetContainer } from '../components/WidgetContainer';
import { complianceAPI, COMPLIANCE_CATEGORY_LABELS } from '../api/compliance';
import type { ComplianceDashboard, ComplianceDashboardItem, ComplianceActionPlanUpdate, AssignableUser } from '../api/compliance';
import { useAuth } from '../context/AuthContext';
import type { ClientProfile } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

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

interface DashboardStats {
  active_policies: number;
  pending_signatures: number;
  total_employees: number;
  compliance_rate: number;
  pending_incidents: PendingIncident[];
  recent_activity: ActivityItem[];
  incident_summary?: IncidentSummary;
}

type HorizonDays = 30 | 60 | 90;

const SEVERITY_STYLES: Record<string, { dot: string; badge: string; label: string }> = {
  critical: {
    dot: 'bg-sage-900 animate-pulse',
    badge: 'bg-sage-200 text-sage-900 rounded-full',
    label: 'Critical',
  },
  warning: {
    dot: 'bg-sage-500',
    badge: 'bg-sage-200 text-sage-600 rounded-full',
    label: 'Warning',
  },
  info: {
    dot: 'bg-sage-400',
    badge: 'bg-sage-200 text-sage-500 rounded-full',
    label: 'Info',
  },
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
    <div className="relative bg-sage-100 rounded-3xl p-6 mb-6 animate-in fade-in slide-in-from-top-2 duration-500">
      <button
        onClick={dismiss}
        className="absolute top-4 right-4 text-sage-400 hover:text-sage-900 transition-colors"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
      <div className="flex items-start gap-4">
        <div className="p-2.5 bg-sage-200 rounded-2xl shrink-0">
          <Sparkles className="w-5 h-5 text-sage-900" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-sage-900 mb-1">Complete your company profile</h3>
          <p className="text-sm text-sage-500 leading-relaxed mb-3">
            Add your headquarters location, benefits, and employment defaults so the AI can pre-fill offer letters,
            give jurisdiction-aware guidance, and generate better documents without extra questions.
          </p>
          <button
            onClick={() => { dismiss(); navigate('/app/matcha/company'); }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-sage-900 text-sage-100 hover:bg-sage-800 rounded-full text-xs font-bold transition-colors"
          >
            Set Up Profile
            <ChevronRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

function ComplianceDashboardWidget() {
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();
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
    if (slaState === 'overdue') {
      return { label: 'Overdue', badge: 'bg-sage-200 text-sage-900 rounded-full', dueText: 'text-sage-900' };
    }
    if (slaState === 'due_soon') {
      return { label: 'Due Soon', badge: 'bg-sage-200 text-sage-600 rounded-full', dueText: 'text-sage-600' };
    }
    if (slaState === 'completed') {
      return { label: 'Completed', badge: 'bg-sage-300 text-sage-500 rounded-full', dueText: 'text-sage-500' };
    }
    if (slaState === 'unassigned') {
      return { label: 'Unassigned', badge: 'bg-sage-300 text-sage-500 rounded-full', dueText: 'text-sage-500' };
    }
    return { label: 'On Track', badge: 'bg-sage-300 text-sage-500 rounded-full', dueText: 'text-sage-500' };
  };

  const criticalCount = data?.coming_up.filter(i => i.severity === 'critical').length ?? 0;
  const warningCount = data?.coming_up.filter(i => i.severity === 'warning').length ?? 0;

  return (
    <div className="bg-sage-100 rounded-3xl overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-sage-300 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <ShieldAlert className="w-4 h-4 text-sage-500" />
          <h2 className="text-base font-semibold text-sage-900">Compliance Impact</h2>
          {criticalCount > 0 && (
            <span className="px-2 py-0.5 text-[10px] font-medium bg-sage-200 text-sage-900 rounded-full">
              {criticalCount} critical
            </span>
          )}
        </div>
        {/* Horizon selector */}
        <div className="flex gap-1.5">
          {([30, 60, 90] as HorizonDays[]).map(d => (
            <button
              key={d}
              onClick={() => setHorizon(d)}
              className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                horizon === d
                  ? 'bg-sage-900 text-sage-100'
                  : 'bg-sage-200 text-sage-500 hover:text-sage-900'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* KPI row */}
      {data && (
        <div className="grid grid-cols-3 md:grid-cols-7 gap-px bg-sage-300 border-b border-sage-300">
          {[
            { label: 'Locations', value: data.kpis.total_locations },
            { label: 'Unread Alerts', value: data.kpis.unread_alerts },
            { label: 'Critical', value: data.kpis.critical_alerts },
            { label: 'At Risk', value: data.kpis.employees_at_risk },
            { label: 'Overdue', value: data.kpis.overdue_actions },
            { label: 'Assigned', value: data.kpis.assigned_actions },
            { label: 'Unassigned', value: data.kpis.unassigned_actions },
          ].map(kpi => (
            <div key={kpi.label} className="bg-sage-200 p-2.5 text-center">
              <div className={`text-lg font-light tabular-nums ${kpi.value > 0 ? 'text-sage-900' : 'text-sage-400'}`}>{kpi.value}</div>
              <div className="text-[8px] uppercase tracking-widest text-sage-500 mt-0.5">{kpi.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Coming up list */}
      <div className="p-3 space-y-2">
        {loading && (
          <div className="p-6 text-center">
            <div className="w-4 h-4 border-2 border-sage-300 border-t-sage-900 rounded-full animate-spin mx-auto mb-2" />
            <p className="text-xs text-sage-500">Loading</p>
          </div>
        )}

        {error && !loading && (
          <div className="p-4 text-center">
            <TriangleAlert className="w-4 h-4 text-sage-400 mx-auto mb-1.5" />
            <p className="text-xs text-sage-500">Failed to load</p>
          </div>
        )}

        {!loading && !error && data && data.coming_up.length === 0 && (
          <div className="p-4 text-center">
            <CheckCircle2 className="w-4 h-4 text-sage-400 mx-auto mb-1.5" />
            <p className="text-xs text-sage-500">No upcoming changes in {horizon}d window</p>
          </div>
        )}

        {!loading && !error && data && data.coming_up.map((item) => {
          const sev = SEVERITY_STYLES[item.severity] ?? SEVERITY_STYLES.info;
          const categoryLabel = item.category ? (COMPLIANCE_CATEGORY_LABELS[item.category] ?? item.category) : null;
          const daysLabel = item.days_until != null
            ? item.days_until <= 0 ? 'Today' : `${item.days_until}d`
            : '—';
          const daysColor = item.days_until != null && item.days_until <= 30
            ? 'text-sage-900 font-semibold'
            : item.days_until != null && item.days_until <= 60
            ? 'text-sage-600'
            : 'text-sage-400';
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
              className="w-full text-left p-3.5 bg-sage-200 rounded-2xl hover:bg-sage-300 transition-all group cursor-pointer"
            >
              <div className="flex items-start gap-2.5">
                <div className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${sev.dot}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="text-sm text-sage-900 font-medium leading-tight truncate">
                      {item.title}
                    </span>
                    <span className={`text-xs font-mono tabular-nums flex-shrink-0 ${daysColor}`}>
                      {daysLabel}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="flex items-center gap-1 text-sage-500">
                      <MapPin className="w-2.5 h-2.5" />
                      <span className="text-[10px]">{item.location_name}</span>
                    </div>

                    {categoryLabel && (
                      <span className="text-[10px] text-sage-500 bg-sage-300 px-1.5 py-px rounded-full">
                        {categoryLabel}
                      </span>
                    )}

                    <span className={`text-[10px] px-1.5 py-px ${sev.badge}`}>
                      {sev.label}
                    </span>
                    <span className={`text-[10px] px-1.5 py-px ${sla.badge}`}>
                      {sla.label}
                    </span>
                  </div>

                  <div className="mt-1.5 space-y-1">
                    <div className="text-xs text-sage-500">
                      <span className="text-sage-400">Next:</span> {item.next_action || 'Review legal impact and assign an owner.'}
                    </div>
                    <div className="flex items-center gap-3 flex-wrap text-[10px] text-sage-500">
                      <span>Owner: <span className="text-sage-900">{item.action_owner_name || 'Unassigned'}</span></span>
                      <span className={sla.dueText}>Due: {dueLabel}</span>
                    </div>

                    {item.estimated_financial_impact && (
                      <div className="text-[10px] text-sage-600">
                        Exposure: {item.estimated_financial_impact}
                      </div>
                    )}

                    {item.affected_employee_count > 0 && (
                      <div className="mt-1 flex items-center gap-1.5">
                        <Users className="w-2.5 h-2.5 text-sage-400" />
                        <span className="text-[10px] text-sage-500">
                          {item.affected_employee_count} employee{item.affected_employee_count !== 1 ? 's' : ''}
                          {item.affected_employee_sample.length > 0 && (
                            <span className="text-sage-400">
                              {' '}— {item.affected_employee_sample.slice(0, 3).join(', ')}
                              {item.affected_employee_count > 3 ? ` +${item.affected_employee_count - 3} more` : ''}
                            </span>
                          )}
                        </span>
                        <span className="text-[9px] text-sage-400 font-mono">~est</span>
                      </div>
                    )}
                  </div>
                </div>

                <ChevronRight className="w-3.5 h-3.5 text-sage-400 group-hover:text-sage-900 transition-colors flex-shrink-0 mt-0.5" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      {data && data.coming_up.length > 0 && (
        <div className="p-3 border-t border-sage-300 bg-sage-200 flex items-center justify-between">
          {(criticalCount > 0 || warningCount > 0) && (
            <span className="text-[10px] text-sage-500">
              {criticalCount > 0 && `${criticalCount} critical`}
              {criticalCount > 0 && warningCount > 0 && ' · '}
              {warningCount > 0 && `${warningCount} warning`}
            </span>
          )}
          <button
            onClick={() => navigate('/app/matcha/compliance?tab=upcoming')}
            className="ml-auto text-xs text-sage-500 hover:text-sage-900 transition-colors"
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
          <div className="w-full max-w-lg bg-sage-100 rounded-3xl shadow-2xl flex flex-col max-h-[90vh]">
            {/* Modal header */}
            <div className="flex items-start justify-between p-5 border-b border-sage-300 flex-shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${SEVERITY_STYLES[selectedItem.severity]?.dot ?? 'bg-sage-400'}`} />
                <span className="text-sm font-semibold text-sage-900 leading-tight">{selectedItem.title}</span>
              </div>
              <button onClick={closeModal} className="ml-3 flex-shrink-0 text-sage-400 hover:text-sage-900 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="overflow-y-auto flex-1 p-5 space-y-4">
              {/* Meta badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <div className="flex items-center gap-1 text-sage-500">
                  <MapPin className="w-2.5 h-2.5" />
                  <span className="text-[10px]">{selectedItem.location_name}</span>
                </div>
                {selectedItem.category && (
                  <span className="text-[10px] text-sage-500 bg-sage-300 px-1.5 py-px rounded-full">
                    {COMPLIANCE_CATEGORY_LABELS[selectedItem.category] ?? selectedItem.category}
                  </span>
                )}
                <span className={`text-[10px] px-1.5 py-px ${SEVERITY_STYLES[selectedItem.severity]?.badge}`}>
                  {SEVERITY_STYLES[selectedItem.severity]?.label}
                </span>
                {selectedItem.effective_date && (
                  <span className="text-[10px] text-sage-500 bg-sage-200 px-1.5 py-px rounded-full">
                    Effective {new Date(`${selectedItem.effective_date}T00:00:00`).toLocaleDateString()}
                    {selectedItem.days_until != null && (
                      <span className={selectedItem.days_until <= 30 ? ' text-sage-900 font-semibold' : selectedItem.days_until <= 60 ? ' text-sage-600' : ''}>
                        {' '}· {selectedItem.days_until <= 0 ? 'Today' : `${selectedItem.days_until}d`}
                      </span>
                    )}
                  </span>
                )}
              </div>

              {/* Description */}
              {selectedItem.description && (
                <div className="bg-sage-200 rounded-2xl p-3">
                  <p className="text-xs text-sage-500 leading-relaxed">{selectedItem.description}</p>
                </div>
              )}

              {/* Next action / playbook */}
              {(selectedItem.next_action || selectedItem.recommended_playbook) && (
                <div className="space-y-2">
                  {selectedItem.next_action && (
                    <div className="text-xs text-sage-500">
                      <span className="text-[10px] text-sage-400 block mb-0.5">Recommended Action</span>
                      {selectedItem.next_action}
                    </div>
                  )}
                  {selectedItem.recommended_playbook && (
                    <div className="text-xs text-sage-500">
                      <span className="text-[10px] text-sage-400 block mb-0.5">Playbook</span>
                      {selectedItem.recommended_playbook}
                    </div>
                  )}
                </div>
              )}

              {/* Affected employees */}
              {selectedItem.affected_employee_count > 0 && (
                <div className="flex items-center gap-1.5">
                  <Users className="w-3 h-3 text-sage-400" />
                  <span className="text-[10px] text-sage-500">
                    {selectedItem.affected_employee_count} employee{selectedItem.affected_employee_count !== 1 ? 's' : ''} affected
                    {selectedItem.affected_employee_sample.length > 0 && (
                      <span className="text-sage-400"> — {selectedItem.affected_employee_sample.slice(0, 3).join(', ')}{selectedItem.affected_employee_count > 3 ? ` +${selectedItem.affected_employee_count - 3} more` : ''}</span>
                    )}
                  </span>
                </div>
              )}

              {/* Financial exposure */}
              {selectedItem.estimated_financial_impact && (
                <div className="text-xs text-sage-600 bg-sage-200 rounded-2xl px-3 py-2">
                  Exposure: {selectedItem.estimated_financial_impact}
                </div>
              )}

              {/* Source link */}
              {selectedItem.source_url && (
                <a
                  href={selectedItem.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-sage-500 hover:text-sage-900 transition-colors"
                >
                  <ExternalLink className="w-3 h-3" />
                  View source
                </a>
              )}

              {/* Divider */}
              <div className="border-t border-sage-300" />

              {/* Assign */}
              <div className="space-y-3">
                <div>
                  <label className="block text-[10px] text-sage-500 mb-1.5">Assign To</label>
                  <select
                    value={modalOwnerId}
                    onChange={(e) => setModalOwnerId(e.target.value)}
                    className="w-full bg-white border border-sage-300 rounded-xl text-sage-900 text-xs px-3 py-2 focus:outline-none focus:border-sage-900"
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
                  <label className="block text-[10px] text-sage-500 mb-1.5">Turnaround Time</label>
                  <div className="flex flex-wrap gap-1.5">
                    {TURNAROUND_OPTIONS.map(opt => (
                      <button
                        key={opt.days}
                        onClick={() => setModalTurnaround(modalTurnaround === opt.days ? null : opt.days)}
                        className={`px-3 py-1.5 text-xs rounded-full transition-colors ${
                          modalTurnaround === opt.days
                            ? 'bg-sage-900 text-sage-100'
                            : 'bg-sage-200 text-sage-500 hover:text-sage-900'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                  {modalTurnaround !== null && (
                    <p className="mt-1.5 text-xs text-sage-500">
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
                <p className="text-xs text-sage-900">{modalError}</p>
              )}
            </div>

            {/* Modal footer */}
            <div className="p-5 border-t border-sage-300 flex items-center justify-between gap-2 flex-shrink-0">
              <div className="flex items-center gap-2">
                {selectedItem.action_status !== 'actioned' && (
                  <button
                    onClick={() => void markActioned(selectedItem)}
                    disabled={modalSaving}
                    className="px-4 py-2 text-xs rounded-full bg-sage-200 text-sage-600 hover:text-sage-900 disabled:opacity-50 transition-colors"
                  >
                    Mark Actioned
                  </button>
                )}
                <button
                  onClick={() => {
                    const params = new URLSearchParams({ location_id: selectedItem.location_id, tab: 'upcoming', legislation_id: selectedItem.legislation_id });
                    navigate(`/app/matcha/compliance?${params.toString()}`);
                  }}
                  className="px-4 py-2 text-xs text-sage-500 hover:text-sage-900 transition-colors"
                >
                  Full View
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={closeModal}
                  className="px-4 py-2 text-xs rounded-full bg-sage-200 text-sage-500 hover:text-sage-900 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => void saveModalChanges()}
                  disabled={modalSaving || (modalOwnerId === (selectedItem.action_owner_id ?? '') && modalTurnaround === null)}
                  className="px-4 py-2 text-xs rounded-full bg-sage-900 text-sage-100 hover:bg-sage-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
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
  const { user, hasFeature } = useAuth();
  const [ptoSummary, setPtoSummary] = useState<PTOSummary | null>(null);
  const [dashStats, setDashStats] = useState<DashboardStats | null>(null);
  const [compliancePendingActions, setCompliancePendingActions] = useState<ComplianceDashboardItem[]>([]);

  useEffect(() => {
    const token = getAccessToken();
    const headers = { Authorization: `Bearer ${token}` };

    if (hasFeature('time_off')) {
      fetch(`${API_BASE}/employees/pto/summary`, { headers })
        .then(r => r.ok ? r.json() : null)
        .then(data => data && setPtoSummary(data))
        .catch(err => console.error('Failed to fetch PTO summary:', err));
    }

    fetch(`${API_BASE}/dashboard/stats`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setDashStats(data))
      .catch(err => console.error('Failed to fetch dashboard stats:', err));
  }, [hasFeature]);

  const showComplianceImpact = user?.role === 'client' && hasFeature('compliance');

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

  const stats = [
    {
      label: 'Active Policies',
      value: dashStats ? String(dashStats.active_policies) : '-',
      change: dashStats?.active_policies === 0 ? 'No policies yet' : 'Active',
      icon: FileText,
      path: '/app/matcha/policies'
    },
    {
      label: 'Pending Signatures',
      value: dashStats ? String(dashStats.pending_signatures) : '-',
      change: dashStats?.pending_signatures === 0 ? 'All signed' : 'Action required',
      icon: Clock,
      path: '/app/matcha/policies'
    },
    {
      label: 'Total Employees',
      value: dashStats ? String(dashStats.total_employees) : '-',
      change: dashStats?.total_employees === 0 ? 'No employees yet' : 'Active',
      icon: Users,
      path: '/app/matcha/employees'
    },
    {
      label: 'Policy Signature Rate',
      value: dashStats ? `${dashStats.compliance_rate}%` : '-',
      change: dashStats?.compliance_rate === 0 ? 'No data yet' : 'Current',
      icon: CheckCircle2,
      path: '/app/matcha/compliance'
    },
  ];

  const complianceRate = dashStats?.compliance_rate ?? 0;

  const dashboardWidgets = [
    { id: 'stats', label: 'Key Metrics', icon: Activity },
    { id: 'compliance', label: 'Compliance Health', icon: ShieldAlert },
    { id: 'compliance_impact', label: 'Compliance Impact', icon: ShieldAlert },
    { id: 'actions', label: 'Pending Actions', icon: Clock },
    { id: 'activity', label: 'System Activity', icon: History },
    { id: 'incidents', label: 'Incident Reports', icon: AlertTriangle },
    { id: 'pto', label: 'Upcoming Time Off', icon: Calendar },
    { id: 'setup', label: 'Quick Setup', icon: Building },
  ];

  return (
    <>
    <OnboardingWizard />
    <div className="-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-6 sm:px-8 lg:px-10 py-10 min-h-screen bg-sage-200">
    <CompanyProfileBanner />
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-4">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
             <div className="px-2.5 py-0.5 bg-sage-100 text-sage-600 text-xs rounded-full">
                Live Overview
             </div>
          </div>
          <h1 className="text-2xl font-bold tracking-tighter text-sage-900 uppercase">
            Command Center
          </h1>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/app/matcha/policies/new')}
            className="px-4 py-2 rounded-full bg-sage-100 text-sage-900 hover:bg-sage-300 text-xs font-medium transition-all"
          >
            New Policy
          </button>
          <button
            onClick={() => navigate('/app/matcha/offer-letters')}
            className="px-4 py-2 bg-sage-900 text-sage-100 hover:bg-sage-800 rounded-full text-xs font-bold transition-all"
          >
            Create Offer
          </button>
        </div>
      </div>

      <WidgetContainer widgets={dashboardWidgets}>
        {(visibleWidgets) => (
          <div className="space-y-6">
            {/* Stats Grid */}
            {visibleWidgets.has('stats') && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {stats.map((stat) => (
                  <button
                    key={stat.label}
                    onClick={() => navigate(stat.path)}
                    className="bg-sage-900 rounded-3xl p-6 hover:bg-sage-800 transition-all group relative overflow-hidden text-left"
                  >
                    <div className="absolute top-0 right-0 p-3 text-sage-800 group-hover:scale-110 transition-all duration-500">
                       <stat.icon className="w-10 h-10" strokeWidth={0.5} />
                    </div>

                    <div className="relative z-10">
                      <div className="text-xs text-sage-600 uppercase tracking-wider mb-3">{stat.label}</div>
                      <div className="text-4xl font-light font-mono text-sage-100 mb-1 tabular-nums">{stat.value}</div>
                      <div className="text-xs text-sage-600">
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
                      className="flex items-center gap-3 p-4 bg-sage-200 rounded-2xl hover:bg-sage-300 transition-all group text-left"
                    >
                      <div className="p-2 bg-sage-300 rounded-xl group-hover:bg-sage-400 transition-colors">
                        <Building className="w-4 h-4 text-sage-900" />
                      </div>
                      <div className="flex-1">
                        <div className="text-sm text-sage-900 font-medium">Company Profile</div>
                        <div className="text-xs text-sage-500 mt-0.5">Set up company info</div>
                      </div>
                      <ArrowUpRight className="w-3.5 h-3.5 text-sage-400 group-hover:text-sage-900 transition-colors" />
                    </button>
                    <button
                      onClick={() => navigate('/app/matcha/employees')}
                      className="flex items-center gap-3 p-4 bg-sage-200 rounded-2xl hover:bg-sage-300 transition-all group text-left"
                    >
                      <div className="p-2 bg-sage-300 rounded-xl group-hover:bg-sage-400 transition-colors">
                        <UserPlus className="w-4 h-4 text-sage-900" />
                      </div>
                      <div className="flex-1">
                        <div className="text-sm text-sage-900 font-medium">Add Employees</div>
                        <div className="text-xs text-sage-500 mt-0.5">Import team via CSV</div>
                      </div>
                      <ArrowUpRight className="w-3.5 h-3.5 text-sage-400 group-hover:text-sage-900 transition-colors" />
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
                          <div className="bg-sage-100 rounded-3xl p-6 h-fit">
                            <h2 className="text-base font-semibold text-sage-900 mb-4">Pending Actions</h2>
                            <div className="space-y-2">
                              {ptoSummary && ptoSummary.pending_count > 0 && (
                                <div
                                  onClick={() => navigate('/app/matcha/pto')}
                                  className="bg-sage-200 rounded-2xl p-4 flex items-start gap-3 cursor-pointer hover:bg-sage-300 transition-colors group"
                                >
                                    <Calendar className="w-4 h-4 text-sage-500 mt-0.5" />
                                    <div className="flex-1">
                                      <div className="text-sm text-sage-900 font-medium mb-0.5">PTO Requests Pending</div>
                                      <div className="text-xs text-sage-500">{ptoSummary.pending_count} request{ptoSummary.pending_count !== 1 ? 's' : ''} awaiting approval</div>
                                    </div>
                                    <ArrowUpRight className="w-3.5 h-3.5 text-sage-400 group-hover:text-sage-900 ml-auto transition-colors" />
                                </div>
                              )}
                              {dashStats?.pending_incidents.map((incident) => (
                                <div
                                  key={incident.id}
                                  onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
                                  className="bg-sage-200 rounded-2xl p-4 flex items-start gap-3 cursor-pointer hover:bg-sage-300 transition-colors group"
                                >
                                    <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-sage-500 animate-pulse flex-shrink-0" />
                                    <div className="flex-1">
                                      <div className="text-sm text-sage-900 font-medium mb-0.5">{incident.title}</div>
                                      <div className="text-xs text-sage-500">{incident.incident_number} &bull; {incident.severity.charAt(0).toUpperCase() + incident.severity.slice(1)} Priority</div>
                                    </div>
                                    <ArrowUpRight className="w-3.5 h-3.5 text-sage-400 group-hover:text-sage-900 ml-auto transition-colors" />
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
                                    className="bg-sage-200 rounded-2xl p-4 flex items-start gap-3 cursor-pointer hover:bg-sage-300 transition-colors group"
                                  >
                                      <div className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${isCritical ? 'bg-sage-900 animate-pulse' : 'bg-sage-500'}`} />
                                      <div className="flex-1">
                                        <div className="text-sm text-sage-900 font-medium mb-0.5">{item.title}</div>
                                        <div className="text-xs text-sage-500">
                                          Compliance &bull; {item.action_owner_name || 'Unassigned'} &bull; {item.sla_state.replace('_', ' ')}
                                        </div>
                                      </div>
                                      <ArrowUpRight className="w-3.5 h-3.5 text-sage-400 group-hover:text-sage-900 ml-auto transition-colors" />
                                  </div>
                                );
                              })}
                              {(!ptoSummary || ptoSummary.pending_count === 0)
                                && (!dashStats || dashStats.pending_incidents.length === 0)
                                && (!showComplianceImpact || compliancePendingActions.length === 0) && (
                                <div className="p-4 text-center">
                                  <CheckCircle2 className="w-5 h-5 text-sage-400 mx-auto mb-1.5" />
                                  <p className="text-sm text-sage-400">All caught up</p>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {visibleWidgets.has('pto') && ptoSummary && ptoSummary.upcoming_time_off > 0 && (
                          <div className="bg-sage-100 rounded-3xl p-6">
                              <div className="flex items-center justify-between mb-4">
                                <h2 className="text-base font-semibold text-sage-900">Upcoming Time Off</h2>
                                <Calendar className="w-4 h-4 text-sage-400" />
                              </div>
                              <div className="text-4xl font-light font-mono text-sage-900 mb-1 tabular-nums">{ptoSummary.upcoming_time_off}</div>
                              <div className="text-xs text-sage-500">employees out (30d)</div>
                              <button
                                onClick={() => navigate('/app/matcha/pto')}
                                className="mt-4 rounded-full bg-sage-200 text-sage-900 hover:bg-sage-300 px-4 py-2 text-xs transition-colors"
                              >
                                View Calendar
                              </button>
                          </div>
                        )}
                      </div>

                      <div className="space-y-4">
                        {visibleWidgets.has('compliance') && (
                          <div className="bg-sage-900 rounded-3xl p-6 relative overflow-hidden group h-fit">
                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-base font-semibold text-sage-100">Policy Signature Coverage</h2>
                                <ShieldAlert className="w-4 h-4 text-sage-600" />
                            </div>

                            <div className="relative w-32 h-32 mx-auto mb-4">
                                <svg className="w-full h-full transform -rotate-90">
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent" className="text-sage-800" />
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent"
                                    strokeDasharray={2 * Math.PI * 58}
                                    strokeDashoffset={(2 * Math.PI * 58) - (complianceRate / 100) * (2 * Math.PI * 58)}
                                    className="text-sage-100 transition-all duration-1000"
                                  />
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                  <span className="text-2xl font-light text-sage-100">{complianceRate > 0 ? `${complianceRate}%` : '--'}</span>
                                  <span className="text-xs text-sage-600 mt-0.5">{complianceRate > 0 ? 'Signed' : 'No data'}</span>
                                </div>
                            </div>

                            {dashStats && dashStats.active_policies > 0 ? (
                              <div className="space-y-2">
                                <div className="flex justify-between text-xs text-sage-600">
                                    <span>Signatures</span>
                                    <span className="text-sage-100">{complianceRate}%</span>
                                </div>
                                <div className="w-full bg-sage-800 h-1 rounded-full overflow-hidden">
                                    <div className="bg-sage-100 h-full transition-all duration-1000" style={{ width: `${complianceRate}%` }} />
                                </div>
                              </div>
                            ) : (
                              <p className="text-xs text-sage-600 text-center">Create policies to track</p>
                            )}
                          </div>
                        )}
                      </div>

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
                        <div className="bg-sage-100 rounded-3xl overflow-hidden">
                          <div className="p-4 border-b border-sage-300 flex justify-between items-center">
                            <h2 className="text-base font-semibold text-sage-900">System Activity</h2>
                            <Activity className="w-4 h-4 text-sage-400" />
                          </div>
                          <div className="divide-y divide-sage-200">
                            {dashStats && dashStats.recent_activity.length > 0 ? (
                              dashStats.recent_activity.map((item, i) => {
                                const ts = new Date(item.timestamp);
                                const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
                                const isToday = new Date().toDateString() === ts.toDateString();
                                const dateLabel = isToday ? 'TODAY' : ts.toLocaleDateString([], { month: 'short', day: 'numeric' }).toUpperCase();
                                return (
                                  <div key={i} className="p-3 flex items-center justify-between hover:bg-sage-200 transition-colors group">
                                    <div className="flex items-center gap-3">
                                      <div className="font-mono text-xs text-sage-400 w-12">
                                        {timeStr}
                                      </div>
                                      <div className="flex items-center gap-2.5">
                                        <div className={`w-1.5 h-1.5 rounded-full ${
                                            item.type === 'success' ? 'bg-sage-900' :
                                            item.type === 'warning' ? 'bg-sage-500 animate-pulse' : 'bg-sage-400'
                                        }`} />
                                        <span className="text-sm text-sage-900">{item.action}</span>
                                      </div>
                                    </div>
                                    <div className="hidden sm:block text-xs text-sage-500 bg-sage-200 px-2 py-0.5 rounded-full">
                                      {dateLabel}
                                    </div>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="p-6 text-center">
                                <Activity className="w-5 h-5 text-sage-400 mx-auto mb-1.5" />
                                <p className="text-sm text-sage-500">No recent activity</p>
                              </div>
                            )}
                          </div>
                          {dashStats && dashStats.recent_activity.length > 0 && (
                            <div className="p-3 border-t border-sage-300 bg-sage-200">
                              <button className="w-full text-center text-xs text-sage-500 hover:text-sage-900 transition-colors">
                                  Full Log
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {visibleWidgets.has('incidents') && dashStats?.incident_summary && dashStats.incident_summary.total_open > 0 && (
                        <div className="bg-sage-100 rounded-3xl overflow-hidden">
                          <div className="p-4 border-b border-sage-300 flex justify-between items-center">
                            <h2 className="text-base font-semibold text-sage-900">Incidents</h2>
                            <ShieldAlert className="w-4 h-4 text-sage-400" />
                          </div>
                          <div className="p-5">
                            <div className="flex items-baseline gap-2.5 mb-4">
                              <span className="text-3xl font-light text-sage-900 tabular-nums">{dashStats.incident_summary.total_open}</span>
                              <span className="text-xs text-sage-500 font-medium">Open Incident{dashStats.incident_summary.total_open !== 1 ? 's' : ''}</span>
                              {dashStats.incident_summary.recent_7_days > 0 && (
                                <span className="ml-auto text-xs bg-sage-200 text-sage-600 px-2 py-0.5 rounded-full">
                                  +{dashStats.incident_summary.recent_7_days}
                                </span>
                              )}
                            </div>
                            <div className="grid grid-cols-4 gap-3">
                              {([
                                { label: 'Crit', count: dashStats.incident_summary.critical, color: 'text-sage-900', bg: 'bg-sage-900' },
                                { label: 'High', count: dashStats.incident_summary.high, color: 'text-sage-700', bg: 'bg-sage-700' },
                                { label: 'Med', count: dashStats.incident_summary.medium, color: 'text-sage-500', bg: 'bg-sage-500' },
                                { label: 'Low', count: dashStats.incident_summary.low, color: 'text-sage-400', bg: 'bg-sage-400' },
                              ] as const).map((sev) => (
                                <div key={sev.label} className="bg-sage-200 rounded-2xl p-3 text-center">
                                  <div className={`text-xl font-light tabular-nums ${sev.count > 0 ? sev.color : 'text-sage-400'}`}>{sev.count}</div>
                                  <div className="flex items-center justify-center gap-1 mt-1">
                                    <span className={`w-1.5 h-1.5 rounded-full ${sev.count > 0 ? sev.bg : 'bg-sage-300'}`} />
                                    <span className="text-[10px] text-sage-500">{sev.label}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                          <div className="p-3 border-t border-sage-300 bg-sage-200">
                            <button
                              onClick={() => navigate('/app/ir/incidents')}
                              className="w-full text-center text-xs text-sage-500 hover:text-sage-900 transition-colors"
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
