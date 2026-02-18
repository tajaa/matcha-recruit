import { useState, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { provisioning } from '../api/client';
import type { GoogleWorkspaceConnectionStatus } from '../types';
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

export default function OnboardingCenter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<Tab>('workspace');

  // Workspace Tab State
  const [loadingGoogle, setLoadingGoogle] = useState(true);
  const [googleStatus, setGoogleStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleStatusError, setGoogleStatusError] = useState('');

  useEffect(() => {
    const tab = searchParams.get('tab');
    if (tab && ['workspace', 'employees', 'templates', 'runs'].includes(tab)) {
      setActiveTab(tab as Tab);
    } else {
      setSearchParams({ tab: 'workspace' }, { replace: true });
    }
  }, [searchParams, setSearchParams]);

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

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="border-b border-white/10 pb-6">
        <h1 className="text-3xl font-bold tracking-tighter text-white uppercase">Onboarding Center</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono uppercase tracking-wide">
          Manage integrations, new hires, and onboarding workflows.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-white/10">
        <nav className="-mb-px flex space-x-8">
          {[
            { id: 'workspace', label: 'Workspace' },
            { id: 'employees', label: 'Employees' },
            { id: 'templates', label: 'Templates' },
            { id: 'runs', label: 'Activity' },
            { id: 'profile', label: 'Company Profile' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id as Tab)}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors ${
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

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Google Workspace Card */}
              <section className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
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
                  onClick={() => navigate('/app/matcha/google-workspace')}
                  className="w-full px-3 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider"
                >
                  Configure
                </button>
              </section>

              {/* Slack Card (Coming Soon) */}
              <section className="border border-white/10 bg-zinc-900/50 p-5 space-y-4 opacity-75">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold tracking-wide text-white">Slack</h2>
                    <p className="text-xs text-zinc-500 mt-1">Auto-invite & channel setup.</p>
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
            <Employees />
          </div>
        )}

        {activeTab === 'templates' && (
          <div className="space-y-6">
            <OnboardingTemplates />
          </div>
        )}

        {activeTab === 'runs' && (
          <div className="flex items-center justify-center h-64 border border-dashed border-white/10 bg-white/5">
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
