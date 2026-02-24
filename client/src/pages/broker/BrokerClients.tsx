import { useEffect, useState } from 'react';
import { brokerPortal } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type { BrokerAuthProfile } from '../../types';
import { Check, Copy, ExternalLink } from 'lucide-react';

const APP_BASE_URL = window.location.origin;

function asBrokerProfile(profile: unknown): BrokerAuthProfile | null {
  if (!profile || typeof profile !== 'object') return null;
  if (!('broker_id' in profile)) return null;
  return profile as BrokerAuthProfile;
}

function statusBadge(status: string) {
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

export default function BrokerClients() {
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
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Your Referred Clients</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Share your referral link — when a company registers through it, they're auto-approved and linked to you.
        </p>
      </div>

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
          Companies that register via this link are immediately approved and counted toward your referrals.
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
        <div className="border border-red-600/40 bg-red-950/20 p-3 text-sm text-red-300">{error}</div>
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
                    <tr key={client.company_id} className="hover:bg-zinc-800/40 transition-colors">
                      <td className="px-4 py-3">
                        <p className="text-white">{client.company_name}</p>
                        {client.company_size && (
                          <p className="text-[10px] text-zinc-500">{client.company_size}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{client.industry || '—'}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center border rounded px-2 py-0.5 text-[10px] uppercase tracking-wider ${statusBadge(client.link_status)}`}
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
                      className={`inline-flex items-center border rounded px-2 py-0.5 text-[10px] uppercase tracking-wider shrink-0 ${statusBadge(client.link_status)}`}
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
    </div>
  );
}
