import { useState, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { onboarding, provisioning } from '../api/client';
import { FeatureGuideTrigger } from '../features/feature-guides';
import type { GoogleWorkspaceConnectionStatus, OnboardingAnalytics } from '../types';
import Employees from './Employees';
import OnboardingTemplates from './OnboardingTemplates';
import CompanyProfile from './CompanyProfile';

type Tab = 'workspace' | 'employees' | 'templates' | 'runs' | 'profile';

function statusTone(status: string): string {
  if (status === 'connected') return 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200';
  if (status === 'error') return 'border-red-500/40 bg-red-950/30 text-red-200';
  if (status === 'needs_action') return 'border-amber-500/40 bg-amber-950/30 text-amber-200';
  return 'border-zinc-700 bg-zinc-900/70 text-zinc-300';
}

type OnboardingCycleStep = {
  id: number;
  title: string;
  icon: string;
  description: string;
  action: string;
};

const ONBOARDING_CYCLE_STEPS: OnboardingCycleStep[] = [
  {
    id: 1,
    title: 'Prehire Setup',
    icon: '⚙️',
    description: 'Define onboarding standards before the hire starts: integrations, templates, owners, and due windows.',
    action: 'Configure workspace integrations and required onboarding templates.',
  },
  {
    id: 2,
    title: 'Create Employee Record',
    icon: '👤',
    description: 'Create the new hire profile with start date, manager, role details, and employment attributes.',
    action: 'Add the employee record from New Hires or CSV import.',
  },
  {
    id: 3,
    title: 'Send Invitation',
    icon: '🔗',
    description: 'Issue a secure setup invitation so the employee can access the portal and checklist.',
    action: 'Send invitation and track pending vs accepted invites.',
  },
  {
    id: 4,
    title: 'Invitation Accepted',
    icon: '✅',
    description: 'The employee activates their account and onboarding work officially moves into execution.',
    action: 'Confirm accepted invite status and begin task execution.',
  },
  {
    id: 5,
    title: 'Onboarding In Progress',
    icon: '🔐',
    description: 'Employee, manager, HR, and IT complete required tasks, compliance paperwork, and provisioning steps.',
    action: 'Drive checklist completion and resolve overdue blockers.',
  },
  {
    id: 6,
    title: 'Checklist Complete',
    icon: '🤝',
    description: 'All required onboarding tasks are complete and no critical dependency remains open.',
    action: 'Validate completion and clear any final exceptions.',
  },
  {
    id: 7,
    title: 'Ready For Day 1',
    icon: '🏁',
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
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>('workspace');
  const [analytics, setAnalytics] = useState<OnboardingAnalytics | null>(null);
  const [analyticsError, setAnalyticsError] = useState('');
  const cycleStorageKey = 'onboarding-cycle-collapsed-v1';
  const [cycleCollapsed, setCycleCollapsed] = useState(() => {
    try {
      return localStorage.getItem(cycleStorageKey) === 'true';
    } catch {
      return false;
    }
  });

  // Workspace Tab State
  const [loadingGoogle, setLoadingGoogle] = useState(true);
  const [googleStatus, setGoogleStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleStatusError, setGoogleStatusError] = useState('');

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && ['workspace', 'employees', 'templates', 'runs', 'profile'].includes(tab)) {
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
        setGoogleStatusError('');
        try {
          const status = await provisioning.getGoogleWorkspaceStatus();
          if (mounted) setGoogleStatus(status);
        } catch (err) {
          if (!mounted) return;
          setGoogleStatusError(err instanceof Error ? err.message : 'Could not load Google status');
        } finally {
          if (mounted) setLoadingGoogle(false);
        }
      };
      loadGoogleStatus();
      return () => {
        mounted = false;
      };
    }
  }, [activeTab]);

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  const googleBadge = useMemo(() => {
    if (loadingGoogle) {
      return { label: 'Checking', tone: 'border-zinc-700 bg-zinc-900/70 text-zinc-300' };
    }
    if (!googleStatus || googleStatus.status === 'disconnected') {
      return { label: 'Not Connected', tone: 'border-zinc-700 bg-zinc-900/70 text-zinc-300' };
    }
    if (googleStatus.status === 'connected') {
      return { label: 'Connected', tone: 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200' };
    }
    if (googleStatus.status === 'error') {
      return { label: 'Needs Attention', tone: 'border-red-500/40 bg-red-950/30 text-red-200' };
    }
    return { label: googleStatus.status.toUpperCase(), tone: statusTone(googleStatus.status) };
  }, [loadingGoogle, googleStatus]);

  const activeCycleStep = useMemo(
    () => computeOnboardingCycleStep(analytics, googleStatus),
    [analytics, googleStatus],
  );

  const toggleCycle = () => {
    const next = !cycleCollapsed;
    setCycleCollapsed(next);
    try {
      localStorage.setItem(cycleStorageKey, String(next));
    } catch {
      // noop
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 overflow-x-hidden">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-white/10 pb-6">
        <div className="text-center sm:text-left">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tighter text-white uppercase">Onboarding Center</h1>
          <p className="text-[10px] sm:text-xs text-zinc-500 mt-2 font-mono uppercase tracking-wide">
            Manage integrations, new hires, and onboarding workflows.
          </p>
        </div>
        <div className="flex justify-center sm:justify-end" data-tour="onboarding-center-guide">
          <FeatureGuideTrigger guideId="onboarding-center" />
        </div>
      </div>

      <div className="border border-white/10 bg-zinc-950/60">
        <button
          onClick={toggleCycle}
          className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
        >
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">Expected Onboarding Cycle</span>
            <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 border border-zinc-700 text-zinc-400">
              Step {activeCycleStep} of {ONBOARDING_CYCLE_STEPS.length}
            </span>
            <span className="text-[10px] text-zinc-600">
              {ONBOARDING_CYCLE_STEPS[activeCycleStep - 1].title}
            </span>
          </div>
          <ChevronDown
            size={14}
            className={`text-zinc-600 transition-transform duration-200 ${cycleCollapsed ? '' : 'rotate-180'}`}
          />
        </button>

        {!cycleCollapsed && (
          <div className="border-t border-white/10">
            <div className="relative px-5 pt-5 pb-2 overflow-x-auto">
              <div className="flex items-start gap-0 min-w-max">
                {ONBOARDING_CYCLE_STEPS.map((step, idx) => {
                  const isComplete = step.id < activeCycleStep;
                  const isActive = step.id === activeCycleStep;
                  return (
                    <div key={step.id} className="flex items-start">
                      <div className="flex flex-col items-center w-28">
                        <div
                          className={`relative w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm transition-all ${
                            isComplete
                              ? 'bg-matcha-500/20 border-matcha-500/50 text-matcha-400'
                              : isActive
                              ? 'bg-white/10 border-white text-white shadow-[0_0_12px_rgba(255,255,255,0.15)]'
                              : 'bg-zinc-900 border-zinc-700 text-zinc-600'
                          }`}
                        >
                          {isComplete ? '✓' : step.icon}
                        </div>
                        <div
                          className={`mt-2 text-center text-[10px] font-bold uppercase tracking-wider leading-tight px-1 ${
                            isActive ? 'text-white' : isComplete ? 'text-matcha-400/70' : 'text-zinc-600'
                          }`}
                        >
                          {step.title}
                        </div>
                      </div>

                      {idx < ONBOARDING_CYCLE_STEPS.length - 1 && (
                        <div
                          className={`w-10 h-0.5 mt-[18px] flex-shrink-0 transition-colors ${
                            step.id < activeCycleStep ? 'bg-matcha-500/40' : 'bg-zinc-800'
                          }`}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="mx-5 mb-5 p-4 bg-white/[0.03] border border-white/10">
              <div className="flex items-start gap-3">
                <span className="text-xl flex-shrink-0">{ONBOARDING_CYCLE_STEPS[activeCycleStep - 1].icon}</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold text-white uppercase tracking-wider">
                      {ONBOARDING_CYCLE_STEPS[activeCycleStep - 1].title}
                    </span>
                    <span className="text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-white/10 text-zinc-400 border border-white/10">
                      Current Step
                    </span>
                  </div>
                  <p className="text-[11px] text-zinc-400 leading-relaxed mb-2">
                    {ONBOARDING_CYCLE_STEPS[activeCycleStep - 1].description}
                  </p>
                  <p className="text-[11px] text-matcha-400/80 font-medium">
                    → {ONBOARDING_CYCLE_STEPS[activeCycleStep - 1].action}
                  </p>
                </div>
              </div>

              {activeCycleStep < ONBOARDING_CYCLE_STEPS.length && (
                <div className="mt-3 pt-3 border-t border-white/10 flex items-center gap-2">
                  <span className="text-[9px] uppercase tracking-widest text-zinc-600">Up next:</span>
                  <span className="text-[10px] text-zinc-500">
                    Step {activeCycleStep + 1} — {ONBOARDING_CYCLE_STEPS[activeCycleStep].title}
                  </span>
                </div>
              )}

              {analytics && (
                <div className="mt-3 pt-3 border-t border-white/10 flex flex-wrap gap-2">
                  <span className="text-[10px] px-2 py-1 border border-white/10 bg-white/[0.02] text-zinc-400">
                    Invited: <span className="text-zinc-200">{analytics.funnel.invited}</span>
                  </span>
                  <span className="text-[10px] px-2 py-1 border border-white/10 bg-white/[0.02] text-zinc-400">
                    Accepted: <span className="text-zinc-200">{analytics.funnel.accepted}</span>
                  </span>
                  <span className="text-[10px] px-2 py-1 border border-white/10 bg-white/[0.02] text-zinc-400">
                    Ready for Day 1: <span className="text-zinc-200">{analytics.funnel.ready_for_day1}</span>
                  </span>
                  {analytics.kpis.completion_before_start_rate !== null && (
                    <span className="text-[10px] px-2 py-1 border border-white/10 bg-white/[0.02] text-zinc-400">
                      Complete Before Start: <span className="text-zinc-200">{analytics.kpis.completion_before_start_rate.toFixed(1)}%</span>
                    </span>
                  )}
                </div>
              )}

              {analyticsError && (
                <div className="mt-3 pt-3 border-t border-white/10">
                  <p className="text-[10px] text-zinc-500">
                    Analytics unavailable: {analyticsError}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-white/10 -mx-4 px-4 sm:mx-0 sm:px-0">
        <nav className="-mb-px flex space-x-8 overflow-x-auto pb-px no-scrollbar">
          {[
            { id: 'workspace', label: 'Workspace' },
            { id: 'employees', label: 'New Hires' },
            { id: 'templates', label: 'Templates' },
            { id: 'runs', label: 'Activity' },
            { id: 'profile', label: 'Company Profile' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id as Tab)}
              data-tour={`onboarding-tab-${tab.id}`}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-white text-white'
                  : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-800'
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
            <div className="border border-white/10 bg-zinc-900/40 p-4 text-xs text-zinc-300 leading-relaxed">
              Connect external systems to automate employee provisioning. Credentials are encrypted and scoped to your organization.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Google Workspace Card */}
              <section data-tour="onboarding-workspace-google-card" className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold tracking-wide text-white">Google Workspace</h2>
                    <p className="text-xs text-zinc-500 mt-1">Provision Gmail & groups.</p>
                  </div>
                  <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-wider ${googleBadge.tone}`}>
                    {googleBadge.label}
                  </span>
                </div>

                {googleStatusError && (
                  <p className="text-xs text-red-300">Status check failed: {googleStatusError}</p>
                )}

                {googleStatus && (
                  <div className="space-y-1 text-[11px] text-zinc-400">
                    <p>Mode: <span className="text-zinc-200">{googleStatus.mode || 'not configured'}</span></p>
                    <p>Domain: <span className="text-zinc-200">{googleStatus.domain || 'not set'}</span></p>
                    <p>Auto-provision: <span className="text-zinc-200">{googleStatus.auto_provision_on_employee_create ? 'on' : 'off'}</span></p>
                  </div>
                )}

                <button
                  data-tour="onboarding-configure-google"
                  onClick={() => navigate('/app/matcha/google-workspace')}
                  className="w-full px-3 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider"
                >
                  Configure
                </button>
              </section>

              {/* Slack Card */}
              <section data-tour="onboarding-workspace-slack-card" className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold tracking-wide text-white">Slack</h2>
                    <p className="text-xs text-zinc-500 mt-1">Auto-invite, channels, and workspace defaults.</p>
                  </div>
                  <span className="rounded border border-zinc-700 bg-zinc-900/70 px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-300">
                    Draft Ready
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400">
                  Configure your workspace defaults now and wire OAuth when your Slack app is enabled.
                </p>
                <button
                  data-tour="onboarding-configure-slack"
                  onClick={() => navigate('/app/matcha/slack-provisioning')}
                  className="w-full px-3 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider"
                >
                  Configure
                </button>
              </section>

              {/* Toast Card (Coming Soon) */}
              <section className="border border-white/10 bg-zinc-900/50 p-5 space-y-4 opacity-75">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold tracking-wide text-white">Toast</h2>
                    <p className="text-xs text-zinc-500 mt-1">POS & location mapping.</p>
                  </div>
                  <span className="rounded border border-zinc-700 bg-zinc-900/70 px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-300">
                    Soon
                  </span>
                </div>
                <button
                  disabled
                  className="w-full px-3 py-2 border border-white/10 text-zinc-500 text-[10px] font-bold uppercase tracking-wider cursor-not-allowed"
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

        {activeTab === 'runs' && (
          <div data-tour="onboarding-runs-panel" className="flex items-center justify-center h-64 border border-dashed border-white/10 bg-white/5">
            <div className="text-center">
              <p className="text-zinc-500 text-sm font-mono uppercase tracking-wide">Activity Log Coming Soon</p>
              <p className="text-zinc-600 text-xs mt-2">View provisioning run history and retries here.</p>
            </div>
          </div>
        )}

        {activeTab === 'profile' && (
          <div className="space-y-6">
            <CompanyProfile />
          </div>
        )}
      </div>
    </div>
  );
}
