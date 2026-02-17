import { useEffect, useState } from 'react';
import { provisioning } from '../api/client';
import { FeatureGuideTrigger } from '../features/feature-guides';
import type {
  GoogleWorkspaceConnectionRequest,
  GoogleWorkspaceConnectionStatus,
} from '../types';

type ConnectionMode = 'mock' | 'api_token' | 'service_account';

interface FormState {
  mode: ConnectionMode;
  domain: string;
  admin_email: string;
  delegated_admin_email: string;
  default_org_unit: string;
  default_groups: string;
  auto_provision_on_employee_create: boolean;
  access_token: string;
  service_account_json: string;
  test_connection: boolean;
}

const EMPTY_FORM: FormState = {
  mode: 'mock',
  domain: '',
  admin_email: '',
  delegated_admin_email: '',
  default_org_unit: '',
  default_groups: '',
  auto_provision_on_employee_create: true,
  access_token: '',
  service_account_json: '',
  test_connection: true,
};

function statusTone(status: string): string {
  if (status === 'connected') return 'text-emerald-300 border-emerald-600/40 bg-emerald-950/20';
  if (status === 'error') return 'text-red-300 border-red-600/40 bg-red-950/20';
  if (status === 'needs_action') return 'text-amber-300 border-amber-600/40 bg-amber-950/20';
  return 'text-zinc-300 border-zinc-700/60 bg-zinc-900/60';
}

function hydrateFormFromStatus(status: GoogleWorkspaceConnectionStatus): FormState {
  return {
    mode: status.mode === 'api_token' || status.mode === 'service_account' ? status.mode : 'mock',
    domain: status.domain || '',
    admin_email: status.admin_email || '',
    delegated_admin_email: status.delegated_admin_email || '',
    default_org_unit: status.default_org_unit || '',
    default_groups: (status.default_groups || []).join(', '),
    auto_provision_on_employee_create: status.auto_provision_on_employee_create ?? true,
    access_token: '',
    service_account_json: '',
    test_connection: true,
  };
}

export default function GoogleWorkspaceProvisioning() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [status, setStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const loadStatus = async () => {
    setLoading(true);
    setError('');
    try {
      const connection = await provisioning.getGoogleWorkspaceStatus();
      setStatus(connection);
      setForm(hydrateFormFromStatus(connection));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load Google Workspace status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');

    try {
      const groups = form.default_groups
        .split(/[\n,]/g)
        .map((entry) => entry.trim())
        .filter(Boolean);

      const payload: GoogleWorkspaceConnectionRequest = {
        mode: form.mode,
        domain: form.domain.trim() || undefined,
        admin_email: form.admin_email.trim() || undefined,
        delegated_admin_email: form.delegated_admin_email.trim() || undefined,
        default_org_unit: form.default_org_unit.trim() || undefined,
        default_groups: groups.length > 0 ? groups : undefined,
        auto_provision_on_employee_create: form.auto_provision_on_employee_create,
        access_token: form.mode === 'api_token' ? (form.access_token.trim() || undefined) : undefined,
        service_account_json:
          form.mode === 'service_account' ? (form.service_account_json.trim() || undefined) : undefined,
        test_connection: form.test_connection,
      };

      const updated = await provisioning.connectGoogleWorkspace(payload);
      setStatus(updated);
      setForm((prev) => ({
        ...hydrateFormFromStatus(updated),
        test_connection: prev.test_connection,
      }));
      setMessage(
        updated.connected
          ? 'Google Workspace connection saved and verified.'
          : `Connection saved with status: ${updated.status}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save connection');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading Google Workspace settings...</div>
      </div>
    );
  }

  const currentStatus = status?.status || 'disconnected';

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="border-b border-white/10 pb-6 flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tighter text-white">Google Workspace Provisioning</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono uppercase tracking-wide">
            Configure Matcha to provision employee accounts in your Google Workspace tenant.
          </p>
        </div>
        <div data-tour="google-workspace-guide">
          <FeatureGuideTrigger guideId="google-workspace" />
        </div>
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

      <div data-tour="google-workspace-status" className={`border p-4 ${statusTone(currentStatus)}`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider opacity-80">Current Status</p>
            <p className="text-sm font-semibold uppercase tracking-wider mt-1">{currentStatus}</p>
          </div>
          <div className="text-xs opacity-80 space-y-1">
            <p>Mode: {status?.mode || 'not configured'}</p>
            <p>Domain: {status?.domain || 'not set'}</p>
            <p>Delegated admin: {status?.delegated_admin_email || 'not set'}</p>
            <p>Auto-provision on employee create: {status?.auto_provision_on_employee_create ? 'on' : 'off'}</p>
            <p>Last tested: {status?.last_tested_at ? new Date(status.last_tested_at).toLocaleString() : 'never'}</p>
          </div>
        </div>
        {status?.last_error && (
          <p className="mt-3 text-xs text-red-200">Last error: {status.last_error}</p>
        )}
      </div>

      <form data-tour="google-workspace-form" onSubmit={handleSave} className="border border-white/10 bg-zinc-900/40 p-5 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label data-tour="google-workspace-mode" className="space-y-2">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">Mode</span>
            <select
              value={form.mode}
              onChange={(e) => setForm((prev) => ({ ...prev, mode: e.target.value as ConnectionMode }))}
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
            >
              <option value="mock">Mock (safe sandbox)</option>
              <option value="api_token">API Token (live)</option>
              <option value="service_account">Service Account (live, recommended)</option>
            </select>
          </label>

          <label data-tour="google-workspace-domain" className="space-y-2">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">Google Workspace Domain</span>
            <input
              value={form.domain}
              onChange={(e) => setForm((prev) => ({ ...prev, domain: e.target.value }))}
              placeholder="example.com"
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
            />
          </label>

          <label data-tour="google-workspace-admin-email" className="space-y-2">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">Admin Email</span>
            <input
              type="email"
              value={form.admin_email}
              onChange={(e) => setForm((prev) => ({ ...prev, admin_email: e.target.value }))}
              placeholder="admin@example.com"
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
            />
            <p className="text-[10px] text-zinc-500 leading-tight">Must be a Super Admin in your Workspace tenant.</p>
          </label>

          <label data-tour="google-workspace-delegated-admin-email" className="space-y-2">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">Delegated Admin Email</span>
            <input
              type="email"
              value={form.delegated_admin_email}
              onChange={(e) => setForm((prev) => ({ ...prev, delegated_admin_email: e.target.value }))}
              placeholder="it-admin@example.com"
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
            />
            <p className="text-[10px] text-zinc-500 leading-tight">The user account impersonated by the Service Account.</p>
          </label>

          <label data-tour="google-workspace-org-unit" className="space-y-2">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">Default Org Unit</span>
            <input
              value={form.default_org_unit}
              onChange={(e) => setForm((prev) => ({ ...prev, default_org_unit: e.target.value }))}
              placeholder="/employees"
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
            />
            <p className="text-[10px] text-zinc-500 leading-tight">Path for new users (e.g. /Employees). Use / for root.</p>
          </label>
        </div>

        <label data-tour="google-workspace-groups" className="space-y-2 block">
          <span className="text-[11px] uppercase tracking-wider text-zinc-400">Default Groups</span>
          <textarea
            value={form.default_groups}
            onChange={(e) => setForm((prev) => ({ ...prev, default_groups: e.target.value }))}
            placeholder="eng@company.com, all-hands@company.com"
            rows={3}
            className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
          />
          <p className="text-[11px] text-zinc-500">Separate groups by comma or newline.</p>
        </label>

        {form.mode === 'api_token' && (
          <label data-tour="google-workspace-token" className="space-y-2 block">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">
              Access Token {status?.has_access_token ? '(leave blank to keep existing)' : '(required)'}
            </span>
            <input
              type="password"
              value={form.access_token}
              onChange={(e) => setForm((prev) => ({ ...prev, access_token: e.target.value }))}
              placeholder={status?.has_access_token ? '••••••••••••••••' : 'Paste Google admin token'}
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
            />
          </label>
        )}

        {form.mode === 'service_account' && (
          <label data-tour="google-workspace-json" className="space-y-2 block">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">
              Service Account JSON {status?.has_service_account_credentials ? '(leave blank to keep existing)' : '(required)'}
            </span>
            <textarea
              value={form.service_account_json}
              onChange={(e) => setForm((prev) => ({ ...prev, service_account_json: e.target.value }))}
              placeholder='{"type":"service_account","project_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\\n..."}'
              rows={8}
              className="w-full bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white font-mono"
            />
            <p className="text-[11px] text-zinc-500">
              Use a Workspace service account with Domain-Wide Delegation enabled.
            </p>
          </label>
        )}

        <label data-tour="google-workspace-options" className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={form.auto_provision_on_employee_create}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, auto_provision_on_employee_create: e.target.checked }))
            }
          />
          Auto-provision Google account when a new employee is created
        </label>

        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={form.test_connection}
            onChange={(e) => setForm((prev) => ({ ...prev, test_connection: e.target.checked }))}
          />
          Test connection before saving
        </label>

        <div className="flex justify-end">
          <button
            data-tour="google-workspace-save"
            type="submit"
            disabled={saving}
            className="px-5 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider disabled:opacity-60"
          >
            {saving ? 'Saving...' : 'Save Connection'}
          </button>
        </div>
      </form>
    </div>
  );
}
