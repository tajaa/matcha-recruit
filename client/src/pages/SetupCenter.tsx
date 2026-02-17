import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { provisioning } from '../api/client';
import type { GoogleWorkspaceConnectionStatus } from '../types';

function statusTone(status: string): string {
  if (status === 'connected') return 'border-emerald-500/40 bg-emerald-950/30 text-emerald-200';
  if (status === 'error') return 'border-red-500/40 bg-red-950/30 text-red-200';
  if (status === 'needs_action') return 'border-amber-500/40 bg-amber-950/30 text-amber-200';
  return 'border-zinc-700 bg-zinc-900/70 text-zinc-300';
}

export default function SetupCenter() {
  const navigate = useNavigate();
  const [loadingGoogle, setLoadingGoogle] = useState(true);
  const [googleStatus, setGoogleStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleStatusError, setGoogleStatusError] = useState('');

  useEffect(() => {
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
  }, []);

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
    <div className="max-w-6xl mx-auto space-y-8">
      <div className="border-b border-white/10 pb-6">
        <h1 className="text-3xl font-bold tracking-tighter text-white">Setup Center</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono uppercase tracking-wide">
          Connect and manage external systems for this business account.
        </p>
      </div>

      <div className="border border-white/10 bg-zinc-900/40 p-4 text-xs text-zinc-300 leading-relaxed">
        Integrations are tenant-scoped. Credentials are saved per business organization and encrypted at rest.
        One business cannot read another business&apos;s integration credentials or data.
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <section className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold tracking-wide text-white">Google Workspace</h2>
              <p className="text-xs text-zinc-500 mt-1">Provision company Gmail accounts on employee onboarding.</p>
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
            Configure Google
          </button>
        </section>

        <section className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold tracking-wide text-white">Slack</h2>
              <p className="text-xs text-zinc-500 mt-1">Auto-invite employees and assign workspace defaults.</p>
            </div>
            <span className="rounded border border-zinc-700 bg-zinc-900/70 px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-300">
              Coming Soon
            </span>
          </div>
          <p className="text-[11px] text-zinc-400">
            This card will support per-business Slack OAuth and channel/group defaults.
          </p>
          <button
            disabled
            className="w-full px-3 py-2 border border-white/10 text-zinc-500 text-[10px] font-bold uppercase tracking-wider cursor-not-allowed"
          >
            Slack Setup (Soon)
          </button>
        </section>

        <section className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold tracking-wide text-white">Toast</h2>
              <p className="text-xs text-zinc-500 mt-1">Link location-level systems for restaurant operations.</p>
            </div>
            <span className="rounded border border-zinc-700 bg-zinc-900/70 px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-300">
              Coming Soon
            </span>
          </div>
          <p className="text-[11px] text-zinc-400">
            This card will support per-business Toast credentials and location mapping.
          </p>
          <button
            disabled
            className="w-full px-3 py-2 border border-white/10 text-zinc-500 text-[10px] font-bold uppercase tracking-wider cursor-not-allowed"
          >
            Toast Setup (Soon)
          </button>
        </section>
      </div>
    </div>
  );
}
