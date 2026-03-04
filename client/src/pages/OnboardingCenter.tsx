import { useState, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { onboarding, provisioning } from '../api/client';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { useIsLightMode } from '../hooks/useIsLightMode';
import type { GoogleWorkspaceConnectionStatus, OnboardingAnalytics, ProvisioningRunListItem, SlackConnectionStatus } from '../types';
import Employees from './Employees';
import OnboardingTemplates from './OnboardingTemplates';
import OnboardingNotificationSettings from './OnboardingNotificationSettings';
import OnboardingPriorities from './OnboardingPriorities';
import CompanyProfile from './CompanyProfile';
import { LifecycleWizard } from '../components/LifecycleWizard';

type Tab = 'workspace' | 'employees' | 'templates' | 'priorities' | 'notifications' | 'runs' | 'profile';

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  cardBorder: 'border border-stone-200 bg-stone-100 rounded-2xl',
  innerEl: 'bg-stone-200 rounded-xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  borderTab: 'border-stone-400/40',
  divide: 'divide-stone-200',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-500 hover:text-stone-700 hover:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnDisabled: 'border border-stone-300 text-stone-400 cursor-not-allowed',
  selectCls: 'bg-white border border-stone-300 text-xs text-zinc-900 px-3 py-1.5 rounded-xl focus:outline-none focus:border-stone-400',
  rowHover: 'hover:bg-stone-50',
  alertInfo: 'border border-stone-200 bg-stone-100 rounded-xl',
  alertWarn: 'border border-amber-300 bg-amber-50 text-amber-700',
  alertError: 'border border-red-300 bg-red-50 text-red-700',
  emptyBorder: 'border border-dashed border-stone-300 bg-stone-100',
  badgeDefault: 'border-stone-300 bg-stone-200 text-stone-600',
  badgeConnected: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  badgeError: 'border-red-300 bg-red-50 text-red-700',
  badgeAmber: 'border-amber-300 bg-amber-50 text-amber-700',
  statusCompleted: 'bg-emerald-50 text-emerald-700 border-emerald-300',
  statusFailed: 'bg-red-50 text-red-700 border-red-300',
  statusAmber: 'bg-amber-50 text-amber-700 border-amber-300',
  statusRunning: 'bg-blue-50 text-blue-700 border-blue-300',
  statusDefault: 'bg-stone-200 text-stone-600 border-stone-300',
  comingSoon: 'opacity-75',
};

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardBorder: 'border border-white/10 bg-zinc-900/50 rounded-2xl',
  innerEl: 'bg-zinc-800 rounded-xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  borderTab: 'border-white/10',
  divide: 'divide-white/10',
  tabActive: 'border-zinc-100 text-zinc-100',
  tabInactive: 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnDisabled: 'border border-white/10 text-zinc-600 cursor-not-allowed',
  selectCls: 'bg-zinc-800 border border-white/10 text-xs text-zinc-100 px-3 py-1.5 rounded-xl focus:outline-none focus:border-white/20',
  rowHover: 'hover:bg-white/5',
  alertInfo: 'border border-white/10 bg-zinc-900/50 rounded-xl',
  alertWarn: 'border border-amber-500/30 bg-amber-950/30 text-amber-400',
  alertError: 'border border-red-500/30 bg-red-950/30 text-red-400',
  emptyBorder: 'border border-dashed border-white/10 bg-zinc-900/30',
  badgeDefault: 'border-zinc-700 bg-zinc-800 text-zinc-400',
  badgeConnected: 'border-emerald-500/30 bg-emerald-950/40 text-emerald-400',
  badgeError: 'border-red-500/30 bg-red-950/40 text-red-400',
  badgeAmber: 'border-amber-500/30 bg-amber-950/40 text-amber-400',
  statusCompleted: 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30',
  statusFailed: 'bg-red-950/40 text-red-400 border-red-500/30',
  statusAmber: 'bg-amber-950/40 text-amber-400 border-amber-500/30',
  statusRunning: 'bg-blue-950/40 text-blue-400 border-blue-500/30',
  statusDefault: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  comingSoon: 'opacity-50',
};

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

export default function OnboardingCenter() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
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
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
      <div className="max-w-7xl mx-auto space-y-6 overflow-x-hidden">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-6">
        <div className="text-center sm:text-left">
          <h1 className={`text-2xl sm:text-3xl font-bold tracking-tighter ${t.textMain} uppercase`}>Onboarding Center</h1>
          <p className={`text-[10px] sm:text-xs ${t.textMuted} mt-2 font-mono uppercase tracking-wide`}>
            Manage integrations, new hires, and onboarding workflows.
          </p>
        </div>
        <div className="flex justify-center sm:justify-end" data-tour="onboarding-center-guide">
          <FeatureGuideTrigger guideId="onboarding-center" />
        </div>
      </div>

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

      {/* Tabs */}
      <div className={`border-b ${t.borderTab} -mx-4 px-4 sm:mx-0 sm:px-0`}>
        <nav className="-mb-px flex space-x-8 overflow-x-auto pb-px no-scrollbar">
          {[
            { id: 'workspace', label: 'Workspace' },
            { id: 'employees', label: 'New Hires' },
            { id: 'templates', label: 'Templates' },
            { id: 'priorities', label: 'Priorities' },
            { id: 'notifications', label: 'Notifications' },
            { id: 'runs', label: 'Activity' },
            { id: 'profile', label: 'Company Profile' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id as Tab)}
              data-tour={`onboarding-tab-${tab.id}`}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors whitespace-nowrap ${
                activeTab === tab.id ? t.tabActive : t.tabInactive
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="py-6">
        {activeTab === 'workspace' && (
          <div className="space-y-6">
            <div className={`${t.alertInfo} p-4 text-xs ${t.textDim} leading-relaxed`}>
              Connect external systems to automate employee provisioning. Credentials are encrypted and scoped to your organization.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Google Workspace Card */}
              <section data-tour="onboarding-workspace-google-card" className={`${t.cardBorder} p-5 space-y-4`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className={`text-sm font-semibold tracking-wide ${t.textMain}`}>Google Workspace</h2>
                    <p className={`text-xs ${t.textMuted} mt-1`}>Provision Gmail & groups.</p>
                  </div>
                  <span className={`rounded-lg border px-2 py-1 text-[10px] uppercase tracking-wider ${googleBadge.tone}`}>
                    {googleBadge.label}
                  </span>
                </div>

                {googleStatusError && (
                  <p className="text-xs text-red-500">Status check failed: {googleStatusError}</p>
                )}

                {googleStatus && (
                  <div className={`space-y-1 text-[11px] ${t.textMuted}`}>
                    <p>Mode: <span className={t.textMain}>{googleStatus.mode || 'not configured'}</span></p>
                    <p>Domain: <span className={t.textMain}>{googleStatus.domain || 'not set'}</span></p>
                    <p>Auto-provision: <span className={t.textMain}>{googleStatus.auto_provision_on_employee_create ? 'on' : 'off'}</span></p>
                  </div>
                )}

                <button
                  data-tour="onboarding-configure-google"
                  onClick={() => navigate('/app/matcha/google-workspace')}
                  className={`w-full px-3 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl transition-colors`}
                >
                  Configure
                </button>
              </section>

              {/* Slack Card */}
              <section data-tour="onboarding-workspace-slack-card" className={`${t.cardBorder} p-5 space-y-4`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className={`text-sm font-semibold tracking-wide ${t.textMain}`}>Slack</h2>
                    <p className={`text-xs ${t.textMuted} mt-1`}>Auto-invite, channels, and workspace defaults.</p>
                  </div>
                  <span className={`rounded-lg border px-2 py-1 text-[10px] uppercase tracking-wider ${slackBadge.tone}`}>
                    {slackBadge.label}
                  </span>
                </div>

                {slackStatusError && (
                  <p className="text-xs text-red-500">Status check failed: {slackStatusError}</p>
                )}

                {slackStatus && (
                  <div className={`space-y-1 text-[11px] ${t.textMuted}`}>
                    <p>Workspace: <span className={t.textMain}>{slackStatus.workspace_url || 'not set'}</span></p>
                    <p>Team: <span className={t.textMain}>{slackStatus.slack_team_name || 'not connected'}</span></p>
                    <p>Auto-invite: <span className={t.textMain}>{slackStatus.auto_invite_on_employee_create ? 'on' : 'off'}</span></p>
                  </div>
                )}

                <button
                  data-tour="onboarding-configure-slack"
                  onClick={() => navigate('/app/matcha/slack-provisioning')}
                  className={`w-full px-3 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl transition-colors`}
                >
                  Configure
                </button>
              </section>

              {/* Toast Card (Coming Soon) */}
              <section className={`${t.cardBorder} p-5 space-y-4 ${t.comingSoon}`}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className={`text-sm font-semibold tracking-wide ${t.textMain}`}>Toast</h2>
                    <p className={`text-xs ${t.textMuted} mt-1`}>POS & location mapping.</p>
                  </div>
                  <span className={`rounded-lg border px-2 py-1 text-[10px] uppercase tracking-wider ${t.badgeDefault}`}>
                    Soon
                  </span>
                </div>
                <button
                  disabled
                  className={`w-full px-3 py-2 ${t.btnDisabled} text-[10px] font-bold uppercase tracking-wider rounded-xl`}
                >
                  Configure
                </button>
              </section>
            </div>
          </div>
        )}

        {activeTab === 'employees' && (
          <div className="space-y-6">
            <Employees mode="onboarding" />
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
              <div className={`${t.card} overflow-hidden`}>
                {/* Header row */}
                <div className={`grid grid-cols-[1fr_120px_100px_100px_140px] gap-3 px-3 py-2 text-[10px] uppercase tracking-wider ${t.textFaint} font-bold border-b ${t.border}`}>
                  <span>Employee</span>
                  <span>Provider</span>
                  <span>Status</span>
                  <span>Trigger</span>
                  <span>Time</span>
                </div>
                <div className={`${t.divide}`}>
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
      </div>
    </div>
  );
}
