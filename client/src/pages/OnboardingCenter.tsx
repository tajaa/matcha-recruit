import { useState, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { onboarding, provisioning, getAccessToken } from '../api/client';
import { useIsLightMode } from '../hooks/useIsLightMode';
import { Mail, CheckCircle, UserX, Clock, ChevronRight } from 'lucide-react';
import type { GoogleWorkspaceConnectionStatus, OnboardingAnalytics, ProvisioningRunListItem, SlackConnectionStatus } from '../types';
import { EmployeeIntake } from '../features/employee-intake';
import OnboardingTemplates from './OnboardingTemplates';
import OnboardingNotificationSettings from './OnboardingNotificationSettings';
import OnboardingPriorities from './OnboardingPriorities';
import CompanyProfile from './CompanyProfile';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { PageShell, TabBar, useTk } from '../components/PageShell';


type Tab = 'workspace' | 'employees' | 'templates' | 'priorities' | 'notifications' | 'runs' | 'profile';

const ONBOARDING_CYCLE_STEPS = [
  {
    id: 1,
    title: 'Prehire Setup',
    icon: 'setup' as const,
    description: 'Define onboarding standards before the hire starts: integrations, templates, owners, and due windows.',
    action: 'Configure workspace integrations and required onboarding templates.',
  },
  {
    id: 2,
    title: 'Create Employee Record',
    icon: 'employee' as const,
    description: 'Create the new hire profile with start date, manager, role details, and employment attributes.',
    action: 'Add the employee record from New Hires or CSV import.',
  },
  {
    id: 3,
    title: 'Send Invitation',
    icon: 'invite' as const,
    description: 'Issue a secure setup invitation so the employee can access the portal and checklist.',
    action: 'Send invitation and track pending vs accepted invites.',
  },
  {
    id: 4,
    title: 'Invitation Accepted',
    icon: 'accepted' as const,
    description: 'The employee activates their account and onboarding work officially moves into execution.',
    action: 'Confirm accepted invite status and begin task execution.',
  },
  {
    id: 5,
    title: 'Onboarding In Progress',
    icon: 'in_progress' as const,
    description: 'Employee, manager, HR, and IT complete required tasks, compliance paperwork, and provisioning steps.',
    action: 'Drive checklist completion and resolve overdue blockers.',
  },
  {
    id: 6,
    title: 'Checklist Complete',
    icon: 'complete' as const,
    description: 'All required onboarding tasks are complete and no critical dependency remains open.',
    action: 'Validate completion and clear any final exceptions.',
  },
  {
    id: 7,
    title: 'Ready For Day 1',
    icon: 'ready' as const,
    description: 'The employee is operationally ready to start with access, compliance, and handoff requirements satisfied.',
    action: 'Track day-one readiness KPI and maintain cycle quality.',
  },
];

function computeOnboardingCycleStep(
  analytics: OnboardingAnalytics | null,
  googleStatus: GoogleWorkspaceConnectionStatus | null,
): number {
  const funnel = analytics?.funnel;
  if (funnel) {
    if ((funnel.ready_for_day1 || 0) > 0) return 7;
    if ((funnel.completed || 0) > 0) return 6;
    if ((funnel.started || 0) > 0) return 5;
    if ((funnel.accepted || 0) > 0) return 4;
    if ((funnel.invited || 0) > 0) return 3;
  }
  if (googleStatus?.status === 'connected') return 2;
  return 1;
}

const API_BASE = import.meta.env.VITE_API_URL || '/api';

interface RecentEmployee {
  id: string;
  first_name: string;
  last_name: string;
  work_email?: string | null;
  email?: string;
  user_id: string | null;
  invitation_status: string | null;
  termination_date: string | null;
  created_at: string;
}

interface OnboardingProgressItem {
  employee_id: string;
  total: number;
  completed: number;
  pending: number;
  has_onboarding: boolean;
}

function RecentHires({ refreshKey }: { refreshKey: number }) {
  const isLight = useIsLightMode();
  const t = useTk();
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<RecentEmployee[]>([]);
  const [progress, setProgress] = useState<Record<string, OnboardingProgressItem>>({});
  const [loading, setLoading] = useState(true);
  const [invitingId, setInvitingId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const token = getAccessToken();
        const [empRes, progRes] = await Promise.all([
          fetch(`${API_BASE}/employees`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API_BASE}/employees/onboarding-progress`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);
        if (!mounted) return;
        if (empRes.ok) {
          const all: RecentEmployee[] = await empRes.json();
          const cutoff = new Date();
          cutoff.setDate(cutoff.getDate() - 30);
          setEmployees(all.filter(e => new Date(e.created_at) >= cutoff));
        }
        if (progRes.ok) {
          setProgress(await progRes.json());
        }
      } catch {
        // non-critical
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, [refreshKey]);

  const handleInvite = async (id: string) => {
    setInvitingId(id);
    try {
      const token = getAccessToken();
      const res = await fetch(`${API_BASE}/employees/${id}/invite`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setEmployees(prev => prev.map(e => e.id === id ? { ...e, invitation_status: 'pending' } : e));
      }
    } catch {
      // ignore
    } finally {
      setInvitingId(null);
    }
  };

  if (loading) {
    return (
      <div className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse py-6 text-center`}>
        Loading recent hires...
      </div>
    );
  }

  if (employees.length === 0) {
    return (
      <div className={`${t.emptyBorder} rounded-2xl flex items-center justify-center py-12`}>
        <p className={`${t.textMuted} text-xs font-mono uppercase tracking-wide`}>
          No employees added in the last 30 days
        </p>
      </div>
    );
  }

  return (
    <div className={`${isLight ? 'bg-stone-100 rounded-2xl' : 'bg-zinc-800 rounded-2xl'} overflow-hidden`}>
      <div className={`px-5 py-3 ${isLight ? 'border-b border-stone-200' : 'border-b border-white/10'}`}>
        <span className={`text-[10px] uppercase tracking-widest font-bold ${t.textMuted}`}>
          Recent Hires ({employees.length})
        </span>
      </div>
      <div className={`divide-y ${t.divide}`}>
        {employees.map(emp => {
          const prog = progress[emp.id];
          const isActive = Boolean(emp.user_id);
          const isTerminated = Boolean(emp.termination_date);
          const isPending = emp.invitation_status === 'pending';
          const canInvite = !isActive && !isTerminated;

          return (
            <div
              key={emp.id}
              onClick={() => navigate(`/app/matcha/employees/${emp.id}`)}
              className={`flex items-center gap-4 px-5 py-3 cursor-pointer ${t.rowHover} transition-colors`}
            >
              {/* Name */}
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-bold ${t.textMain} truncate`}>
                  {emp.first_name} {emp.last_name}
                </p>
                <p className={`text-[10px] ${t.textMuted} truncate`}>
                  {emp.work_email || emp.email || '\u2014'}
                </p>
              </div>

              {/* Onboarding progress */}
              <div className="w-28 flex items-center gap-2">
                {prog?.has_onboarding ? (
                  <>
                    <div className={`w-12 h-1.5 ${isLight ? 'bg-stone-300' : 'bg-zinc-700'} rounded-full overflow-hidden`}>
                      <div
                        className="h-full bg-emerald-500 rounded-full transition-all"
                        style={{ width: `${(prog.completed / prog.total) * 100}%` }}
                      />
                    </div>
                    <span className={`text-[10px] ${t.textMuted} font-mono`}>
                      {prog.completed}/{prog.total}
                    </span>
                  </>
                ) : (
                  <span className={`text-[10px] ${t.textFaint} uppercase tracking-wider`}>No tasks</span>
                )}
              </div>

              {/* Status / Invite */}
              <div className="w-28 flex justify-end" onClick={e => e.stopPropagation()}>
                {isTerminated ? (
                  <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] uppercase tracking-wider font-bold ${isLight ? 'bg-stone-200 text-stone-500' : 'bg-zinc-700 text-zinc-400'}`}>
                    <UserX size={10} /> Terminated
                  </span>
                ) : isActive ? (
                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] uppercase tracking-wider font-bold bg-emerald-950/40 text-emerald-400 border border-emerald-500/30">
                    <CheckCircle size={10} /> Active
                  </span>
                ) : isPending ? (
                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] uppercase tracking-wider font-bold bg-zinc-100 text-zinc-900 border border-zinc-300">
                    <Clock size={10} /> Invited
                  </span>
                ) : canInvite ? (
                  <button
                    onClick={() => handleInvite(emp.id)}
                    disabled={invitingId === emp.id}
                    className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] uppercase tracking-wider font-bold transition-colors disabled:opacity-50 ${isLight ? 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800' : 'bg-zinc-100 text-zinc-900 hover:bg-white'}`}
                  >
                    <Mail size={10} />
                    {invitingId === emp.id ? '...' : 'Send Invite'}
                  </button>
                ) : null}
              </div>

              <ChevronRight size={14} className={t.textFaint} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ONBOARDING_TABS: { id: Tab; label: string }[] = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'employees', label: 'Add Employees' },
  { id: 'templates', label: 'Templates' },
  { id: 'priorities', label: 'Priorities' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'runs', label: 'Activity' },
  { id: 'profile', label: 'Company Profile' },
];

export default function OnboardingCenter() {
  const isLight = useIsLightMode();
  const t = useTk();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>('workspace');
  const [analytics, setAnalytics] = useState<OnboardingAnalytics | null>(null);
  const [analyticsError, setAnalyticsError] = useState('');

  // Workspace Tab State
  const [loadingGoogle, setLoadingGoogle] = useState(true);
  const [googleStatus, setGoogleStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleStatusError, setGoogleStatusError] = useState('');
  const [loadingSlack, setLoadingSlack] = useState(true);
  const [slackStatus, setSlackStatus] = useState<SlackConnectionStatus | null>(null);
  const [slackStatusError, setSlackStatusError] = useState('');

  // Activity Tab State
  const [runs, setRuns] = useState<ProvisioningRunListItem[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState('');
  const [runsProviderFilter, setRunsProviderFilter] = useState<string>('');
  const [runsStatusFilter, setRunsStatusFilter] = useState<string>('');
  const [intakeRefreshKey, setIntakeRefreshKey] = useState(0);

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && ['workspace', 'employees', 'templates', 'priorities', 'notifications', 'runs', 'profile'].includes(tab)) {
      setActiveTab(tab as Tab);
    } else {
      setSearchParams({ tab: 'workspace' }, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    let mounted = true;
    const loadAnalytics = async () => {
      setAnalyticsError('');
      try {
        const data = await onboarding.getAnalytics();
        if (mounted) setAnalytics(data);
      } catch (err) {
        if (!mounted) return;
        setAnalyticsError(err instanceof Error ? err.message : 'Could not load onboarding analytics');
      }
    };
    loadAnalytics();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (activeTab === 'workspace') {
      let mounted = true;
      const loadGoogleStatus = async () => {
        setLoadingGoogle(true);
        setLoadingSlack(true);
        setGoogleStatusError('');
        setSlackStatusError('');
        try {
          const [google, slack] = await Promise.all([
            provisioning.getGoogleWorkspaceStatus(),
            provisioning.getSlackStatus(),
          ]);
          if (!mounted) return;
          setGoogleStatus(google);
          setSlackStatus(slack);
        } catch (err) {
          if (!mounted) return;
          const message = err instanceof Error ? err.message : 'Could not load provisioning status';
          setGoogleStatusError(message);
          setSlackStatusError(message);
        } finally {
          if (mounted) {
            setLoadingGoogle(false);
            setLoadingSlack(false);
          }
        }
      };
      loadGoogleStatus();
      return () => {
        mounted = false;
      };
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'runs') {
      let mounted = true;
      const loadRuns = async () => {
        setRunsLoading(true);
        setRunsError('');
        try {
          const data = await provisioning.listRuns({
            provider: runsProviderFilter || undefined,
            status: runsStatusFilter || undefined,
            limit: 100,
          });
          if (mounted) setRuns(data);
        } catch (err) {
          if (mounted) setRunsError(err instanceof Error ? err.message : 'Could not load activity');
        } finally {
          if (mounted) setRunsLoading(false);
        }
      };
      loadRuns();
      return () => { mounted = false; };
    }
  }, [activeTab, runsProviderFilter, runsStatusFilter]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  const googleBadge = useMemo(() => {
    if (loadingGoogle) {
      return { label: 'Checking', tone: t.badgeDefault };
    }
    if (!googleStatus || googleStatus.status === 'disconnected') {
      return { label: 'Not Connected', tone: t.badgeDefault };
    }
    if (googleStatus.status === 'connected') {
      return { label: 'Connected', tone: t.badgeConnected };
    }
    if (googleStatus.status === 'error') {
      return { label: 'Needs Attention', tone: t.badgeError };
    }
    return { label: googleStatus.status.toUpperCase(), tone: t.badgeDefault };
  }, [loadingGoogle, googleStatus, t]);

  const slackBadge = useMemo(() => {
    if (loadingSlack) {
      return { label: 'Checking', tone: t.badgeDefault };
    }
    if (!slackStatus || slackStatus.status === 'disconnected') {
      return { label: 'Not Connected', tone: t.badgeDefault };
    }
    if (slackStatus.status === 'connected') {
      return { label: 'Connected', tone: t.badgeConnected };
    }
    if (slackStatus.status === 'error') {
      return { label: 'Needs Attention', tone: t.badgeError };
    }
    return { label: slackStatus.status.toUpperCase(), tone: t.badgeDefault };
  }, [loadingSlack, slackStatus, t]);

  const activeCycleStep = useMemo(
    () => computeOnboardingCycleStep(analytics, googleStatus),
    [analytics, googleStatus],
  );

  function statusClass(status: string) {
    if (status === 'completed') return t.statusCompleted;
    if (status === 'failed') return t.statusFailed;
    if (status === 'needs_action') return t.statusAmber;
    if (status === 'running') return t.statusRunning;
    return t.statusDefault;
  }

  return (
    <PageShell
      title="Onboarding Center"
      subtitle="Manage integrations, new hires, and onboarding workflows."
      guideId="onboarding-center"
      guideTourAttr="onboarding-center-guide"
    >
      <LifecycleWizard
        steps={ONBOARDING_CYCLE_STEPS}
        activeStep={activeCycleStep}
        title="Expected Onboarding Cycle"
        storageKey="onboarding-cycle-collapsed-v1"
      />
      {analyticsError && (
        <div className={`${t.alertWarn} px-4 py-3 text-[10px] font-mono uppercase tracking-[0.15em] rounded-xl`}>
          Analytics temporarily unavailable: {analyticsError}
        </div>
      )}

      {/* Analytics Dashboard */}
      {analytics && (analytics.funnel.invited > 0 || analytics.funnel.accepted > 0 || analytics.funnel.started > 0 || analytics.funnel.completed > 0 || analytics.funnel.ready_for_day1 > 0) && (
        <div className="space-y-4">
          {/* Funnel Bar */}
          <div className={`${t.card} p-5`}>
            <div className={`${t.label} mb-4`}>Onboarding Funnel</div>
            {(() => {
              const stages = [
                { key: 'invited', label: 'Invited', count: analytics.funnel.invited, color: isLight ? 'bg-stone-400' : 'bg-zinc-600' },
                { key: 'accepted', label: 'Accepted', count: analytics.funnel.accepted, color: isLight ? 'bg-blue-400' : 'bg-blue-500' },
                { key: 'started', label: 'Started', count: analytics.funnel.started, color: isLight ? 'bg-amber-400' : 'bg-amber-500' },
                { key: 'completed', label: 'Completed', count: analytics.funnel.completed, color: isLight ? 'bg-emerald-400' : 'bg-emerald-500' },
                { key: 'ready', label: 'Ready for Day 1', count: analytics.funnel.ready_for_day1, color: isLight ? 'bg-emerald-600' : 'bg-emerald-400' },
              ];
              const total = Math.max(...stages.map(s => s.count), 1);
              return (
                <div className="space-y-3">
                  {/* Segmented bar */}
                  <div className={`flex h-3 rounded-full overflow-hidden ${isLight ? 'bg-stone-200' : 'bg-zinc-800'}`}>
                    {stages.map((s) => {
                      const pct = (s.count / total) * 100;
                      if (pct === 0) return null;
                      return (
                        <div
                          key={s.key}
                          className={`${s.color} transition-all duration-500`}
                          style={{ width: `${pct}%` }}
                          title={`${s.label}: ${s.count}`}
                        />
                      );
                    })}
                  </div>
                  {/* Stage labels */}
                  <div className="flex flex-wrap gap-x-6 gap-y-2">
                    {stages.map((s, i) => {
                      const prev = i > 0 ? stages[i - 1].count : null;
                      const convPct = prev && prev > 0 ? Math.round((s.count / prev) * 100) : null;
                      return (
                        <div key={s.key} className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${s.color}`} />
                          <span className={`text-[11px] ${t.textMuted}`}>{s.label}</span>
                          <span className={`text-[11px] font-bold ${t.textMain}`}>{s.count}</span>
                          {convPct !== null && (
                            <span className={`text-[10px] ${t.textFaint}`}>({convPct}%)</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
          </div>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className={`${t.card} p-4`}>
              <div className={`${t.label} mb-2`}>Time to Ready (p50)</div>
              <div className={`text-xl font-bold tracking-tight ${t.textMain}`}>
                {analytics.kpis.time_to_ready_p50_days != null ? `${analytics.kpis.time_to_ready_p50_days}d` : '—'}
              </div>
            </div>
            <div className={`${t.card} p-4`}>
              <div className={`${t.label} mb-2`}>Time to Ready (p90)</div>
              <div className={`text-xl font-bold tracking-tight ${t.textMain}`}>
                {analytics.kpis.time_to_ready_p90_days != null ? `${analytics.kpis.time_to_ready_p90_days}d` : '—'}
              </div>
            </div>
            <div className={`${t.card} p-4`}>
              <div className={`${t.label} mb-2`}>Complete Before Start</div>
              <div className={`text-xl font-bold tracking-tight ${t.textMain}`}>
                {analytics.kpis.completion_before_start_rate != null ? `${Math.round(analytics.kpis.completion_before_start_rate)}%` : '—'}
              </div>
            </div>
            <div className={`${t.card} p-4`}>
              <div className={`${t.label} mb-2`}>Automation Success</div>
              <div className={`text-xl font-bold tracking-tight ${t.textMain}`}>
                {analytics.kpis.automation_success_rate != null ? `${Math.round(analytics.kpis.automation_success_rate)}%` : '—'}
              </div>
            </div>
          </div>

          {/* Bottlenecks */}
          {analytics.bottlenecks.length > 0 && (
            <div className={`${t.card} p-5`}>
              <div className={`${t.label} mb-3`}>Bottlenecks</div>
              <div className={`divide-y ${t.divide}`}>
                {analytics.bottlenecks.map((b, i) => (
                  <div key={i} className="flex items-center justify-between py-2.5 first:pt-0 last:pb-0">
                    <span className={`text-xs ${t.textMain}`}>{b.task_title}</span>
                    <div className="flex items-center gap-4">
                      <span className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>
                        {b.overdue_count} overdue
                      </span>
                      <span className={`text-[10px] font-mono ${t.textFaint}`}>
                        avg {b.avg_days_overdue.toFixed(1)}d
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <TabBar tabs={ONBOARDING_TABS} activeTab={activeTab} onTabChange={handleTabChange} tourPrefix="onboarding-tab" />

      {/* Tab Content */}
      <div className="py-6">
        {activeTab === 'workspace' && (
          <div className="space-y-6">
            <div className={`${t.alertInfo} p-4 text-xs ${t.textDim} leading-relaxed`}>
              Connect external systems to automate employee provisioning. Credentials are encrypted and scoped to your organization.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Google Workspace Card */}
              <section data-tour="onboarding-workspace-google-card" className={`${t.cardDark} p-6 ${t.cardDarkHover} transition-all group relative overflow-hidden text-left flex flex-col justify-between`}>
                <div className={`absolute top-0 right-0 p-3 ${t.cardDarkGhost} group-hover:scale-110 transition-all duration-500`}>
                  {/* Decorative faint icon */}
                  <div className="w-10 h-10 opacity-20"></div> 
                </div>

                <div className="relative z-10 space-y-4 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className={`${t.labelOnDark} mb-1`}>Google Workspace</div>
                      <p className={`text-[10px] ${t.textMuted}`}>Provision Gmail & groups.</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-0.5 text-[9px] uppercase tracking-widest font-bold ${googleBadge.tone}`}>
                      {googleBadge.label}
                    </span>
                  </div>

                  {googleStatusError && (
                    <p className="text-[10px] text-red-500 bg-red-500/10 px-2 py-1 rounded">Status check failed: {googleStatusError}</p>
                  )}

                  {googleStatus && (
                    <div className={`space-y-1 text-[11px] font-mono ${t.textMuted}`}>
                      <p>Mode: <span className={t.textMain}>{googleStatus.mode || 'not configured'}</span></p>
                      <p>Domain: <span className={t.textMain}>{googleStatus.domain || 'not set'}</span></p>
                      <p>Auto-provision: <span className={t.textMain}>{googleStatus.auto_provision_on_employee_create ? 'on' : 'off'}</span></p>
                    </div>
                  )}
                </div>

                <div className="relative z-10 mt-6">
                  <button
                    data-tour="onboarding-configure-google"
                    onClick={() => navigate('/app/matcha/google-workspace')}
                    className={`px-4 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl transition-colors`}
                  >
                    Configure
                  </button>
                </div>
              </section>

              {/* Slack Card */}
              <section data-tour="onboarding-workspace-slack-card" className={`${t.cardDark} p-6 ${t.cardDarkHover} transition-all group relative overflow-hidden text-left flex flex-col justify-between`}>
                <div className={`absolute top-0 right-0 p-3 ${t.cardDarkGhost} group-hover:scale-110 transition-all duration-500`}>
                   <div className="w-10 h-10 opacity-20"></div>
                </div>

                <div className="relative z-10 space-y-4 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className={`${t.labelOnDark} mb-1`}>Slack</div>
                      <p className={`text-[10px] ${t.textMuted}`}>Auto-invite, channels, & defaults.</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-0.5 text-[9px] uppercase tracking-widest font-bold ${slackBadge.tone}`}>
                      {slackBadge.label}
                    </span>
                  </div>

                  {slackStatusError && (
                    <p className="text-[10px] text-red-500 bg-red-500/10 px-2 py-1 rounded">Status check failed: {slackStatusError}</p>
                  )}

                  {slackStatus && (
                    <div className={`space-y-1 text-[11px] font-mono ${t.textMuted}`}>
                      <p>Workspace: <span className={t.textMain} title={slackStatus.workspace_url || ''}>{slackStatus.workspace_url ? slackStatus.workspace_url.replace('https://','').split('.')[0] : 'not set'}</span></p>
                      <p>Team: <span className={t.textMain}>{slackStatus.slack_team_name || 'not connected'}</span></p>
                      <p>Auto-invite: <span className={t.textMain}>{slackStatus.auto_invite_on_employee_create ? 'on' : 'off'}</span></p>
                    </div>
                  )}
                </div>

                <div className="relative z-10 mt-6">
                  <button
                    data-tour="onboarding-configure-slack"
                    onClick={() => navigate('/app/matcha/slack-provisioning')}
                    className={`px-4 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl transition-colors`}
                  >
                    Configure
                  </button>
                </div>
              </section>

              {/* Toast Card (Coming Soon) */}
              <section className={`${t.cardDark} p-6 ${t.comingSoon} relative overflow-hidden text-left flex flex-col justify-between`}>
                 <div className={`absolute top-0 right-0 p-3 ${t.cardDarkGhost}`}>
                   <div className="w-10 h-10 opacity-20"></div>
                </div>

                <div className="relative z-10 space-y-4 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className={`${t.labelOnDark} mb-1`}>Toast</div>
                      <p className={`text-[10px] ${t.textMuted}`}>POS & location mapping.</p>
                    </div>
                    <span className={`rounded-full px-2.5 py-0.5 text-[9px] uppercase tracking-widest font-bold ${t.badgeDefault}`}>
                      Soon
                    </span>
                  </div>
                </div>
                
                <div className="relative z-10 mt-6">
                  <button
                    disabled
                    className={`px-4 py-2 ${t.btnDisabled} text-[10px] font-bold uppercase tracking-wider rounded-xl`}
                  >
                    Configure
                  </button>
                </div>
              </section>
            </div>
          </div>
        )}

        {activeTab === 'employees' && (
          <div className="space-y-6">
            <EmployeeIntake onCreated={() => setIntakeRefreshKey(k => k + 1)} />
            <RecentHires refreshKey={intakeRefreshKey} />
          </div>
        )}

        {activeTab === 'templates' && (
          <div className="space-y-6">
            <OnboardingTemplates />
          </div>
        )}

        {activeTab === 'priorities' && (
          <div className="space-y-6">
            <OnboardingPriorities />
          </div>
        )}

        {activeTab === 'notifications' && (
          <div className="space-y-6">
            <OnboardingNotificationSettings />
          </div>
        )}

        {activeTab === 'runs' && (
          <div data-tour="onboarding-runs-panel" className="space-y-4">
            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3">
              <select
                value={runsProviderFilter}
                onChange={(e) => setRunsProviderFilter(e.target.value)}
                className={t.selectCls}
              >
                <option value="">All Providers</option>
                <option value="slack">Slack</option>
                <option value="google_workspace">Google Workspace</option>
              </select>
              <select
                value={runsStatusFilter}
                onChange={(e) => setRunsStatusFilter(e.target.value)}
                className={t.selectCls}
              >
                <option value="">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="needs_action">Needs Action</option>
                <option value="running">Running</option>
                <option value="pending">Pending</option>
              </select>
              {(runsProviderFilter || runsStatusFilter) && (
                <button
                  onClick={() => { setRunsProviderFilter(''); setRunsStatusFilter(''); }}
                  className={`text-[10px] uppercase tracking-wider ${t.textMuted} hover:${t.textMain}`}
                >
                  Clear
                </button>
              )}
              <span className={`ml-auto text-[10px] ${t.textMuted} uppercase tracking-wider`}>
                {runs.length} run{runs.length !== 1 ? 's' : ''}
              </span>
            </div>

            {runsError && (
              <div className={`${t.alertError} px-4 py-3 text-xs rounded-xl`}>
                {runsError}
              </div>
            )}

            {runsLoading ? (
              <p className={`text-xs ${t.textMuted} font-mono uppercase tracking-wider animate-pulse py-8 text-center`}>
                Loading activity...
              </p>
            ) : runs.length === 0 ? (
              <div className={`flex items-center justify-center h-48 ${t.emptyBorder} rounded-2xl`}>
                <div className="text-center">
                  <p className={`${t.textMuted} text-xs font-mono uppercase tracking-wide`}>No provisioning runs found</p>
                  <p className={`${t.textFaint} text-[10px] mt-2`}>Runs appear here when employees are created or provisioned manually.</p>
                </div>
              </div>
            ) : (
              <div className={`${t.cardDark} overflow-hidden shadow-lg`}>
                {/* Header row */}
                <div className={`grid grid-cols-[1fr_120px_100px_100px_140px] gap-3 px-4 py-3 ${t.labelOnDark} border-b border-white/5`}>
                  <span>Employee</span>
                  <span>Provider</span>
                  <span className="text-center">Status</span>
                  <span className="text-center">Trigger</span>
                  <span className="text-right">Time</span>
                </div>
                <div className="divide-y divide-white/5">
                {runs.map((run) => (
                    <div
                      key={run.run_id}
                      className={`grid grid-cols-[1fr_120px_100px_100px_140px] gap-3 px-3 py-3 ${t.rowHover} transition-colors`}
                    >
                      <div className="min-w-0">
                        <p className={`text-xs ${t.textMain} truncate`}>{run.employee_name || '—'}</p>
                        <p className={`text-[10px] ${t.textMuted} truncate`}>{run.employee_email || run.employee_id}</p>
                        {run.last_error && (
                          <p className="text-[10px] text-red-500 mt-0.5 truncate" title={run.last_error}>
                            {run.last_error}
                          </p>
                        )}
                      </div>
                      <span className={`text-[10px] ${t.textMuted} self-center`}>
                        {run.provider === 'google_workspace' ? 'Google WS' : run.provider.charAt(0).toUpperCase() + run.provider.slice(1)}
                      </span>
                      <span className={`self-center px-2 py-0.5 text-[10px] uppercase tracking-wider rounded-lg border w-fit ${statusClass(run.status)}`}>
                        {run.status}
                      </span>
                      <span className={`text-[10px] ${t.textMuted} self-center capitalize`}>
                        {run.trigger_source.replace(/_/g, ' ')}
                      </span>
                      <span className={`text-[10px] ${t.textMuted} self-center font-mono`}>
                        {new Date(run.created_at).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'profile' && (
          <div className="space-y-6">
            <CompanyProfile />
          </div>
        )}
      </div>
    </PageShell>
  );
}
