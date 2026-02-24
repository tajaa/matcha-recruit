import { useState, useEffect, useCallback } from 'react';
import { adminBrokers } from '../../api/client';
import type { AdminBroker, AdminBrokerCreateRequest } from '../../api/client';
import { Building2, Plus, X, ChevronDown } from 'lucide-react';

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  pending: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  suspended: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  terminated: 'bg-red-500/10 text-red-400 border-red-500/20',
};

const BRANDING_STYLES: Record<string, string> = {
  direct: 'text-zinc-500',
  co_branded: 'text-blue-400',
  white_label: 'text-purple-400',
};

const STATUSES = ['pending', 'active', 'suspended', 'terminated'] as const;
const SUPPORT_ROUTINGS = ['shared', 'broker_first', 'matcha_first'] as const;
const BILLING_MODES = ['direct', 'reseller', 'hybrid'] as const;
const INVOICE_OWNERS = ['matcha', 'broker'] as const;

const EMPTY_CREATE: AdminBrokerCreateRequest = {
  broker_name: '',
  owner_email: '',
  owner_name: '',
  owner_password: '',
  slug: '',
  support_routing: 'shared',
  billing_mode: 'direct',
  invoice_owner: 'matcha',
  terms_required_version: 'v1',
};

export function BrokerManagement() {
  const [brokers, setBrokers] = useState<AdminBroker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create modal
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<AdminBrokerCreateRequest>(EMPTY_CREATE);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Inline status editing
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const fetchBrokers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await adminBrokers.list();
      setBrokers(data.brokers);
    } catch {
      setError('Failed to load brokers');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBrokers();
  }, [fetchBrokers]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const payload: AdminBrokerCreateRequest = {
        ...createForm,
        slug: createForm.slug?.trim() || undefined,
        owner_password: createForm.owner_password?.trim() || undefined,
      };
      await adminBrokers.create(payload);
      setShowCreate(false);
      setCreateForm(EMPTY_CREATE);
      await fetchBrokers();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create broker');
    } finally {
      setCreating(false);
    }
  };

  const handleStatusChange = async (broker: AdminBroker, newStatus: string) => {
    if (newStatus === broker.status) { setEditingStatus(null); return; }
    setUpdatingId(broker.id);
    setEditingStatus(null);
    try {
      const updated = await adminBrokers.update(broker.id, { status: newStatus });
      setBrokers(prev => prev.map(b => b.id === broker.id ? { ...b, status: updated.status as AdminBroker['status'] } : b));
    } catch {
      setError('Failed to update broker status');
    } finally {
      setUpdatingId(null);
    }
  };

  const handleRoutingChange = async (broker: AdminBroker, newRouting: string) => {
    setUpdatingId(broker.id);
    try {
      await adminBrokers.update(broker.id, { support_routing: newRouting });
      setBrokers(prev => prev.map(b => b.id === broker.id ? { ...b, support_routing: newRouting as AdminBroker['support_routing'] } : b));
    } catch {
      setError('Failed to update support routing');
    } finally {
      setUpdatingId(null);
    }
  };

  const fmt = (n: number | null | undefined, prefix = '$') =>
    n != null ? `${prefix}${n.toLocaleString()}` : '—';

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-3 border-b border-white/10 pb-6 md:pb-8">
        <div>
          <h1 className="text-2xl md:text-4xl font-bold tracking-tighter text-white uppercase">Broker Management</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Manage brokerage partnerships and their client companies
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 font-mono">
            {brokers.length} Brokers
          </div>
          <button
            onClick={() => { setShowCreate(true); setCreateError(null); }}
            className="flex items-center gap-2 px-4 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
          >
            <Plus size={14} />
            New Broker
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="border border-white/10 bg-zinc-900/30">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading brokers...</div>
          </div>
        ) : brokers.length === 0 ? (
          <div className="text-center py-24 text-zinc-500 font-mono text-sm uppercase tracking-wider">
            No brokers found
          </div>
        ) : (
          <>
            {/* Desktop */}
            <div className="hidden lg:block overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10 bg-zinc-950">
                    <th className="text-left px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Broker</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Status</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Branding</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Members</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Companies</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Base Fee</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">PEPM</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Support Routing</th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Billing</th>
                  </tr>
                </thead>
                <tbody>
                  {brokers.map((broker) => (
                    <tr key={broker.id} className="border-b border-white/5 hover:bg-white/5 transition-colors bg-zinc-950">
                      {/* Name */}
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center flex-shrink-0">
                            <Building2 size={14} className="text-zinc-400" />
                          </div>
                          <div>
                            <div className="text-sm text-white font-bold">{broker.name}</div>
                            <div className="text-[10px] text-zinc-500 font-mono">/{broker.slug}</div>
                          </div>
                        </div>
                      </td>

                      {/* Status — inline dropdown */}
                      <td className="text-center px-4 py-4">
                        <div className="relative inline-block">
                          <button
                            onClick={() => setEditingStatus(editingStatus === broker.id ? null : broker.id)}
                            disabled={updatingId === broker.id}
                            className={`flex items-center gap-1 px-2 py-1 text-[9px] font-bold uppercase tracking-wider border ${STATUS_STYLES[broker.status] ?? 'text-zinc-400 border-zinc-700'} ${updatingId === broker.id ? 'opacity-50' : 'hover:opacity-80'} transition-opacity`}
                          >
                            {broker.status}
                            <ChevronDown size={10} />
                          </button>
                          {editingStatus === broker.id && (
                            <div className="absolute top-full mt-1 left-1/2 -translate-x-1/2 z-20 bg-zinc-900 border border-zinc-700 shadow-xl min-w-[120px]">
                              {STATUSES.map(s => (
                                <button
                                  key={s}
                                  onClick={() => handleStatusChange(broker, s)}
                                  className={`block w-full text-left px-3 py-2 text-[10px] uppercase tracking-wider hover:bg-zinc-800 transition-colors ${s === broker.status ? 'text-white font-bold' : 'text-zinc-400'}`}
                                >
                                  {s}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Branding */}
                      <td className="text-center px-4 py-4">
                        <span className={`text-[10px] font-mono uppercase tracking-wider ${BRANDING_STYLES[broker.branding_mode] ?? 'text-zinc-500'}`}>
                          {broker.branding_mode.replace('_', ' ')}
                        </span>
                      </td>

                      {/* Members */}
                      <td className="text-center px-4 py-4">
                        <span className="text-sm text-white font-mono">{broker.active_member_count}</span>
                      </td>

                      {/* Companies */}
                      <td className="text-center px-4 py-4">
                        <span className="text-sm text-white font-mono">{broker.active_company_count}</span>
                      </td>

                      {/* Base Fee */}
                      <td className="text-center px-4 py-4">
                        <span className="text-xs text-zinc-300 font-mono">{fmt(broker.active_contract?.base_platform_fee)}</span>
                      </td>

                      {/* PEPM */}
                      <td className="text-center px-4 py-4">
                        <span className="text-xs text-zinc-300 font-mono">{fmt(broker.active_contract?.pepm_rate)}</span>
                      </td>

                      {/* Support Routing */}
                      <td className="text-center px-4 py-4">
                        <select
                          value={broker.support_routing}
                          onChange={(e) => handleRoutingChange(broker, e.target.value)}
                          disabled={updatingId === broker.id}
                          className="bg-zinc-900 border border-zinc-700 text-zinc-300 text-[10px] uppercase tracking-wider px-2 py-1 focus:outline-none focus:border-zinc-500 disabled:opacity-50"
                        >
                          {SUPPORT_ROUTINGS.map(r => (
                            <option key={r} value={r}>{r.replace('_', ' ')}</option>
                          ))}
                        </select>
                      </td>

                      {/* Billing */}
                      <td className="text-center px-4 py-4">
                        <div className="flex flex-col items-center gap-0.5">
                          <span className="text-[10px] text-zinc-400 font-mono uppercase">{broker.billing_mode}</span>
                          <span className="text-[9px] text-zinc-600 font-mono uppercase">inv: {broker.invoice_owner}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile card layout */}
            <div className="lg:hidden divide-y divide-white/5">
              {brokers.map((broker) => (
                <div key={broker.id} className="p-4 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                        <Building2 size={14} className="text-zinc-400" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm text-white font-bold truncate">{broker.name}</div>
                        <div className="text-[10px] text-zinc-500 font-mono">/{broker.slug}</div>
                      </div>
                    </div>
                    <span className={`text-[9px] px-1.5 py-0.5 uppercase tracking-wider font-bold border shrink-0 ${STATUS_STYLES[broker.status] ?? 'text-zinc-400 border-zinc-700'}`}>
                      {broker.status}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="bg-zinc-900 border border-zinc-800 px-2 py-2">
                      <div className="text-[9px] text-zinc-500 uppercase tracking-wider">Members</div>
                      <div className="text-sm text-white font-mono mt-0.5">{broker.active_member_count}</div>
                    </div>
                    <div className="bg-zinc-900 border border-zinc-800 px-2 py-2">
                      <div className="text-[9px] text-zinc-500 uppercase tracking-wider">Companies</div>
                      <div className="text-sm text-white font-mono mt-0.5">{broker.active_company_count}</div>
                    </div>
                    <div className="bg-zinc-900 border border-zinc-800 px-2 py-2">
                      <div className="text-[9px] text-zinc-500 uppercase tracking-wider">Branding</div>
                      <div className={`text-[10px] font-mono mt-0.5 uppercase ${BRANDING_STYLES[broker.branding_mode] ?? 'text-zinc-500'}`}>
                        {broker.branding_mode.replace('_', ' ')}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] text-zinc-500 font-mono">
                    <span>Routing: <span className="text-zinc-300">{broker.support_routing.replace('_', ' ')}</span></span>
                    <span>·</span>
                    <span>Billing: <span className="text-zinc-300">{broker.billing_mode}</span></span>
                    {broker.active_contract?.pepm_rate != null && (
                      <>
                        <span>·</span>
                        <span>PEPM: <span className="text-zinc-300">${broker.active_contract.pepm_rate}</span></span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Create Broker Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <div>
                <h3 className="text-lg font-bold text-white uppercase tracking-tight">New Broker</h3>
                <p className="text-xs text-zinc-500 mt-1">Create a brokerage account with an owner user</p>
              </div>
              <button onClick={() => setShowCreate(false)} className="text-zinc-500 hover:text-white transition-colors">
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreate} className="p-6 space-y-4">
              {createError && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                  {createError}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Broker Name *</label>
                  <input
                    required
                    value={createForm.broker_name}
                    onChange={(e) => setCreateForm(f => ({ ...f, broker_name: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
                    placeholder="Acme Brokerage"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Slug (optional)</label>
                  <input
                    value={createForm.slug}
                    onChange={(e) => setCreateForm(f => ({ ...f, slug: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
                    placeholder="acme-brokerage"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Terms Version</label>
                  <input
                    value={createForm.terms_required_version}
                    onChange={(e) => setCreateForm(f => ({ ...f, terms_required_version: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Owner Name *</label>
                  <input
                    required
                    value={createForm.owner_name}
                    onChange={(e) => setCreateForm(f => ({ ...f, owner_name: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
                    placeholder="Jane Smith"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Owner Email *</label>
                  <input
                    required
                    type="email"
                    value={createForm.owner_email}
                    onChange={(e) => setCreateForm(f => ({ ...f, owner_email: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
                    placeholder="jane@acme.com"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Owner Password (leave blank to auto-generate)</label>
                  <input
                    type="password"
                    value={createForm.owner_password}
                    onChange={(e) => setCreateForm(f => ({ ...f, owner_password: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500 placeholder:text-zinc-600"
                    placeholder="min 8 characters"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Support Routing</label>
                  <select
                    value={createForm.support_routing}
                    onChange={(e) => setCreateForm(f => ({ ...f, support_routing: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500"
                  >
                    {SUPPORT_ROUTINGS.map(r => <option key={r} value={r}>{r.replace('_', ' ')}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Billing Mode</label>
                  <select
                    value={createForm.billing_mode}
                    onChange={(e) => setCreateForm(f => ({ ...f, billing_mode: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500"
                  >
                    {BILLING_MODES.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Invoice Owner</label>
                  <select
                    value={createForm.invoice_owner}
                    onChange={(e) => setCreateForm(f => ({ ...f, invoice_owner: e.target.value }))}
                    className="w-full bg-zinc-900 border border-zinc-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-500"
                  >
                    {INVOICE_OWNERS.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {creating ? 'Creating...' : 'Create Broker'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Click-outside to close status dropdown */}
      {editingStatus && (
        <div className="fixed inset-0 z-10" onClick={() => setEditingStatus(null)} />
      )}
    </div>
  );
}

export default BrokerManagement;
