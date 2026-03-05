import { useEffect, useState, useCallback } from 'react';
import { brokerPortal } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type {
  BrokerAuthProfile,
  BrokerClientSetup,
  BrokerClientSetupCreateRequest,
} from '../../types';
import {
  Check,
  Copy,
  ExternalLink,
  Plus,
  Send,
  XCircle,
  Pencil,
  X,
  Loader2,
} from 'lucide-react';

const APP_BASE_URL = window.location.origin;

function asBrokerProfile(profile: unknown): BrokerAuthProfile | null {
  if (!profile || typeof profile !== 'object') return null;
  if (!('broker_id' in profile)) return null;
  return profile as BrokerAuthProfile;
}

/* ---------- status badge helpers ---------- */

function setupStatusBadge(s: string) {
  switch (s) {
    case 'draft':
      return 'border-zinc-600/40 bg-zinc-800/40 text-zinc-300';
    case 'invited':
      return 'border-blue-600/40 bg-blue-950/20 text-blue-300';
    case 'activated':
      return 'border-emerald-600/40 bg-emerald-950/20 text-emerald-300';
    case 'expired':
      return 'border-amber-600/40 bg-amber-950/20 text-amber-300';
    case 'cancelled':
      return 'border-red-600/40 bg-red-950/20 text-red-300';
    default:
      return 'border-zinc-700 bg-zinc-900 text-zinc-400';
  }
}

function linkStatusBadge(status: string) {
  switch (status) {
    case 'active':
      return 'border-emerald-600/40 bg-emerald-950/20 text-emerald-300';
    case 'grace':
      return 'border-amber-600/40 bg-amber-950/20 text-amber-300';
    case 'terminated':
      return 'border-red-600/40 bg-red-950/20 text-red-300';
    default:
      return 'border-zinc-700 bg-zinc-900 text-zinc-400';
  }
}

function companyStatusBadge(status: string) {
  switch (status) {
    case 'approved':
      return 'text-emerald-400';
    case 'pending':
      return 'text-amber-400';
    case 'suspended':
      return 'text-red-400';
    default:
      return 'text-zinc-400';
  }
}

/* ---------- feature label map ---------- */

const FEATURE_LABELS: Record<string, string> = {
  offer_letters: 'Offer Letters',
  offer_letters_plus: 'Offer Letters+',
  policies: 'Policies',
  handbooks: 'Handbooks',
  compliance: 'Compliance',
  compliance_plus: 'Compliance+',
  employees: 'Employees',
  vibe_checks: 'Vibe Checks',
  enps: 'eNPS',
  performance_reviews: 'Performance Reviews',
  er_copilot: 'ER Copilot',
  incidents: 'Incidents',
  time_off: 'Time Off',
  accommodations: 'Accommodations',
  internal_mobility: 'Internal Mobility',
};

const ALL_FEATURES = Object.keys(FEATURE_LABELS);

const STATUS_FILTERS = ['all', 'draft', 'invited', 'activated', 'expired', 'cancelled'] as const;
type SetupStatus = (typeof STATUS_FILTERS)[number];

/* ---------- types ---------- */

interface ReferredClient {
  company_id: string;
  company_name: string;
  industry: string | null;
  company_size: string | null;
  company_status: string;
  link_status: string;
  linked_at: string | null;
  activated_at: string | null;
  active_employee_count: number;
  enabled_feature_count: number;
}

/* ---------- Create / Edit Modal ---------- */

interface SetupModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  editing?: BrokerClientSetup | null;
}

function SetupModal({ open, onClose, onSaved, editing }: SetupModalProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('');
  const [companySize, setCompanySize] = useState('');
  const [headcount, setHeadcount] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [inviteImmediately, setInviteImmediately] = useState(false);
  const [expiresDays, setExpiresDays] = useState('14');

  useEffect(() => {
    if (!open) return;
    if (editing) {
      setCompanyName(editing.company_name);
      setIndustry(editing.industry || '');
      setCompanySize(editing.company_size || '');
      setHeadcount(editing.headcount_hint?.toString() || '');
      setContactName(editing.contact_name || '');
      setContactEmail(editing.contact_email || '');
      setContactPhone(editing.contact_phone || '');
      setFeatures(editing.preconfigured_features || {});
      setInviteImmediately(false);
      setExpiresDays('14');
    } else {
      setCompanyName('');
      setIndustry('');
      setCompanySize('');
      setHeadcount('');
      setContactName('');
      setContactEmail('');
      setContactPhone('');
      setFeatures({});
      setInviteImmediately(false);
      setExpiresDays('14');
    }
    setError('');
    setSaving(false);
  }, [open, editing]);

  const toggleFeature = (key: string) => {
    setFeatures((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const enabledCount = Object.values(features).filter(Boolean).length;

  const handleSubmit = async () => {
    if (!companyName.trim()) {
      setError('Company name is required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      if (editing) {
        await brokerPortal.updateSetup(editing.id, {
          company_name: companyName.trim(),
          industry: industry.trim() || undefined,
          company_size: companySize.trim() || undefined,
          headcount: headcount ? parseInt(headcount, 10) : undefined,
          contact_name: contactName.trim() || undefined,
          contact_email: contactEmail.trim() || undefined,
          contact_phone: contactPhone.trim() || undefined,
          preconfigured_features: features,
        });
      } else {
        const data: BrokerClientSetupCreateRequest = {
          company_name: companyName.trim(),
          industry: industry.trim() || undefined,
          company_size: companySize.trim() || undefined,
          headcount: headcount ? parseInt(headcount, 10) : undefined,
          contact_name: contactName.trim() || undefined,
          contact_email: contactEmail.trim() || undefined,
          contact_phone: contactPhone.trim() || undefined,
          preconfigured_features: features,
          invite_immediately: inviteImmediately,
          invite_expires_days: inviteImmediately ? parseInt(expiresDays, 10) || 14 : undefined,
        };
        await brokerPortal.createSetup(data);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save setup');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  const inputCls =
    'w-full bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 rounded-sm';
  const labelCls = 'block text-[10px] uppercase tracking-wider text-zinc-500 mb-1';

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-16 px-4">
      <div className="fixed inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-zinc-900 border border-zinc-800 w-full max-w-lg max-h-[calc(100vh-8rem)] overflow-y-auto">
        <div className="sticky top-0 bg-zinc-900 border-b border-zinc-800 px-5 py-4 flex items-center justify-between z-10">
          <h2 className="text-base font-medium text-white">
            {editing ? 'Edit Client Setup' : 'New Client Setup'}
          </h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <X size={18} />
          </button>
        </div>
        <div className="p-5 space-y-4">
          {error && (
            <div className="border border-red-600/40 bg-red-950/20 p-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <div>
            <label className={labelCls}>
              Company Name <span className="text-red-400">*</span>
            </label>
            <input
              className={inputCls}
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Acme Corp"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Industry</label>
              <input
                className={inputCls}
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="Technology"
              />
            </div>
            <div>
              <label className={labelCls}>Company Size</label>
              <input
                className={inputCls}
                value={companySize}
                onChange={(e) => setCompanySize(e.target.value)}
                placeholder="50-100"
              />
            </div>
          </div>

          <div>
            <label className={labelCls}>Headcount</label>
            <input
              className={inputCls}
              type="number"
              value={headcount}
              onChange={(e) => setHeadcount(e.target.value)}
              placeholder="75"
            />
          </div>

          <div className="border-t border-zinc-800 pt-4">
            <p className={labelCls}>Contact Information</p>
            <div className="space-y-3 mt-2">
              <input
                className={inputCls}
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
                placeholder="Contact name"
              />
              <input
                className={inputCls}
                type="email"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                placeholder="contact@company.com"
              />
              <input
                className={inputCls}
                type="tel"
                value={contactPhone}
                onChange={(e) => setContactPhone(e.target.value)}
                placeholder="(555) 123-4567"
              />
            </div>
          </div>

          <div className="border-t border-zinc-800 pt-4">
            <p className={labelCls}>
              Pre-configured Features{' '}
              <span className="text-zinc-600 normal-case tracking-normal">
                ({enabledCount} selected)
              </span>
            </p>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 mt-2">
              {ALL_FEATURES.map((key) => (
                <label
                  key={key}
                  className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer hover:text-white py-0.5"
                >
                  <input
                    type="checkbox"
                    checked={!!features[key]}
                    onChange={() => toggleFeature(key)}
                    className="accent-emerald-500 rounded-sm"
                  />
                  {FEATURE_LABELS[key]}
                </label>
              ))}
            </div>
          </div>

          {!editing && (
            <div className="border-t border-zinc-800 pt-4 space-y-3">
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={inviteImmediately}
                  onChange={(e) => setInviteImmediately(e.target.checked)}
                  className="accent-emerald-500 rounded-sm"
                />
                Send invite immediately
              </label>
              {inviteImmediately && (
                <div>
                  <label className={labelCls}>Invite expires in (days)</label>
                  <input
                    className={inputCls}
                    type="number"
                    min={1}
                    max={90}
                    value={expiresDays}
                    onChange={(e) => setExpiresDays(e.target.value)}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        <div className="sticky bottom-0 bg-zinc-900 border-t border-zinc-800 px-5 py-4 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs uppercase tracking-wide text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="flex items-center gap-1.5 px-4 py-2 text-xs uppercase tracking-wide bg-white text-black hover:bg-zinc-200 disabled:opacity-50 transition-colors"
          >
            {saving && <Loader2 size={13} className="animate-spin" />}
            {editing ? 'Save Changes' : 'Create Setup'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Invite URL Copy Button ---------- */

function CopyInviteUrl({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-blue-400 hover:text-blue-300 transition-colors"
    >
      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
      {copied ? 'Copied' : 'Copy Link'}
    </button>
  );
}

/* ---------- Client Setups Tab ---------- */

function ClientSetupsTab() {
  const [setups, setSetups] = useState<BrokerClientSetup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState<SetupStatus>('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSetup, setEditingSetup] = useState<BrokerClientSetup | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadSetups = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const filter = statusFilter === 'all' ? undefined : statusFilter;
      const res = await brokerPortal.listSetups(filter);
      setSetups(res.setups);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load client setups');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadSetups();
  }, [loadSetups]);

  const handleSendInvite = async (setup: BrokerClientSetup) => {
    setActionLoading(setup.id);
    try {
      await brokerPortal.sendInvite(setup.id);
      await loadSetups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send invite');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (setup: BrokerClientSetup) => {
    setActionLoading(setup.id);
    try {
      await brokerPortal.cancelSetup(setup.id);
      await loadSetups();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel setup');
    } finally {
      setActionLoading(null);
    }
  };

  const handleEdit = (setup: BrokerClientSetup) => {
    setEditingSetup(setup);
    setModalOpen(true);
  };

  const openCreate = () => {
    setEditingSetup(null);
    setModalOpen(true);
  };

  const enabledFeatures = (feats: Record<string, boolean>) =>
    Object.entries(feats)
      .filter(([, v]) => v)
      .map(([k]) => k);

  const isEditable = (s: BrokerClientSetup) => s.status === 'draft' || s.status === 'invited';
  const isCancellable = (s: BrokerClientSetup) =>
    s.status === 'draft' || s.status === 'invited';

  return (
    <>
      <SetupModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingSetup(null);
        }}
        onSaved={loadSetups}
        editing={editingSetup}
      />

      {/* Header row */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 text-[10px] uppercase tracking-wider border rounded-sm transition-colors ${
                statusFilter === s
                  ? 'border-white/30 bg-white/10 text-white'
                  : 'border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-1.5 px-4 py-2 text-xs uppercase tracking-wide bg-white text-black hover:bg-zinc-200 transition-colors shrink-0"
        >
          <Plus size={14} />
          New Client Setup
        </button>
      </div>

      {error && (
        <div className="border border-red-600/40 bg-red-950/20 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Setup list */}
      {loading ? (
        <div className="bg-zinc-900 border border-zinc-800 p-8 text-center text-sm text-zinc-400">
          Loading...
        </div>
      ) : setups.length === 0 ? (
        <div className="bg-zinc-900 border border-zinc-800 p-10 text-center">
          <p className="text-sm text-zinc-400 mb-1">No client setups yet.</p>
          <p className="text-xs text-zinc-600">
            Create one to pre-configure a company and send an invite.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {setups.map((setup) => {
            const feats = enabledFeatures(setup.preconfigured_features);
            const busy = actionLoading === setup.id;
            return (
              <div
                key={setup.id}
                className="bg-zinc-900 border border-zinc-800 p-4 space-y-3"
              >
                {/* Top row */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-medium text-white truncate">
                        {setup.company_name}
                      </p>
                      <span
                        className={`inline-flex items-center border rounded px-2 py-0.5 text-[10px] uppercase tracking-wider ${setupStatusBadge(setup.status)}`}
                      >
                        {setup.status}
                      </span>
                    </div>
                    {(setup.contact_name || setup.contact_email) && (
                      <p className="text-xs text-zinc-500 mt-0.5 truncate">
                        {[setup.contact_name, setup.contact_email].filter(Boolean).join(' — ')}
                      </p>
                    )}
                    {(setup.industry || setup.company_size) && (
                      <p className="text-[10px] text-zinc-600 mt-0.5">
                        {[setup.industry, setup.company_size].filter(Boolean).join(' / ')}
                      </p>
                    )}
                  </div>
                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    {setup.status === 'draft' && (
                      <button
                        onClick={() => handleSendInvite(setup)}
                        disabled={busy}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] uppercase tracking-wide border border-blue-600/40 text-blue-300 hover:bg-blue-950/30 disabled:opacity-50 transition-colors"
                        title="Send Invite"
                      >
                        {busy ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Send size={12} />
                        )}
                        Invite
                      </button>
                    )}
                    {isEditable(setup) && (
                      <button
                        onClick={() => handleEdit(setup)}
                        disabled={busy}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] uppercase tracking-wide border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 disabled:opacity-50 transition-colors"
                        title="Edit"
                      >
                        <Pencil size={12} />
                        Edit
                      </button>
                    )}
                    {isCancellable(setup) && (
                      <button
                        onClick={() => handleCancel(setup)}
                        disabled={busy}
                        className="flex items-center gap-1 px-2.5 py-1.5 text-[10px] uppercase tracking-wide border border-red-600/30 text-red-400 hover:bg-red-950/30 disabled:opacity-50 transition-colors"
                        title="Cancel"
                      >
                        {busy ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <XCircle size={12} />
                        )}
                        Cancel
                      </button>
                    )}
                  </div>
                </div>

                {/* Feature pills */}
                {feats.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {feats.map((f) => (
                      <span
                        key={f}
                        className="px-2 py-0.5 text-[10px] border border-zinc-700 text-zinc-400 rounded-sm"
                      >
                        {FEATURE_LABELS[f] || f}
                      </span>
                    ))}
                  </div>
                )}

                {/* Invite URL */}
                {setup.invite_url && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-zinc-500 truncate font-mono max-w-[280px]">
                      {setup.invite_url}
                    </span>
                    <CopyInviteUrl url={setup.invite_url} />
                  </div>
                )}

                {/* Timestamps */}
                <div className="flex gap-4 text-[10px] text-zinc-600">
                  <span>Created {new Date(setup.created_at).toLocaleDateString()}</span>
                  {setup.invited_at && (
                    <span>Invited {new Date(setup.invited_at).toLocaleDateString()}</span>
                  )}
                  {setup.activated_at && (
                    <span>Activated {new Date(setup.activated_at).toLocaleDateString()}</span>
                  )}
                  {setup.invite_expires_at && setup.status === 'invited' && (
                    <span>
                      Expires {new Date(setup.invite_expires_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

/* ---------- Referred Clients Tab ---------- */

function ReferredClientsTab() {
  const { profile } = useAuth();
  const brokerProfile = asBrokerProfile(profile);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [clients, setClients] = useState<ReferredClient[]>([]);
  const [copied, setCopied] = useState(false);

  const referralLink = brokerProfile
    ? `${APP_BASE_URL}/register?via=${brokerProfile.broker_slug}`
    : '';

  const handleCopy = () => {
    if (!referralLink) return;
    navigator.clipboard.writeText(referralLink).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await brokerPortal.getReferredClients();
        setClients(response.clients);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load referred clients');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const activeCount = clients.filter((c) => c.link_status === 'active').length;

  return (
    <>
      {/* Referral link card */}
      <div className="bg-zinc-900 border border-zinc-800 p-5 space-y-3">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500">Your Referral Link</p>
        <div className="flex items-center gap-2">
          <div className="flex-1 bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-300 font-mono truncate rounded-sm">
            {referralLink || '—'}
          </div>
          <button
            onClick={handleCopy}
            disabled={!referralLink}
            className="flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wide border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition-colors disabled:opacity-40"
          >
            {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          {referralLink && (
            <a
              href={referralLink}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wide border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition-colors"
            >
              <ExternalLink size={13} />
              Preview
            </a>
          )}
        </div>
        <p className="text-xs text-zinc-500">
          Companies that register via this link are immediately approved and counted toward your
          referrals.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-zinc-900 border border-zinc-800 p-4">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Total Referred</p>
          <p className="text-2xl font-light text-white mt-1">{clients.length}</p>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 p-4">
          <p className="text-[10px] uppercase tracking-wider text-zinc-500">Active</p>
          <p className="text-2xl font-light text-emerald-400 mt-1">{activeCount}</p>
        </div>
      </div>

      {error && (
        <div className="border border-red-600/40 bg-red-950/20 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Clients table */}
      <div className="bg-zinc-900 border border-zinc-800 overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 text-[10px] uppercase tracking-wider text-zinc-500">
          Referred Companies
        </div>
        {loading ? (
          <div className="p-6 text-sm text-zinc-400">Loading...</div>
        ) : clients.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-sm text-zinc-400 mb-1">No referrals yet</p>
            <p className="text-xs text-zinc-600">Share your referral link to get started.</p>
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800 text-[10px] uppercase tracking-wider text-zinc-500">
                    <th className="text-left px-4 py-2 font-normal">Company</th>
                    <th className="text-left px-4 py-2 font-normal">Industry</th>
                    <th className="text-left px-4 py-2 font-normal">Status</th>
                    <th className="text-right px-4 py-2 font-normal">Employees</th>
                    <th className="text-right px-4 py-2 font-normal">Features</th>
                    <th className="text-left px-4 py-2 font-normal">Joined</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {clients.map((client) => (
                    <tr
                      key={client.company_id}
                      className="hover:bg-zinc-800/40 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <p className="text-white">{client.company_name}</p>
                        {client.company_size && (
                          <p className="text-[10px] text-zinc-500">{client.company_size}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{client.industry || '—'}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center border rounded px-2 py-0.5 text-[10px] uppercase tracking-wider ${linkStatusBadge(client.link_status)}`}
                        >
                          {client.link_status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-zinc-300">
                        {client.active_employee_count}
                      </td>
                      <td className="px-4 py-3 text-right text-zinc-300">
                        {client.enabled_feature_count}
                      </td>
                      <td className="px-4 py-3 text-zinc-400 text-xs">
                        {client.linked_at
                          ? new Date(client.linked_at).toLocaleDateString()
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden divide-y divide-zinc-800">
              {clients.map((client) => (
                <div key={client.company_id} className="p-4 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm text-white">{client.company_name}</p>
                      <p className="text-xs text-zinc-500">{client.industry || '—'}</p>
                    </div>
                    <span
                      className={`inline-flex items-center border rounded px-2 py-0.5 text-[10px] uppercase tracking-wider shrink-0 ${linkStatusBadge(client.link_status)}`}
                    >
                      {client.link_status}
                    </span>
                  </div>
                  <div className="flex gap-4 text-xs text-zinc-400">
                    <span>{client.active_employee_count} employees</span>
                    <span>{client.enabled_feature_count} features</span>
                    <span className={companyStatusBadge(client.company_status)}>
                      {client.company_status}
                    </span>
                  </div>
                  {client.linked_at && (
                    <p className="text-[10px] text-zinc-600">
                      Joined {new Date(client.linked_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}

/* ---------- Main Component ---------- */

type Tab = 'setups' | 'referred';

export default function BrokerClients() {
  const [activeTab, setActiveTab] = useState<Tab>('setups');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Clients</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Manage client setups and track referred companies.
        </p>
      </div>

      {/* Tab navigation */}
      <div className="flex gap-0 border-b border-zinc-800">
        <button
          onClick={() => setActiveTab('setups')}
          className={`px-4 py-2.5 text-xs uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === 'setups'
              ? 'border-white text-white'
              : 'border-transparent text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Client Setups
        </button>
        <button
          onClick={() => setActiveTab('referred')}
          className={`px-4 py-2.5 text-xs uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === 'referred'
              ? 'border-white text-white'
              : 'border-transparent text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Referred Clients
        </button>
      </div>

      {activeTab === 'setups' ? <ClientSetupsTab /> : <ReferredClientsTab />}
    </div>
  );
}
