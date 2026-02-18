import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

interface SlackProvisioningDraft {
  workspaceUrl: string;
  adminEmail: string;
  defaultChannels: string;
  oauthScopes: string;
  autoInviteOnEmployeeCreate: boolean;
  syncDisplayName: boolean;
}

const STORAGE_KEY = 'matcha.slack-provisioning-draft';
const DEFAULT_DRAFT: SlackProvisioningDraft = {
  workspaceUrl: '',
  adminEmail: '',
  defaultChannels: '',
  oauthScopes: 'users:read,users:read.email,users:write,channels:read,conversations.invite',
  autoInviteOnEmployeeCreate: true,
  syncDisplayName: true,
};

export default function SlackProvisioning() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<SlackProvisioningDraft>(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return DEFAULT_DRAFT;
      const parsed = JSON.parse(raw) as Partial<SlackProvisioningDraft>;
      return {
        ...DEFAULT_DRAFT,
        ...parsed,
      };
    } catch {
      return DEFAULT_DRAFT;
    }
  });
  const [statusMessage, setStatusMessage] = useState('');
  const [loadError] = useState(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return '';
      JSON.parse(raw);
      return '';
    } catch {
      return 'Could not load saved Slack setup draft.';
    }
  });

  const handleSaveDraft = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    setStatusMessage('Slack setup draft saved locally. OAuth activation can be connected when backend support is enabled.');
  };

  const handleReset = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setDraft(DEFAULT_DRAFT);
    setStatusMessage('Slack setup draft cleared.');
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="border-b border-white/10 pb-6">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-3xl font-bold tracking-tighter text-white uppercase">Slack Provisioning</h1>
          <span className="rounded border border-zinc-700 bg-zinc-900/70 px-2 py-1 text-[10px] uppercase tracking-wider text-zinc-300">
            Draft Ready
          </span>
        </div>
        <p className="text-xs text-zinc-500 mt-2 font-mono uppercase tracking-wide">
          Prepare workspace defaults now. OAuth connect can be enabled without changing this setup screen.
        </p>
      </div>

      {loadError && (
        <div className="border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-200">
          {loadError}
        </div>
      )}

      {statusMessage && (
        <div className="border border-emerald-500/30 bg-emerald-950/20 p-3 text-xs text-emerald-200">
          {statusMessage}
        </div>
      )}

      <form onSubmit={handleSaveDraft} className="border border-white/10 bg-zinc-900/40 p-5 space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="space-y-2">
            <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Workspace URL</span>
            <input
              type="text"
              value={draft.workspaceUrl}
              onChange={(event) => setDraft((prev) => ({ ...prev, workspaceUrl: event.target.value }))}
              placeholder="https://your-workspace.slack.com"
              className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
            />
          </label>

          <label className="space-y-2">
            <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Admin Email</span>
            <input
              type="email"
              value={draft.adminEmail}
              onChange={(event) => setDraft((prev) => ({ ...prev, adminEmail: event.target.value }))}
              placeholder="it-admin@company.com"
              className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
            />
          </label>
        </div>

        <label className="space-y-2 block">
          <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">Default Channels</span>
          <input
            type="text"
            value={draft.defaultChannels}
            onChange={(event) => setDraft((prev) => ({ ...prev, defaultChannels: event.target.value }))}
            placeholder="#all-hands,#new-hires,#it-help"
            className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
          />
          <p className="text-[11px] text-zinc-500">Comma-separated channel names to invite new hires into by default.</p>
        </label>

        <label className="space-y-2 block">
          <span className="block text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">OAuth Scopes</span>
          <input
            type="text"
            value={draft.oauthScopes}
            onChange={(event) => setDraft((prev) => ({ ...prev, oauthScopes: event.target.value }))}
            className="w-full px-3 py-2 bg-black/40 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30"
          />
        </label>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-zinc-300">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.autoInviteOnEmployeeCreate}
              onChange={(event) => setDraft((prev) => ({ ...prev, autoInviteOnEmployeeCreate: event.target.checked }))}
            />
            Auto-invite users when employee profiles are created
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.syncDisplayName}
              onChange={(event) => setDraft((prev) => ({ ...prev, syncDisplayName: event.target.checked }))}
            />
            Sync profile display names from HRIS
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-[10px] font-bold uppercase tracking-wider"
          >
            Save Draft
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="px-4 py-2 border border-white/15 text-zinc-200 hover:border-white/30 text-[10px] font-bold uppercase tracking-wider"
          >
            Clear Draft
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
