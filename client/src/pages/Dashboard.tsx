import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowUpRight, Users, FileText, CheckCircle2, Clock, Activity, ShieldAlert, Calendar, Building, UserPlus, LayoutDashboard, History, AlertTriangle, MapPin, ChevronRight, TriangleAlert, X, ExternalLink } from 'lucide-react';
import { getAccessToken } from '../api/client';
import { OnboardingWizard } from '../components/OnboardingWizard';
import { Collapsible } from '../components/Collapsible';
import { Tabs } from '../components/Tabs';
import { WidgetContainer } from '../components/WidgetContainer';
import { complianceAPI, COMPLIANCE_CATEGORY_LABELS } from '../api/compliance';
import type { ComplianceDashboard, ComplianceDashboardItem, ComplianceActionPlanUpdate, AssignableUser } from '../api/compliance';
import { useAuth } from '../context/AuthContext';

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

const SEVERITY_STYLES: Record<string, { dot: string; border: string; badge: string; label: string }> = {
  critical: {
    dot: 'bg-red-500 animate-pulse',
    border: 'border-red-500/20 hover:border-red-500/40',
    badge: 'bg-red-500/10 text-red-400 border border-red-500/20',
    label: 'Critical',
  },
  warning: {
    dot: 'bg-amber-500',
    border: 'border-amber-500/20 hover:border-amber-500/40',
    badge: 'bg-amber-500/10 text-amber-400 border border-amber-500/20',
    label: 'Warning',
  },
  info: {
    dot: 'bg-blue-400',
    border: 'border-white/10 hover:border-white/20',
    badge: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',
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

function ComplianceDashboardWidget() {
  const navigate = useNavigate();
  const { user: currentUser } = useAuth();
  const [horizon, setHorizon] = useState<HorizonDays>(90);
  const [data, setData] = useState<ComplianceDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [savingAlertId, setSavingAlertId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

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

  const saveModalChanges = async () => {
    if (!selectedItem?.alert_id) return;
    setModalSaving(true);
    setModalError(null);
    try {
      const payload: ComplianceActionPlanUpdate = {};
      if (modalOwnerId !== (selectedItem.action_owner_id ?? '')) {
        payload.action_owner_id = modalOwnerId || null;
      }
      if (modalTurnaround !== null) {
        const due = new Date();
        due.setDate(due.getDate() + modalTurnaround);
        payload.action_due_date = due.toISOString().slice(0, 10);
      }
      if (Object.keys(payload).length > 0) {
        await complianceAPI.updateAlertActionPlan(selectedItem.alert_id, payload);
        loadDashboard(horizon);
      }
      closeModal();
    } catch {
      setModalError('Could not save changes');
    } finally {
      setModalSaving(false);
    }
  };

  const markActioned = async (item: ComplianceDashboardItem) => {
    if (!item.alert_id) return;
    setModalSaving(true);
    setModalError(null);
    try {
      await complianceAPI.updateAlertActionPlan(item.alert_id, { mark_actioned: true });
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
      return {
        label: 'Overdue',
        badge: 'bg-red-500/10 text-red-400 border border-red-500/20',
        dueText: 'text-red-400',
      };
    }
    if (slaState === 'due_soon') {
      return {
        label: 'Due Soon',
        badge: 'bg-amber-500/10 text-amber-400 border border-amber-500/20',
        dueText: 'text-amber-400',
      };
    }
    if (slaState === 'completed') {
      return {
        label: 'Completed',
        badge: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
        dueText: 'text-emerald-400',
      };
    }
    if (slaState === 'unassigned') {
      return {
        label: 'Unassigned',
        badge: 'bg-zinc-700/50 text-zinc-300 border border-zinc-600',
        dueText: 'text-zinc-400',
      };
    }
    return {
      label: 'On Track',
      badge: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',
      dueText: 'text-zinc-400',
    };
  };

  const updateActionPlan = async (item: ComplianceDashboardItem, payload: ComplianceActionPlanUpdate) => {
    if (!item.alert_id) return;
    try {
      setActionError(null);
      setSavingAlertId(item.alert_id);
      await complianceAPI.updateAlertActionPlan(item.alert_id, payload);
      loadDashboard(horizon);
    } catch {
      setActionError('Could not update action plan');
    } finally {
      setSavingAlertId(null);
    }
  };

  const criticalCount = data?.coming_up.filter(i => i.severity === 'critical').length ?? 0;
  const warningCount = data?.coming_up.filter(i => i.severity === 'warning').length ?? 0;

  return (
    <div className="border border-white/10 bg-zinc-900/30">
      {/* Header */}
      <div className="p-3 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-3.5 h-3.5 text-emerald-500" />
          <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">Compliance Impact</h2>
          {criticalCount > 0 && (
            <span className="px-1.5 py-0.5 text-[7px] font-mono uppercase tracking-widest bg-red-500/10 text-red-400 border border-red-500/20">
              {criticalCount} critical
            </span>
          )}
        </div>
        {/* Horizon selector */}
        <div className="flex gap-px">
          {([30, 60, 90] as HorizonDays[]).map(d => (
            <button
              key={d}
              onClick={() => setHorizon(d)}
              className={`px-2 py-0.5 text-[7px] font-mono uppercase tracking-widest transition-colors ${
                horizon === d
                  ? 'bg-white text-black'
                  : 'text-zinc-500 hover:text-white border border-white/10'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* KPI row */}
      {data && (
        <div className="grid grid-cols-3 md:grid-cols-7 gap-px bg-white/5 border-b border-white/10">
          {[
            { label: 'Locations', value: data.kpis.total_locations, color: 'text-white' },
            { label: 'Unread Alerts', value: data.kpis.unread_alerts, color: data.kpis.unread_alerts > 0 ? 'text-amber-400' : 'text-white' },
            { label: 'Critical', value: data.kpis.critical_alerts, color: data.kpis.critical_alerts > 0 ? 'text-red-400' : 'text-white' },
            { label: 'At Risk', value: data.kpis.employees_at_risk, color: data.kpis.employees_at_risk > 0 ? 'text-amber-400' : 'text-zinc-500' },
            { label: 'Overdue', value: data.kpis.overdue_actions, color: data.kpis.overdue_actions > 0 ? 'text-red-400' : 'text-zinc-500' },
            { label: 'Assigned', value: data.kpis.assigned_actions, color: data.kpis.assigned_actions > 0 ? 'text-emerald-400' : 'text-zinc-500' },
            { label: 'Unassigned', value: data.kpis.unassigned_actions, color: data.kpis.unassigned_actions > 0 ? 'text-amber-400' : 'text-zinc-500' },
          ].map(kpi => (
            <div key={kpi.label} className="bg-zinc-950 p-2 text-center">
              <div className={`text-lg font-light tabular-nums ${kpi.color}`}>{kpi.value}</div>
              <div className="text-[7px] uppercase tracking-widest text-zinc-500 mt-0.5">{kpi.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Coming up list */}
      <div className="divide-y divide-white/5">
        {actionError && (
          <div className="p-2 border-b border-red-500/20 bg-red-500/10">
            <p className="text-[8px] text-red-300 uppercase tracking-wider">{actionError}</p>
          </div>
        )}

        {loading && (
          <div className="p-6 text-center">
            <div className="w-4 h-4 border border-zinc-700 border-t-white rounded-full animate-spin mx-auto mb-2" />
            <p className="text-[9px] text-zinc-500 uppercase tracking-wider">Loading</p>
          </div>
        )}

        {error && !loading && (
          <div className="p-4 text-center">
            <TriangleAlert className="w-4 h-4 text-zinc-700 mx-auto mb-1.5" />
            <p className="text-[9px] text-zinc-500 uppercase tracking-wider">Failed to load</p>
          </div>
        )}

        {!loading && !error && data && data.coming_up.length === 0 && (
          <div className="p-4 text-center">
            <CheckCircle2 className="w-4 h-4 text-zinc-700 mx-auto mb-1.5" />
            <p className="text-[9px] text-zinc-500 uppercase tracking-wider">No upcoming changes in {horizon}d window</p>
          </div>
        )}

        {!loading && !error && data && data.coming_up.map((item) => {
          const sev = SEVERITY_STYLES[item.severity] ?? SEVERITY_STYLES.info;
          const categoryLabel = item.category ? (COMPLIANCE_CATEGORY_LABELS[item.category] ?? item.category) : null;
          const daysLabel = item.days_until != null
            ? item.days_until <= 0 ? 'Today' : `${item.days_until}d`
            : '—';
          const daysColor = item.days_until != null && item.days_until <= 30
            ? 'text-red-400'
            : item.days_until != null && item.days_until <= 60
            ? 'text-amber-400'
            : 'text-zinc-400';
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
              className={`w-full text-left p-3 border-l-2 ${sev.border} bg-zinc-950 hover:bg-zinc-900 transition-all group`}
            >
              <div className="flex items-start gap-2.5">
                <div className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${sev.dot}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="text-[11px] text-zinc-200 group-hover:text-white transition-colors font-medium leading-tight truncate">
                      {item.title}
                    </span>
                    <span className={`text-[9px] font-mono tabular-nums flex-shrink-0 ${daysColor}`}>
                      {daysLabel}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="flex items-center gap-1 text-zinc-500">
                      <MapPin className="w-2.5 h-2.5" />
                      <span className="text-[8px] uppercase tracking-wider">{item.location_name}</span>
                    </div>

                    {categoryLabel && (
                      <span className="text-[7px] font-mono uppercase tracking-widest text-zinc-600 border border-white/10 px-1 py-px">
                        {categoryLabel}
                      </span>
                    )}

                    <span className={`text-[7px] font-mono uppercase tracking-widest px-1 py-px ${sev.badge}`}>
                      {sev.label}
                    </span>
                    <span className={`text-[7px] font-mono uppercase tracking-widest px-1 py-px ${sla.badge}`}>
                      {sla.label}
                    </span>
                  </div>

                  <div className="mt-1.5 space-y-1">
                    <div className="text-[9px] text-zinc-400">
                      <span className="text-zinc-600">Next:</span> {item.next_action || 'Review legal impact and assign an owner.'}
                    </div>
                    <div className="flex items-center gap-3 flex-wrap text-[8px] text-zinc-500">
                      <span>Owner: <span className="text-zinc-300">{item.action_owner_name || 'Unassigned'}</span></span>
                      <span className={sla.dueText}>Due: {dueLabel}</span>
                    </div>

                    {item.estimated_financial_impact && (
                      <div className="text-[8px] text-red-300/80">
                        Exposure: {item.estimated_financial_impact}
                      </div>
                    )}

                    {item.affected_employee_count > 0 && (
                      <div className="mt-1 flex items-center gap-1.5">
                        <Users className="w-2.5 h-2.5 text-zinc-600" />
                        <span className="text-[8px] text-zinc-500">
                          {item.affected_employee_count} employee{item.affected_employee_count !== 1 ? 's' : ''}
                          {item.affected_employee_sample.length > 0 && (
                            <span className="text-zinc-600">
                              {' '}— {item.affected_employee_sample.slice(0, 3).join(', ')}
                              {item.affected_employee_count > 3 ? ` +${item.affected_employee_count - 3} more` : ''}
                            </span>
                          )}
                        </span>
                        <span className="text-[7px] text-zinc-700 font-mono">~est</span>
                      </div>
                    )}

                  </div>
                </div>

                <ChevronRight className="w-3 h-3 text-zinc-600 group-hover:text-zinc-400 transition-colors flex-shrink-0 mt-0.5" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      {data && data.coming_up.length > 0 && (
        <div className="p-2.5 border-t border-white/10 bg-white/5 flex items-center justify-between">
          {(criticalCount > 0 || warningCount > 0) && (
            <span className="text-[7px] font-mono text-zinc-600 uppercase tracking-widest">
              {criticalCount > 0 && `${criticalCount} critical`}
              {criticalCount > 0 && warningCount > 0 && ' · '}
              {warningCount > 0 && `${warningCount} warning`}
            </span>
          )}
          <button
            onClick={() => navigate('/app/matcha/compliance?tab=upcoming')}
            className="ml-auto text-[8px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors"
          >
            Full Compliance View
          </button>
        </div>
      )}

      {/* Compliance Action Modal */}
      {selectedItem && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}
        >
          <div className="w-full max-w-lg bg-zinc-950 border border-white/10 shadow-2xl flex flex-col max-h-[90vh]">
            {/* Modal header */}
            <div className="flex items-start justify-between p-4 border-b border-white/10 flex-shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${SEVERITY_STYLES[selectedItem.severity]?.dot ?? 'bg-zinc-500'}`} />
                <span className="text-[11px] font-semibold text-white leading-tight">{selectedItem.title}</span>
              </div>
              <button onClick={closeModal} className="ml-3 flex-shrink-0 text-zinc-500 hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="overflow-y-auto flex-1 p-4 space-y-4">
              {/* Meta badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <div className="flex items-center gap-1 text-zinc-500">
                  <MapPin className="w-2.5 h-2.5" />
                  <span className="text-[8px] uppercase tracking-wider">{selectedItem.location_name}</span>
                </div>
                {selectedItem.category && (
                  <span className="text-[7px] font-mono uppercase tracking-widest text-zinc-600 border border-white/10 px-1 py-px">
                    {COMPLIANCE_CATEGORY_LABELS[selectedItem.category] ?? selectedItem.category}
                  </span>
                )}
                <span className={`text-[7px] font-mono uppercase tracking-widest px-1 py-px ${SEVERITY_STYLES[selectedItem.severity]?.badge}`}>
                  {SEVERITY_STYLES[selectedItem.severity]?.label}
                </span>
                {selectedItem.effective_date && (
                  <span className="text-[7px] font-mono text-zinc-500 border border-white/5 px-1 py-px">
                    Effective {new Date(`${selectedItem.effective_date}T00:00:00`).toLocaleDateString()}
                    {selectedItem.days_until != null && (
                      <span className={selectedItem.days_until <= 30 ? ' text-red-400' : selectedItem.days_until <= 60 ? ' text-amber-400' : ' text-zinc-400'}>
                        {' '}· {selectedItem.days_until <= 0 ? 'Today' : `${selectedItem.days_until}d`}
                      </span>
                    )}
                  </span>
                )}
              </div>

              {/* Description */}
              {selectedItem.description && (
                <div className="bg-zinc-900/50 border border-white/5 p-3">
                  <p className="text-[9px] text-zinc-400 leading-relaxed">{selectedItem.description}</p>
                </div>
              )}

              {/* Next action / playbook */}
              {(selectedItem.next_action || selectedItem.recommended_playbook) && (
                <div className="space-y-1">
                  {selectedItem.next_action && (
                    <div className="text-[9px] text-zinc-400">
                      <span className="text-[7px] uppercase tracking-widest text-zinc-600 block mb-0.5">Recommended Action</span>
                      {selectedItem.next_action}
                    </div>
                  )}
                  {selectedItem.recommended_playbook && (
                    <div className="text-[9px] text-zinc-400">
                      <span className="text-[7px] uppercase tracking-widest text-zinc-600 block mb-0.5">Playbook</span>
                      {selectedItem.recommended_playbook}
                    </div>
                  )}
                </div>
              )}

              {/* Affected employees */}
              {selectedItem.affected_employee_count > 0 && (
                <div className="flex items-center gap-1.5">
                  <Users className="w-3 h-3 text-zinc-600" />
                  <span className="text-[8px] text-zinc-500">
                    {selectedItem.affected_employee_count} employee{selectedItem.affected_employee_count !== 1 ? 's' : ''} affected
                    {selectedItem.affected_employee_sample.length > 0 && (
                      <span className="text-zinc-600"> — {selectedItem.affected_employee_sample.slice(0, 3).join(', ')}{selectedItem.affected_employee_count > 3 ? ` +${selectedItem.affected_employee_count - 3} more` : ''}</span>
                    )}
                  </span>
                </div>
              )}

              {/* Financial exposure */}
              {selectedItem.estimated_financial_impact && (
                <div className="text-[8px] text-red-300/80 bg-red-500/5 border border-red-500/10 px-2 py-1">
                  Exposure: {selectedItem.estimated_financial_impact}
                </div>
              )}

              {/* Source link */}
              {selectedItem.source_url && (
                <a
                  href={selectedItem.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-[8px] text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  <ExternalLink className="w-2.5 h-2.5" />
                  View source
                </a>
              )}

              {/* Divider */}
              <div className="border-t border-white/5" />

              {/* Assign */}
              {selectedItem.alert_id && (
                <div className="space-y-3">
                  <div>
                    <label className="block text-[7px] uppercase tracking-widest text-zinc-500 mb-1.5">Assign To</label>
                    <select
                      value={modalOwnerId}
                      onChange={(e) => setModalOwnerId(e.target.value)}
                      className="w-full bg-zinc-900 border border-white/10 text-zinc-200 text-[10px] px-2 py-1.5 focus:outline-none focus:border-white/20"
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
                    <label className="block text-[7px] uppercase tracking-widest text-zinc-500 mb-1.5">Turnaround Time</label>
                    <div className="flex flex-wrap gap-1.5">
                      {TURNAROUND_OPTIONS.map(opt => (
                        <button
                          key={opt.days}
                          onClick={() => setModalTurnaround(modalTurnaround === opt.days ? null : opt.days)}
                          className={`px-2 py-1 text-[8px] font-mono uppercase tracking-widest border transition-colors ${
                            modalTurnaround === opt.days
                              ? 'bg-white text-black border-white'
                              : 'border-white/10 text-zinc-400 hover:border-white/20 hover:text-zinc-200'
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                    {modalTurnaround !== null && (
                      <p className="mt-1.5 text-[8px] text-zinc-500">
                        Due date will be set to {(() => {
                          const d = new Date();
                          d.setDate(d.getDate() + modalTurnaround);
                          return d.toLocaleDateString();
                        })()} · reminder email sent when due approaches
                      </p>
                    )}
                  </div>
                </div>
              )}

              {modalError && (
                <p className="text-[8px] text-red-400 uppercase tracking-wider">{modalError}</p>
              )}
            </div>

            {/* Modal footer */}
            <div className="p-4 border-t border-white/10 flex items-center justify-between gap-2 flex-shrink-0">
              <div className="flex items-center gap-2">
                {selectedItem.action_status !== 'actioned' && selectedItem.alert_id && (
                  <button
                    onClick={() => void markActioned(selectedItem)}
                    disabled={modalSaving}
                    className="px-3 py-1.5 text-[8px] uppercase tracking-widest border border-emerald-500/30 text-emerald-400 hover:text-emerald-300 hover:border-emerald-400/50 disabled:opacity-50 transition-colors"
                  >
                    Mark Actioned
                  </button>
                )}
                <button
                  onClick={() => {
                    const params = new URLSearchParams({ location_id: selectedItem.location_id, tab: 'upcoming', legislation_id: selectedItem.legislation_id });
                    navigate(`/app/matcha/compliance?${params.toString()}`);
                  }}
                  className="px-3 py-1.5 text-[8px] uppercase tracking-widest text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  Full View
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={closeModal}
                  className="px-3 py-1.5 text-[8px] uppercase tracking-widest border border-white/10 text-zinc-400 hover:text-white hover:border-white/20 transition-colors"
                >
                  Cancel
                </button>
                {selectedItem.alert_id && (
                  <button
                    onClick={() => void saveModalChanges()}
                    disabled={modalSaving || (modalOwnerId === (selectedItem.action_owner_id ?? '') && modalTurnaround === null)}
                    className="px-3 py-1.5 text-[8px] uppercase tracking-widest bg-white text-black hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {modalSaving ? 'Saving…' : 'Save'}
                  </button>
                )}
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

    fetch(`${API_BASE}/employees/pto/summary`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setPtoSummary(data))
      .catch(err => console.error('Failed to fetch PTO summary:', err));

    fetch(`${API_BASE}/dashboard/stats`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => data && setDashStats(data))
      .catch(err => console.error('Failed to fetch dashboard stats:', err));
  }, []);

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
      color: 'text-emerald-500',
      path: '/app/matcha/policies'
    },
    {
      label: 'Pending Signatures',
      value: dashStats ? String(dashStats.pending_signatures) : '-',
      change: dashStats?.pending_signatures === 0 ? 'All signed' : 'Action required',
      icon: Clock,
      color: 'text-amber-500',
      path: '/app/matcha/policies'
    },
    {
      label: 'Total Employees',
      value: dashStats ? String(dashStats.total_employees) : '-',
      change: dashStats?.total_employees === 0 ? 'No employees yet' : 'Active',
      icon: Users,
      color: 'text-white',
      path: '/app/matcha/employees'
    },
    {
      label: 'Policy Signature Rate',
      value: dashStats ? `${dashStats.compliance_rate}%` : '-',
      change: dashStats?.compliance_rate === 0 ? 'No data yet' : 'Current',
      icon: CheckCircle2,
      color: 'text-emerald-500',
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
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-white/10 pb-4">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
             <div className="px-1.5 py-0.5 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[8px] uppercase tracking-widest font-mono rounded">
                Live Overview
             </div>
          </div>
          <h1 className="text-2xl font-bold tracking-tighter text-white uppercase">
            Command Center
          </h1>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/app/matcha/policies/new')}
            className="px-4 py-2 border border-white/20 hover:bg-white hover:text-black text-[10px] font-mono uppercase tracking-widest transition-all"
          >
            New Policy
          </button>
          <button
            onClick={() => navigate('/app/matcha/offer-letters')}
            className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] font-mono uppercase tracking-widest transition-all font-bold"
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
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10">
                {stats.map((stat) => (
                  <button
                    key={stat.label}
                    onClick={() => navigate(stat.path)}
                    className="bg-zinc-950 p-4 hover:bg-zinc-900 transition-all group relative overflow-hidden text-left"
                  >
                    <div className="absolute top-0 right-0 p-3 opacity-5 group-hover:opacity-10 group-hover:scale-110 transition-all duration-500">
                       <stat.icon className="w-10 h-10 text-white" strokeWidth={0.5} />
                    </div>

                    <div className="relative z-10">
                      <div className="flex items-center gap-2 mb-2">
                         <div className={`p-1 rounded bg-white/5 ${stat.color}`}>
                            <stat.icon className="w-3 h-3" />
                         </div>
                         <span className="text-[8px] uppercase tracking-[0.2em] text-zinc-500 font-bold">{stat.label}</span>
                      </div>

                      <div className="text-xl font-light text-white mb-0.5 tabular-nums tracking-tight group-hover:text-emerald-400 transition-colors">{stat.value}</div>
                      <div className="flex items-center gap-2 text-[8px] font-mono text-zinc-500 uppercase">
                         <span className="w-1 h-1 bg-zinc-700 rounded-full" />
                         {stat.change}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}


            {/* Quick Setup — shown for new businesses with no employees and no policies */}
            {visibleWidgets.has('setup') && dashStats && dashStats.total_employees === 0 && dashStats.active_policies === 0 && (
              <Collapsible title="Quick Setup" icon={Activity}>
                <div className="p-4 bg-zinc-900/10">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <button
                      onClick={() => navigate('/app/matcha/company')}
                      className="flex items-center gap-3 p-3 border border-white/10 hover:border-white/30 hover:bg-white/5 transition-all group text-left"
                    >
                      <div className="p-1.5 bg-white/5 group-hover:bg-white/10 transition-colors">
                        <Building className="w-3.5 h-3.5 text-zinc-400 group-hover:text-white transition-colors" />
                      </div>
                      <div className="flex-1">
                        <div className="text-[11px] text-white font-medium group-hover:text-white transition-colors">Company Profile</div>
                        <div className="text-[8px] text-zinc-500 uppercase tracking-wider mt-0.5">Set up company info</div>
                      </div>
                      <ArrowUpRight className="w-3 h-3 text-zinc-600 group-hover:text-white transition-colors" />
                    </button>
                    <button
                      onClick={() => navigate('/app/matcha/employees')}
                      className="flex items-center gap-3 p-3 border border-white/10 hover:border-white/30 hover:bg-white/5 transition-all group text-left"
                    >
                      <div className="p-1.5 bg-white/5 group-hover:bg-white/10 transition-colors">
                        <UserPlus className="w-3.5 h-3.5 text-zinc-400 group-hover:text-white transition-colors" />
                      </div>
                      <div className="flex-1">
                        <div className="text-[11px] text-white font-medium group-hover:text-white transition-colors">Add Employees</div>
                        <div className="text-[8px] text-zinc-500 uppercase tracking-wider mt-0.5">Import team via CSV</div>
                      </div>
                      <ArrowUpRight className="w-3 h-3 text-zinc-600 group-hover:text-white transition-colors" />
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
            >
              {(activeTab) => (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  {activeTab === 'overview' && (
                    <>
                      <div className="lg:col-span-2 space-y-4">
                        {visibleWidgets.has('actions') && (
                          <div className="border border-white/10 bg-zinc-900/30 p-4 h-fit">
                            <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em] mb-3">Pending Actions</h2>
                            <div className="space-y-1.5">
                              {ptoSummary && ptoSummary.pending_count > 0 && (
                                <div
                                  onClick={() => navigate('/app/matcha/pto')}
                                  className="p-2.5 bg-amber-500/10 border border-amber-500/20 flex items-start gap-3 cursor-pointer hover:bg-amber-500/20 transition-colors"
                                >
                                    <Calendar className="w-3.5 h-3.5 text-amber-500 mt-0.5" />
                                    <div className="flex-1">
                                      <div className="text-[11px] text-amber-200 font-medium mb-0.5">PTO Requests Pending</div>
                                      <div className="text-[9px] text-amber-500/70">{ptoSummary.pending_count} request{ptoSummary.pending_count !== 1 ? 's' : ''} awaiting approval</div>
                                    </div>
                                    <ArrowUpRight className="w-3 h-3 text-amber-500 ml-auto" />
                                </div>
                              )}
                              {dashStats?.pending_incidents.map((incident) => (
                                <div
                                  key={incident.id}
                                  onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
                                  className="p-2.5 bg-amber-500/10 border border-amber-500/20 flex items-start gap-3 cursor-pointer hover:bg-amber-500/20 transition-colors"
                                >
                                    <div className="mt-1.5 w-1 h-1 rounded-full bg-amber-500 animate-pulse" />
                                    <div className="flex-1">
                                      <div className="text-[11px] text-amber-200 font-medium mb-0.5">{incident.title}</div>
                                      <div className="text-[9px] text-amber-500/70">{incident.incident_number} &bull; {incident.severity.charAt(0).toUpperCase() + incident.severity.slice(1)} Priority</div>
                                    </div>
                                    <ArrowUpRight className="w-3 h-3 text-amber-500 ml-auto" />
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
                                    className={`p-2.5 border flex items-start gap-3 cursor-pointer transition-colors ${
                                      isCritical
                                        ? 'bg-red-500/10 border-red-500/20 hover:bg-red-500/20'
                                        : 'bg-amber-500/10 border-amber-500/20 hover:bg-amber-500/20'
                                    }`}
                                  >
                                      <div className={`mt-1.5 w-1 h-1 rounded-full ${isCritical ? 'bg-red-500 animate-pulse' : 'bg-amber-500'}`} />
                                      <div className="flex-1">
                                        <div className={`text-[11px] font-medium mb-0.5 ${isCritical ? 'text-red-200' : 'text-amber-200'}`}>{item.title}</div>
                                        <div className={`text-[9px] ${isCritical ? 'text-red-300/70' : 'text-amber-500/70'}`}>
                                          Compliance &bull; {item.action_owner_name || 'Unassigned'} &bull; {item.sla_state.replace('_', ' ')}
                                        </div>
                                      </div>
                                      <ArrowUpRight className={`w-3 h-3 ml-auto ${isCritical ? 'text-red-400' : 'text-amber-500'}`} />
                                  </div>
                                );
                              })}
                              {(!ptoSummary || ptoSummary.pending_count === 0)
                                && (!dashStats || dashStats.pending_incidents.length === 0)
                                && (!showComplianceImpact || compliancePendingActions.length === 0) && (
                                <div className="p-3 text-center">
                                  <CheckCircle2 className="w-4 h-4 text-zinc-700 mx-auto mb-1.5" />
                                  <p className="text-[9px] text-zinc-500 uppercase tracking-wider">All caught up</p>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                        
                        {visibleWidgets.has('pto') && ptoSummary && ptoSummary.upcoming_time_off > 0 && (
                          <div className="border border-white/10 bg-zinc-900/30 p-4">
                              <div className="flex items-center justify-between mb-3">
                                <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">Upcoming Time Off</h2>
                                <Calendar className="w-3.5 h-3.5 text-zinc-500" />
                              </div>
                              <div className="text-xl font-light text-white mb-0.5">{ptoSummary.upcoming_time_off}</div>
                              <div className="text-[9px] text-zinc-500 uppercase tracking-wider">employees out (30d)</div>
                              <button
                                onClick={() => navigate('/app/matcha/pto')}
                                className="mt-3 w-full text-center py-1.5 border border-white/10 text-[8px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white hover:border-white/30 transition-colors"
                              >
                                View Calendar
                              </button>
                          </div>
                        )}
                      </div>

                      <div className="space-y-4">
                        {visibleWidgets.has('compliance') && (
                          <div className="border border-white/10 bg-zinc-900/30 p-4 relative overflow-hidden group h-fit">
                            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-full blur-[40px] pointer-events-none" />

                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">Policy Signature Coverage</h2>
                                <ShieldAlert className="w-3.5 h-3.5 text-emerald-500" />
                            </div>

                            <div className="relative w-32 h-32 mx-auto mb-4">
                                <svg className="w-full h-full transform -rotate-90">
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent" className="text-zinc-800" />
                                  <circle cx="64" cy="64" r="58" stroke="currentColor" strokeWidth="8" fill="transparent"
                                    strokeDasharray={2 * Math.PI * 58}
                                    strokeDashoffset={(2 * Math.PI * 58) - (complianceRate / 100) * (2 * Math.PI * 58)}
                                    className="text-emerald-500 transition-all duration-1000"
                                  />
                                </svg>
                                <div className="absolute inset-0 flex flex-col items-center justify-center">
                                  <span className="text-2xl font-light text-white">{complianceRate > 0 ? `${complianceRate}%` : '--'}</span>
                                  <span className="text-[8px] uppercase tracking-widest text-zinc-500 mt-0.5">{complianceRate > 0 ? 'Signed' : 'No data'}</span>
                                </div>
                            </div>

                            {dashStats && dashStats.active_policies > 0 ? (
                              <div className="space-y-2">
                                <div className="flex justify-between text-[8px] text-zinc-400 uppercase tracking-wider">
                                    <span>Signatures</span>
                                    <span className="text-white">{complianceRate}%</span>
                                </div>
                                <div className="w-full bg-zinc-800 h-1 rounded-full overflow-hidden">
                                    <div className="bg-emerald-500 h-full transition-all duration-1000" style={{ width: `${complianceRate}%` }} />
                                </div>
                              </div>
                            ) : (
                              <p className="text-[8px] text-zinc-600 text-center uppercase tracking-wider">Create policies to track</p>
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
                        <div className="border border-white/10 bg-zinc-900/30">
                          <div className="p-3 border-b border-white/10 flex justify-between items-center">
                            <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">System Activity</h2>
                            <Activity className="w-3.5 h-3.5 text-zinc-500" />
                          </div>
                          <div className="divide-y divide-white/5">
                            {dashStats && dashStats.recent_activity.length > 0 ? (
                              dashStats.recent_activity.map((item, i) => {
                                const ts = new Date(item.timestamp);
                                const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
                                const isToday = new Date().toDateString() === ts.toDateString();
                                const dateLabel = isToday ? 'TODAY' : ts.toLocaleDateString([], { month: 'short', day: 'numeric' }).toUpperCase();
                                return (
                                  <div key={i} className="p-2.5 flex items-center justify-between hover:bg-white/5 transition-colors group">
                                    <div className="flex items-center gap-3">
                                      <div className="font-mono text-[8px] text-zinc-500 w-12">
                                        {timeStr}
                                      </div>
                                      <div className="flex items-center gap-2.5">
                                        <div className={`w-1 h-1 rounded-full ${
                                            item.type === 'success' ? 'bg-emerald-500' :
                                            item.type === 'warning' ? 'bg-amber-500 animate-pulse' : 'bg-zinc-600'
                                        }`} />
                                        <span className="text-[11px] text-zinc-300 group-hover:text-white transition-colors">{item.action}</span>
                                      </div>
                                    </div>
                                    <div className="hidden sm:block text-[8px] font-mono text-zinc-600 uppercase tracking-widest border border-white/5 px-1.5 py-0.5 rounded">
                                      {dateLabel}
                                    </div>
                                  </div>
                                );
                              })
                            ) : (
                              <div className="p-4 text-center">
                                <Activity className="w-5 h-5 text-zinc-700 mx-auto mb-1.5" />
                                <p className="text-[11px] text-zinc-500">No recent activity</p>
                              </div>
                            )}
                          </div>
                          {dashStats && dashStats.recent_activity.length > 0 && (
                            <div className="p-2.5 border-t border-white/10 bg-white/5">
                              <button className="w-full text-center text-[8px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors">
                                  Full Log
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                      {visibleWidgets.has('incidents') && dashStats?.incident_summary && dashStats.incident_summary.total_open > 0 && (
                        <div className="border border-white/10 bg-zinc-900/30">
                          <div className="p-3 border-b border-white/10 flex justify-between items-center">
                            <h2 className="text-[9px] font-bold text-white uppercase tracking-[0.2em]">Incidents</h2>
                            <ShieldAlert className="w-3.5 h-3.5 text-zinc-500" />
                          </div>
                          <div className="p-4">
                            <div className="flex items-baseline gap-2.5 mb-4">
                              <span className="text-2xl font-light text-white tabular-nums">{dashStats.incident_summary.total_open}</span>
                              <span className="text-[8px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Open Incident{dashStats.incident_summary.total_open !== 1 ? 's' : ''}</span>
                              {dashStats.incident_summary.recent_7_days > 0 && (
                                <span className="ml-auto text-[8px] font-mono text-amber-500 border border-amber-500/20 bg-amber-500/10 px-1.5 py-0.5 rounded">
                                  +{dashStats.incident_summary.recent_7_days}
                                </span>
                              )}
                            </div>
                            <div className="grid grid-cols-4 gap-px bg-white/10">
                              {([
                                { label: 'Crit', count: dashStats.incident_summary.critical, color: 'text-red-400', bg: 'bg-red-500' },
                                { label: 'High', count: dashStats.incident_summary.high, color: 'text-orange-400', bg: 'bg-orange-500' },
                                { label: 'Med', count: dashStats.incident_summary.medium, color: 'text-amber-400', bg: 'bg-amber-500' },
                                { label: 'Low', count: dashStats.incident_summary.low, color: 'text-zinc-400', bg: 'bg-zinc-500' },
                              ] as const).map((sev) => (
                                <div key={sev.label} className="bg-zinc-950 p-2 text-center">
                                  <div className={`text-lg font-light tabular-nums ${sev.count > 0 ? sev.color : 'text-zinc-700'}`}>{sev.count}</div>
                                  <div className="flex items-center justify-center gap-1 mt-1">
                                    <span className={`w-1 h-1 rounded-full ${sev.count > 0 ? sev.bg : 'bg-zinc-800'}`} />
                                    <span className="text-[7px] uppercase tracking-widest text-zinc-500">{sev.label}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                          <div className="p-2.5 border-t border-white/10 bg-white/5">
                            <button
                              onClick={() => navigate('/app/ir/incidents')}
                              className="w-full text-center text-[8px] uppercase tracking-[0.2em] text-zinc-400 hover:text-white transition-colors"
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
    </>
  );
}

export default Dashboard;
