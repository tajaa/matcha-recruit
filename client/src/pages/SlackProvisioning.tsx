import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { provisioning } from '../api/client';
import type { SlackConnectionRequest, SlackConnectionStatus } from '../types';

interface SlackProvisioningForm {
  client_id: string;
  client_secret: string;
  workspace_url: string;
  admin_email: string;
  default_channels: string;
  oauth_scopes: string;
  auto_invite_on_employee_create: boolean;
  sync_display_name: boolean;
}

const DEFAULT_OAUTH_SCOPES = 'users:read,users:read.email,users:write,channels:read,conversations.invite';
const EMPTY_FORM: SlackProvisioningForm = {
  client_id: '',
  client_secret: '',
  workspace_url: '',
  admin_email: '',
  default_channels: '',
  oauth_scopes: DEFAULT_OAUTH_SCOPES,
  auto_invite_on_employee_create: true,
  sync_display_name: true,
};

function statusTone(status: string): string {
  if (status === 'connected') return 'text-emerald-300 border-emerald-600/40 bg-emerald-950/20';
  if (status === 'error') return 'text-red-300 border-red-600/40 bg-red-950/20';
  if (status === 'needs_action') return 'text-amber-300 border-amber-600/40 bg-amber-950/20';
  return 'text-zinc-300 border-zinc-700/60 bg-zinc-900/60';
}

function splitCsv(value: string): string[] {
  return value
    .split(/[\n,]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function hydrateFormFromStatus(status: SlackConnectionStatus): SlackProvisioningForm {
  return {
    client_id: status.client_id || '',
    client_secret: '',
    workspace_url: status.workspace_url || '',
    admin_email: status.admin_email || '',
    default_channels: (status.default_channels || []).join(', '),
    oauth_scopes: (status.oauth_scopes || []).join(', ') || DEFAULT_OAUTH_SCOPES,
    auto_invite_on_employee_create: status.auto_invite_on_employee_create ?? true,
    sync_display_name: status.sync_display_name ?? true,
  };
}

export default function SlackProvisioning() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [oauthStarting, setOauthStarting] = useState(false);
  const [status, setStatus] = useState<SlackConnectionStatus | null>(null);
  const [form, setForm] = useState<SlackProvisioningForm>(EMPTY_FORM);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const loadStatus = async () => {
    setLoading(true);
    setError('');
    try {
      const connection = await provisioning.getSlackStatus();
      setStatus(connection);
      setForm(hydrateFormFromStatus(connection));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Slack status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  useEffect(() => {
    const oauth = searchParams.get('slack_oauth');
    const oauthMessage = searchParams.get('slack_message');
    if (!oauth && !oauthMessage) return;

    if (oauth === 'success') {
      setMessage(oauthMessage || 'Slack OAuth connected successfully.');
      setError('');
      void loadStatus();
    } else {
      setError(oauthMessage || 'Slack OAuth failed.');
      setMessage('');
    }

    const next = new URLSearchParams(searchParams);
    next.delete('slack_oauth');
    next.delete('slack_message');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const currentStatus = status?.status || 'disconnected';
  const statusBadgeText = useMemo(() => {
    if (loading) return 'Checking';
    if (!status || status.status === 'disconnected') return 'Not Connected';
    if (status.status === 'connected') return 'Connected';
    if (status.status === 'error') return 'Needs Attention';
    return status.status.toUpperCase();
  }, [loading, status]);

  const buildPayload = (): SlackConnectionRequest => ({
    client_id: form.client_id.trim() || undefined,
    client_secret: form.client_secret.trim() || undefined,
    workspace_url: form.workspace_url.trim() || undefined,
    admin_email: form.admin_email.trim() || undefined,
    default_channels: splitCsv(form.default_channels),
    oauth_scopes: splitCsv(form.oauth_scopes),
    auto_invite_on_employee_create: form.auto_invite_on_employee_create,
    sync_display_name: form.sync_display_name,
  });

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const updated = await provisioning.connectSlack(buildPayload());
      setStatus(updated);
      setForm(hydrateFormFromStatus(updated));
      setMessage(
        updated.connected
          ? 'Slack settings saved.'
          : `Slack settings saved. Status: ${updated.status}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save Slack settings');
    } finally {
      setSaving(false);
    }
  };

  const handleStartOAuth = async () => {
    setOauthStarting(true);
    setError('');
    setMessage('');
    try {
      const saved = await provisioning.connectSlack(buildPayload());
      setStatus(saved);
      const oauth = await provisioning.startSlackOAuth();
      window.location.assign(oauth.authorize_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Slack OAuth');
      setOauthStarting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading Slack settings...</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="border-b border-white/10 pb-6">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-3xl font-bold tracking-tighter text-white uppercase">Slack Provisioning</h1>
          <span className={`rounded border px-2 py-1 text-[10px] uppercase tracking-wider ${statusTone(currentStatus)}`}>
            {statusBadgeText}
          </span>
        </div>
        <p className="text-xs text-zinc-500 mt-2 font-mono uppercase tracking-wide">
          Configure workspace defaults and connect OAuth for onboarding invites.
        </p>
      </div>

      {error && (
        <div className="border border-red-600/40 bg-red-950/20 p-3 text-sm text-red-300">
          {error}
        </div>
      )}
      {message && (
        <div className="border border-emerald-600/40 bg-emerald-950/20 p-3 text-sm text-emerald-300">
          {message}
        </div>
      )}

      <div className={`border p-4 ${statusTone(currentStatus)}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider opacity-80">Current Status</p>
            <p className="text-sm font-semibold uppercase tracking-wider mt-1">{currentStatus}</p>
          </div>
          <div className="text-xs opacity-80 space-y-1">
            <p>Client ID: {status?.client_id || 'not set'}</p>
            <p>Client secret: {status?.has_client_secret ? 'stored' : 'missing'}</p>
            <p>Workspace: {status?.workspace_url || 'not set'}</p>
            <p>Team: {status?.slack_team_name || status?.slack_team_id || 'not connected'}</p>
            <p>Bot token: {status?.has_bot_token ? 'stored' : 'missing'}</p>
            <p>Last OAuth test: {status?.last_tested_at ? new Date(status.last_tested_at).toLocaleString() : 'never'}</p>
          </div>
        </div>
        {status?.last_error && (
          <p className="mt-3 text-xs text-red-200">Last error: {status.last_error}</p>
        )}
      </div>

      <form onSubmit={handleSave} className="border border-white/10 bg-zinc-900/40 p-5 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="space-y-2">
            <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Slack Client ID</span>
            <input
              type="text"
              value={form.client_id}
              onChange={(event) => setForm((prev) => ({ ...prev, client_id: event.target.value }))}
              placeholder="1234567890.1234567890"
              className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
            />
          </label>

          <label className="space-y-2">
            <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Slack Client Secret</span>
            <input
              type="password"
              value={form.client_secret}
              onChange={(event) => setForm((prev) => ({ ...prev, client_secret: event.target.value }))}
              placeholder={status?.has_client_secret ? '•••••••• (leave blank to keep)' : 'Enter client secret'}
              className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
            />
            <p className="text-[11px] text-zinc-500">Leave blank to keep the currently stored secret.</p>
          </label>

          <label className="space-y-2">
            <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Workspace URL</span>
            <input
              type="text"
              value={form.workspace_url}
              onChange={(event) => setForm((prev) => ({ ...prev, workspace_url: event.target.value }))}
              placeholder="https://your-workspace.slack.com"
              className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
            />
          </label>

          <label className="space-y-2">
            <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Admin Email</span>
            <input
              type="email"
              value={form.admin_email}
              onChange={(event) => setForm((prev) => ({ ...prev, admin_email: event.target.value }))}
              placeholder="it-admin@company.com"
              className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
            />
          </label>
        </div>

        <label className="space-y-2 block">
          <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Default Channels</span>
          <input
            type="text"
            value={form.default_channels}
            onChange={(event) => setForm((prev) => ({ ...prev, default_channels: event.target.value }))}
            placeholder="#all-hands,#new-hires,#it-help"
            className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
          />
          <p className="text-[11px] text-zinc-500">Comma-separated channel names to invite new hires into by default.</p>
        </label>

        <label className="space-y-2 block">
          <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">OAuth Scopes</span>
          <input
            type="text"
            value={form.oauth_scopes}
            onChange={(event) => setForm((prev) => ({ ...prev, oauth_scopes: event.target.value }))}
            className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
          />
        </label>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-zinc-300">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.auto_invite_on_employee_create}
              onChange={(event) => setForm((prev) => ({ ...prev, auto_invite_on_employee_create: event.target.checked }))}
            />
            Auto-invite users when employee profiles are created
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.sync_display_name}
              onChange={(event) => setForm((prev) => ({ ...prev, sync_display_name: event.target.checked }))}
            />
            Sync profile display names from HRIS
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={saving || oauthStarting}
            className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
          <button
            type="button"
            onClick={handleStartOAuth}
            disabled={saving || oauthStarting}
            className="px-4 py-2 bg-emerald-500 text-black hover:bg-emerald-400 text-[10px] font-bold uppercase tracking-wider disabled:opacity-50"
          >
            {oauthStarting ? 'Redirecting...' : status?.connected ? 'Reconnect Slack' : 'Connect Slack OAuth'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/app/matcha/onboarding?tab=workspace')}
            className="px-4 py-2 border border-white/15 text-zinc-200 hover:border-white/30 text-[10px] font-bold uppercase tracking-wider"
          >
            Back to Onboarding
          </button>
        </div>
      </form>
    </div>
  );
}
