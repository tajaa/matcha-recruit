import { useEffect, useMemo, useState } from 'react';
import { auth, brokerPortal } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type { BrokerAuthProfile, BrokerClientSetup, BrokerClientSetupCreateRequest } from '../../types';

const FEATURE_KEYS = ['compliance', 'policies', 'handbooks', 'incidents'] as const;

function asBrokerProfile(profile: unknown): BrokerAuthProfile | null {
  if (!profile || typeof profile !== 'object') return null;
  if (!('broker_id' in profile)) return null;
  return profile as BrokerAuthProfile;
}

export default function BrokerClients() {
  const { profile, refreshUser } = useAuth();
  const brokerProfile = asBrokerProfile(profile);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [setups, setSetups] = useState<BrokerClientSetup[]>([]);
  const [expiredCount, setExpiredCount] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [acceptingTerms, setAcceptingTerms] = useState(false);

  const [form, setForm] = useState<BrokerClientSetupCreateRequest>({
    company_name: '',
    industry: '',
    company_size: '',
    contact_name: '',
    contact_email: '',
    headcount: undefined,
    invite_immediately: false,
    preconfigured_features: {
      compliance: true,
      policies: true,
      handbooks: true,
      incidents: false,
    },
  });

  const loadSetups = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await brokerPortal.listSetups();
      setSetups(response.setups);
      setExpiredCount(response.expired_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load broker setups');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSetups();
  }, []);

  const counts = useMemo(() => {
    return setups.reduce(
      (acc, setup) => {
        acc.total += 1;
        acc[setup.status] += 1;
        return acc;
      },
      {
        total: 0,
        draft: 0,
        invited: 0,
        activated: 0,
        expired: 0,
        cancelled: 0,
      }
    );
  }, [setups]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const payload: BrokerClientSetupCreateRequest = {
        ...form,
        company_name: (form.company_name || '').trim(),
        industry: form.industry || undefined,
        company_size: form.company_size || undefined,
        contact_name: form.contact_name || undefined,
        contact_email: form.contact_email || undefined,
        headcount: form.headcount || undefined,
      };
      await brokerPortal.createSetup(payload);
      setMessage('Client setup created');
      setForm({
        company_name: '',
        industry: '',
        company_size: '',
        contact_name: '',
        contact_email: '',
        headcount: undefined,
        invite_immediately: false,
        preconfigured_features: {
          compliance: true,
          policies: true,
          handbooks: true,
          incidents: false,
        },
      });
      await loadSetups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create setup');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSendInvite = async (setupId: string) => {
    setError('');
    setMessage('');
    try {
      const response = await brokerPortal.sendInvite(setupId, 14);
      setMessage(`Invite sent for ${response.setup.company_name}`);
      await loadSetups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send invite');
    }
  };

  const handleCancel = async (setupId: string) => {
    setError('');
    setMessage('');
    try {
      await brokerPortal.cancelSetup(setupId);
      setMessage('Setup cancelled');
      await loadSetups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel setup');
    }
  };

  const handleExpireStale = async () => {
    setError('');
    setMessage('');
    try {
      const response = await brokerPortal.expireStale();
      setMessage(`Expired ${response.expired_count} stale setup(s)`);
      await loadSetups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to expire stale setups');
    }
  };

  const handleAcceptTerms = async () => {
    if (!brokerProfile) return;
    setAcceptingTerms(true);
    setError('');
    setMessage('');
    try {
      await auth.acceptBrokerTerms(brokerProfile.terms_required_version);
      await refreshUser();
      setMessage('Broker partner terms accepted');
      await loadSetups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept broker terms');
    } finally {
      setAcceptingTerms(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Broker Client Onboarding</h1>
          <p className="text-sm text-zinc-400">Pre-configure accounts, invite clients, and monitor activation.</p>
        </div>
        <button
          onClick={handleExpireStale}
          className="px-3 py-2 text-xs uppercase tracking-wide border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500"
        >
          Expire Stale ({expiredCount})
        </button>
      </div>

      {!brokerProfile?.terms_accepted && (
        <div className="border border-amber-600/40 bg-amber-950/20 p-4 rounded-sm">
          <p className="text-sm text-amber-200 mb-3">
            You must accept broker partner terms ({brokerProfile?.terms_required_version || 'v1'}) before onboarding client companies.
          </p>
          <button
            onClick={handleAcceptTerms}
            disabled={acceptingTerms}
            className="px-3 py-2 text-xs uppercase tracking-wide bg-amber-500 text-black disabled:opacity-60"
          >
            {acceptingTerms ? 'Accepting...' : 'Accept Terms'}
          </button>
        </div>
      )}

      {error && <div className="border border-red-600/40 bg-red-950/20 p-3 text-sm text-red-300">{error}</div>}
      {message && <div className="border border-emerald-600/40 bg-emerald-950/20 p-3 text-sm text-emerald-300">{message}</div>}

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <div className="bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Total</p>
          <p className="text-lg text-white">{counts.total}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Draft</p>
          <p className="text-lg text-white">{counts.draft}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Invited</p>
          <p className="text-lg text-white">{counts.invited}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Activated</p>
          <p className="text-lg text-white">{counts.activated}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Expired</p>
          <p className="text-lg text-white">{counts.expired}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-3">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Cancelled</p>
          <p className="text-lg text-white">{counts.cancelled}</p>
        </div>
      </div>

      <form onSubmit={handleCreate} className="bg-zinc-900 border border-zinc-800 p-4 space-y-4">
        <h2 className="text-sm uppercase tracking-wide text-zinc-300">Create Setup</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            value={form.company_name || ''}
            onChange={(e) => setForm((prev) => ({ ...prev, company_name: e.target.value }))}
            placeholder="Company name"
            className="bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
            required
          />
          <input
            value={form.industry || ''}
            onChange={(e) => setForm((prev) => ({ ...prev, industry: e.target.value }))}
            placeholder="Industry"
            className="bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
          />
          <input
            value={form.company_size || ''}
            onChange={(e) => setForm((prev) => ({ ...prev, company_size: e.target.value }))}
            placeholder="Company size (e.g. 11-50)"
            className="bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
          />
          <input
            value={form.contact_name || ''}
            onChange={(e) => setForm((prev) => ({ ...prev, contact_name: e.target.value }))}
            placeholder="Primary contact name"
            className="bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
          />
          <input
            value={form.contact_email || ''}
            onChange={(e) => setForm((prev) => ({ ...prev, contact_email: e.target.value }))}
            placeholder="Primary contact email"
            type="email"
            className="bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
          />
          <input
            value={form.headcount || ''}
            onChange={(e) => {
              const val = e.target.value ? Number(e.target.value) : undefined;
              setForm((prev) => ({ ...prev, headcount: val }));
            }}
            placeholder="Headcount"
            type="number"
            min={1}
            className="bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-white"
          />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {FEATURE_KEYS.map((featureKey) => (
            <label key={featureKey} className="flex items-center gap-2 text-xs text-zinc-300">
              <input
                type="checkbox"
                checked={Boolean(form.preconfigured_features?.[featureKey])}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    preconfigured_features: {
                      ...(prev.preconfigured_features || {}),
                      [featureKey]: e.target.checked,
                    },
                  }))
                }
              />
              {featureKey}
            </label>
          ))}
        </div>

        <label className="flex items-center gap-2 text-xs text-zinc-300">
          <input
            type="checkbox"
            checked={Boolean(form.invite_immediately)}
            onChange={(e) => setForm((prev) => ({ ...prev, invite_immediately: e.target.checked }))}
          />
          Send invite immediately after create
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="px-3 py-2 text-xs uppercase tracking-wide bg-white text-black disabled:opacity-60"
        >
          {submitting ? 'Creating...' : 'Create Setup'}
        </button>
      </form>

      <div className="bg-zinc-900 border border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 text-sm uppercase tracking-wide text-zinc-300">Setups</div>
        {loading ? (
          <div className="p-4 text-sm text-zinc-400">Loading setups...</div>
        ) : setups.length === 0 ? (
          <div className="p-4 text-sm text-zinc-400">No setups yet.</div>
        ) : (
          <div className="divide-y divide-zinc-800">
            {setups.map((setup) => (
              <div key={setup.id} className="p-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                  <p className="text-sm text-white">{setup.company_name}</p>
                  <p className="text-xs text-zinc-400">
                    {setup.status.toUpperCase()} | {setup.contact_email || 'No contact email'}
                  </p>
                  {setup.invite_url && (
                    <p className="text-xs text-zinc-500 mt-1 break-all">{setup.invite_url}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {(setup.status === 'draft' || setup.status === 'invited') && (
                    <button
                      onClick={() => handleSendInvite(setup.id)}
                      className="px-2 py-1 text-[10px] uppercase tracking-wide border border-zinc-700 text-zinc-300"
                    >
                      Send Invite
                    </button>
                  )}
                  {(setup.status === 'draft' || setup.status === 'invited') && (
                    <button
                      onClick={() => handleCancel(setup.id)}
                      className="px-2 py-1 text-[10px] uppercase tracking-wide border border-red-700 text-red-300"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
