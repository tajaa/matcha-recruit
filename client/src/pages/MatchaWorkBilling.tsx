import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { matchaWork, getAccessToken } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type {
  MWBillingBalanceResponse,
  MWBillingTransactionsResponse,
  MWCreditPack,
  MWCreditTransaction,
  MWSubscription,
} from '../types/matcha-work';

const API_BASE = import.meta.env.VITE_API_URL || '/api';
const PAGE_SIZE = 25;

function formatCents(cents: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(cents / 100);
}

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

function txLabel(t: MWCreditTransaction['transaction_type']): string {
  switch (t) {
    case 'purchase': return 'Purchase';
    case 'grant':    return 'Grant';
    case 'deduction': return 'Usage';
    case 'refund':   return 'Refund';
    default:         return 'Adjustment';
  }
}

function txBadgeClass(t: MWCreditTransaction['transaction_type']): string {
  switch (t) {
    case 'purchase': return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    case 'grant':    return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'deduction': return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    case 'refund':   return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
    default:         return 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Admin view
// ─────────────────────────────────────────────────────────────────────────────

interface CompanyCreditSummary {
  company_id: string;
  company_name: string;
  company_status: string;
  credits_remaining: number;
  total_credits_purchased: number;
  total_credits_granted: number;
  updated_at: string | null;
}

function AdminBillingView() {
  const [companies, setCompanies] = useState<CompanyCreditSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [grantTarget, setGrantTarget] = useState<CompanyCreditSummary | null>(null);
  const [grantAmount, setGrantAmount] = useState('');
  const [grantNote, setGrantNote] = useState('');
  const [granting, setGranting] = useState(false);
  const [grantError, setGrantError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_BASE}/matcha-work/billing/admin/companies`, {
        headers: { Authorization: `Bearer ${getAccessToken()}` },
      });
      if (!res.ok) throw new Error('Failed to load');
      setCompanies(await res.json());
    } catch {
      setError('Could not load company credits.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openGrant = (c: CompanyCreditSummary) => {
    setGrantTarget(c);
    setGrantAmount('');
    setGrantNote('');
    setGrantError(null);
  };

  const submitGrant = async () => {
    if (!grantTarget) return;
    const credits = parseInt(grantAmount, 10);
    if (isNaN(credits) || credits === 0) { setGrantError('Enter a non-zero amount'); return; }
    setGranting(true);
    setGrantError(null);
    try {
      const res = await fetch(
        `${API_BASE}/matcha-work/billing/admin/companies/${grantTarget.company_id}/grant`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${getAccessToken()}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ credits, description: grantNote || undefined }),
        }
      );
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail || 'Grant failed');
      }
      setNotice(`${credits > 0 ? '+' : ''}${credits.toLocaleString()} credits applied to ${grantTarget.company_name}.`);
      setGrantTarget(null);
      void load();
    } catch (err) {
      setGrantError(err instanceof Error ? err.message : 'Grant failed');
    } finally {
      setGranting(false);
    }
  };

  const totalRemaining  = companies.reduce((s, c) => s + c.credits_remaining, 0);
  const totalPurchased  = companies.reduce((s, c) => s + c.total_credits_purchased, 0);
  const totalGranted    = companies.reduce((s, c) => s + c.total_credits_granted, 0);
  const parsedAmount    = parseInt(grantAmount, 10);
  const amountIsValid   = !isNaN(parsedAmount) && parsedAmount !== 0;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-6xl mx-auto px-6 py-10 space-y-8">

        {/* Header */}
        <div className="border-b border-zinc-800 pb-6">
          <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">Matcha Work</p>
          <h1 className="text-2xl font-semibold text-zinc-100">Billing & Credits</h1>
          <p className="text-sm text-zinc-400 mt-1">
            Manage credit balances across all customer accounts.
          </p>
        </div>

        {notice && (
          <div className="flex items-start gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
            <span className="text-emerald-400 mt-0.5">✓</span>
            <p className="text-sm text-emerald-300">{notice}</p>
            <button onClick={() => setNotice(null)} className="ml-auto text-zinc-500 hover:text-zinc-300">✕</button>
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-300">{error}</div>
        )}

        {/* Platform totals */}
        {!loading && (
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Credits in Use', value: totalRemaining.toLocaleString(), sub: 'across all accounts' },
              { label: 'Total Purchased', value: totalPurchased.toLocaleString(), sub: 'via Stripe' },
              { label: 'Total Granted', value: totalGranted.toLocaleString(), sub: 'manual grants' },
            ].map(s => (
              <div key={s.label} className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-5 py-4">
                <p className="text-xs uppercase tracking-widest text-zinc-500 mb-2">{s.label}</p>
                <p className="text-3xl font-semibold tabular-nums text-zinc-100">{s.value}</p>
                <p className="text-xs text-zinc-600 mt-1">{s.sub}</p>
              </div>
            ))}
          </div>
        )}

        {/* Company table */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-zinc-400">Customer Accounts</h2>
            <span className="text-xs text-zinc-600">{companies.length} companies</span>
          </div>

          <div className="rounded-xl border border-zinc-800 overflow-hidden">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/80">
                  {['Company', 'Credits Remaining', 'Purchased', 'Granted', 'Last Activity', ''].map(h => (
                    <th key={h} className={`px-5 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium ${h === 'Company' || h === '' ? 'text-left' : 'text-right'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {loading && (
                  <tr><td colSpan={6} className="px-5 py-12 text-center text-sm text-zinc-600">Loading…</td></tr>
                )}
                {!loading && companies.length === 0 && (
                  <tr><td colSpan={6} className="px-5 py-12 text-center text-sm text-zinc-600">No companies found.</td></tr>
                )}
                {companies.map(c => {
                  const low = c.credits_remaining > 0 && c.credits_remaining < 20;
                  const empty = c.credits_remaining <= 0;
                  return (
                    <tr key={c.company_id} className="bg-zinc-950 hover:bg-zinc-900/40 transition-colors">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-md bg-zinc-800 flex items-center justify-center text-xs font-semibold text-zinc-400 flex-shrink-0">
                            {c.company_name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-zinc-200">{c.company_name}</p>
                            {c.company_status === 'pending' && (
                              <p className="text-[10px] text-amber-500 uppercase tracking-wider">Pending approval</p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <span className={`text-sm font-semibold tabular-nums ${empty ? 'text-red-400' : low ? 'text-amber-400' : 'text-zinc-100'}`}>
                          {c.credits_remaining.toLocaleString()}
                        </span>
                        {(empty || low) && (
                          <p className="text-[10px] text-zinc-600 mt-0.5">{empty ? 'out of credits' : 'running low'}</p>
                        )}
                      </td>
                      <td className="px-5 py-3.5 text-right text-sm tabular-nums text-zinc-400">{c.total_credits_purchased.toLocaleString()}</td>
                      <td className="px-5 py-3.5 text-right text-sm tabular-nums text-zinc-400">{c.total_credits_granted.toLocaleString()}</td>
                      <td className="px-5 py-3.5 text-right text-xs text-zinc-600">{c.updated_at ? formatDate(c.updated_at) : '—'}</td>
                      <td className="px-5 py-3.5 text-right">
                        <button
                          onClick={() => openGrant(c)}
                          className="px-3 py-1.5 text-xs font-medium rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-zinc-100 border border-zinc-700 hover:border-zinc-600 transition-all"
                        >
                          Grant Credits
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Grant modal */}
      {grantTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={e => { if (e.target === e.currentTarget) setGrantTarget(null); }}
        >
          <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-sm mx-4 shadow-2xl">
            <div className="px-6 py-5 border-b border-zinc-800">
              <h3 className="text-base font-semibold text-zinc-100">Grant Credits</h3>
              <p className="text-xs text-zinc-500 mt-0.5">{grantTarget.company_name}</p>
            </div>

            <div className="px-6 py-5 space-y-4">
              <div className="flex items-center justify-between rounded-lg bg-zinc-900 border border-zinc-800 px-4 py-3">
                <span className="text-xs text-zinc-500 uppercase tracking-wider">Current balance</span>
                <span className="text-sm font-semibold text-zinc-200 tabular-nums">{grantTarget.credits_remaining.toLocaleString()}</span>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                  Credits <span className="text-zinc-600 font-normal">(negative to deduct)</span>
                </label>
                <input
                  type="number"
                  value={grantAmount}
                  onChange={e => setGrantAmount(e.target.value)}
                  placeholder="500"
                  autoFocus
                  className="w-full bg-zinc-900 border border-zinc-700 text-zinc-100 text-sm px-3.5 py-2.5 rounded-lg focus:outline-none focus:border-zinc-500 placeholder:text-zinc-700 transition-colors"
                />
                {amountIsValid && (
                  <p className="mt-1.5 text-xs text-zinc-500">
                    New balance: <span className="text-zinc-300 font-medium">{Math.max(0, grantTarget.credits_remaining + parsedAmount).toLocaleString()}</span>
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                  Note <span className="text-zinc-600 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  value={grantNote}
                  onChange={e => setGrantNote(e.target.value)}
                  placeholder="e.g. Courtesy credits for onboarding"
                  className="w-full bg-zinc-900 border border-zinc-700 text-zinc-100 text-sm px-3.5 py-2.5 rounded-lg focus:outline-none focus:border-zinc-500 placeholder:text-zinc-700 transition-colors"
                />
              </div>

              {grantError && <p className="text-xs text-red-400">{grantError}</p>}
            </div>

            <div className="px-6 py-4 border-t border-zinc-800 flex items-center justify-end gap-3">
              <button
                onClick={() => setGrantTarget(null)}
                className="px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void submitGrant()}
                disabled={granting || !amountIsValid}
                className="px-5 py-2 text-sm font-medium rounded-lg bg-zinc-100 text-zinc-950 hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                {granting
                  ? 'Applying…'
                  : amountIsValid
                    ? `Apply ${parsedAmount > 0 ? '+' : ''}${parsedAmount.toLocaleString()} credits`
                    : 'Apply Credits'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Client view
// ─────────────────────────────────────────────────────────────────────────────

function ClientBillingView() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [balance, setBalance]           = useState<MWBillingBalanceResponse | null>(null);
  const [packs, setPacks]               = useState<MWCreditPack[]>([]);
  const [subscription, setSubscription] = useState<MWSubscription | null>(null);
  const [transactions, setTransactions] = useState<MWBillingTransactionsResponse | null>(null);
  const [offset, setOffset]             = useState(0);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState<string | null>(null);
  const [notice, setNotice]             = useState<string | null>(null);

  const [autoRenewFlags, setAutoRenewFlags] = useState<Record<string, boolean>>({});
  const [buyingPackId, setBuyingPackId]     = useState<string | null>(null);
  const [cancelingSub, setCancelingSub]     = useState(false);

  const totalPages  = useMemo(() => (!transactions ? 1 : Math.max(1, Math.ceil(transactions.total / transactions.limit))), [transactions]);
  const currentPage = useMemo(() => (!transactions ? 1 : Math.floor(transactions.offset / transactions.limit) + 1), [transactions]);

  const loadData = useCallback(async (nextOffset: number) => {
    try {
      setLoading(true); setError(null);
      const [bal, pks, sub, tx] = await Promise.all([
        matchaWork.getBillingBalance(),
        matchaWork.getCreditPacks(),
        matchaWork.getSubscription(),
        matchaWork.getBillingTransactions({ limit: PAGE_SIZE, offset: nextOffset }),
      ]);
      setBalance(bal); setPacks(pks); setSubscription(sub); setTransactions(tx); setOffset(nextOffset);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load billing data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(0); }, [loadData]);

  useEffect(() => {
    if (searchParams.get('success') === '1') {
      setNotice('Payment completed. Credits are being applied now.');
      setSearchParams({}, { replace: true });
      void loadData(0);
    } else if (searchParams.get('canceled') === '1') {
      setNotice('Checkout canceled. No credits were added.');
      setSearchParams({}, { replace: true });
    }
  }, [loadData, searchParams, setSearchParams]);

  const handleBuy = async (packId: string) => {
    const autoRenew = autoRenewFlags[packId] ?? false;
    try {
      setBuyingPackId(packId); setError(null);
      const s = await matchaWork.createCheckout(packId, autoRenew);
      if (!s.checkout_url) throw new Error('Checkout URL missing');
      window.location.href = s.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start checkout');
      setBuyingPackId(null);
    }
  };

  const handleCancelSub = async () => {
    if (!confirm('Cancel your subscription? Credits remain until used and no further payments will be taken.')) return;
    try {
      setCancelingSub(true); setError(null);
      await matchaWork.cancelSubscription();
      setNotice('Subscription canceled. It will not renew at the end of the current period.');
      void loadData(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel subscription');
    } finally {
      setCancelingSub(false);
    }
  };

  const credits   = balance?.credits_remaining ?? 0;
  const low       = credits > 0 && credits < 10;
  const activeSub = subscription?.active ? subscription : null;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-4xl mx-auto px-6 py-10 space-y-10">

        {/* Header */}
        <div className="border-b border-zinc-800 pb-6">
          <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">Matcha Work</p>
          <h1 className="text-2xl font-semibold text-zinc-100">Billing & Credits</h1>
          <p className="text-sm text-zinc-400 mt-1">Credits are shared across all admins in your organization.</p>
        </div>

        {notice && (
          <div className="flex items-start gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
            <span className="text-emerald-400 mt-0.5 text-sm">✓</span>
            <p className="text-sm text-emerald-300 flex-1">{notice}</p>
            <button onClick={() => setNotice(null)} className="text-zinc-500 hover:text-zinc-300 text-xs">✕</button>
          </div>
        )}
        {error && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-300">{error}</div>
        )}

        {/* Balance + subscription */}
        <div className="grid sm:grid-cols-2 gap-4">
          {/* Balance */}
          <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 px-6 py-5">
            <p className="text-xs uppercase tracking-widest text-zinc-500 mb-3">Credits Remaining</p>
            <p className={`text-5xl font-semibold tabular-nums ${credits <= 0 ? 'text-red-400' : low ? 'text-amber-400' : 'text-zinc-100'}`}>
              {credits.toLocaleString()}
            </p>
            <div className="mt-4 pt-4 border-t border-zinc-800 grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-zinc-600 mb-0.5">Purchased</p>
                <p className="text-zinc-300 font-medium tabular-nums">{(balance?.total_credits_purchased ?? 0).toLocaleString()}</p>
              </div>
              <div>
                <p className="text-zinc-600 mb-0.5">Granted</p>
                <p className="text-zinc-300 font-medium tabular-nums">{(balance?.total_credits_granted ?? 0).toLocaleString()}</p>
              </div>
            </div>
            {credits <= 0 && <p className="mt-3 text-xs text-red-400">Out of credits — purchase a pack below to continue.</p>}
            {low && <p className="mt-3 text-xs text-amber-400">Running low — fewer than 10 credits remaining.</p>}
          </div>

          {/* Subscription or placeholder */}
          {activeSub ? (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 px-6 py-5">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <p className="text-xs font-semibold uppercase tracking-widest text-emerald-400">Auto-Renew Active</p>
              </div>
              <p className="text-3xl font-semibold tabular-nums text-zinc-100">{activeSub.credits_per_cycle?.toLocaleString()}</p>
              <p className="text-sm text-zinc-400 mt-1">credits / month</p>
              <div className="mt-4 pt-4 border-t border-emerald-500/10 space-y-1 text-xs text-zinc-500">
                {activeSub.amount_cents && <p>{formatCents(activeSub.amount_cents)} billed monthly</p>}
                {activeSub.current_period_end && <p>Next renewal {formatDate(activeSub.current_period_end)}</p>}
              </div>
              {activeSub.canceled_at ? (
                <p className="mt-3 text-xs text-amber-400">Cancels at period end</p>
              ) : (
                <button
                  onClick={() => void handleCancelSub()}
                  disabled={cancelingSub}
                  className="mt-4 text-xs text-zinc-600 hover:text-red-400 transition-colors disabled:opacity-50"
                >
                  {cancelingSub ? 'Canceling…' : 'Cancel subscription'}
                </button>
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-zinc-800 border-dashed bg-transparent px-6 py-5 flex flex-col items-center justify-center text-center gap-2">
              <p className="text-sm font-medium text-zinc-400">No active subscription</p>
              <p className="text-xs text-zinc-600">Enable auto-renew on any pack below to subscribe.</p>
            </div>
          )}
        </div>

        {/* Credit packs */}
        <section>
          <div className="mb-5">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-zinc-400">Top Up Credits</h2>
            <p className="text-xs text-zinc-600 mt-1">All credits go into a shared pool. A $2.50 processing fee applies.</p>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            {packs.map(pack => {
              const autoRenew  = autoRenewFlags[pack.pack_id] ?? false;
              const isBuying   = buyingPackId === pack.pack_id;
              const isBlocked  = Boolean(buyingPackId) && !isBuying;
              const hasThisSub = activeSub?.pack_id === pack.pack_id && !activeSub.canceled_at;

              return (
                <div key={pack.pack_id} className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 flex flex-col gap-5">
                  <div>
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-xs uppercase tracking-widest text-zinc-500 mb-1">{pack.label}</p>
                        <div className="flex items-baseline gap-2">
                          <span className="text-4xl font-semibold tabular-nums text-zinc-100">{pack.credits.toLocaleString()}</span>
                          <span className="text-sm text-zinc-500">credits</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-xl font-semibold text-zinc-100">{formatCents(pack.amount_cents)}</p>
                        <p className="text-xs text-zinc-600 mt-0.5">incl. {formatCents(pack.fee_cents)} fee</p>
                      </div>
                    </div>
                  </div>

                  {/* Auto-renew toggle */}
                  <div className="flex items-center justify-between gap-4 rounded-xl bg-zinc-800/50 border border-zinc-800 px-4 py-3">
                    <div>
                      <p className="text-xs font-medium text-zinc-300">Auto-renew monthly</p>
                      <p className="text-[11px] text-zinc-600 mt-0.5">
                        {autoRenew ? `${formatCents(pack.amount_cents)}/mo · renews automatically` : 'One-time purchase'}
                      </p>
                    </div>
                    <button
                      onClick={() => setAutoRenewFlags(p => ({ ...p, [pack.pack_id]: !p[pack.pack_id] }))}
                      role="switch"
                      aria-checked={autoRenew}
                      className={`relative w-10 h-[22px] rounded-full transition-colors flex-shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${autoRenew ? 'bg-emerald-500' : 'bg-zinc-700'}`}
                    >
                      <span className={`absolute top-[3px] left-[3px] w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${autoRenew ? 'translate-x-[18px]' : 'translate-x-0'}`} />
                    </button>
                  </div>

                  {hasThisSub && !autoRenew ? (
                    <div className="flex items-center justify-center gap-1.5 py-2 text-xs text-emerald-400">
                      <span>✓</span> <span>Auto-renewing — manage above</span>
                    </div>
                  ) : (
                    <button
                      onClick={() => void handleBuy(pack.pack_id)}
                      disabled={isBuying || isBlocked}
                      className="w-full py-3 rounded-xl bg-zinc-100 text-zinc-950 text-sm font-semibold hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                    >
                      {isBuying
                        ? 'Redirecting…'
                        : autoRenew
                          ? `Subscribe · ${formatCents(pack.amount_cents)}/mo`
                          : `Buy once · ${formatCents(pack.amount_cents)}`}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Transaction history */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-zinc-400">Transaction History</h2>
            {transactions && transactions.total > PAGE_SIZE && (
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <button
                  onClick={() => void loadData(Math.max(0, offset - PAGE_SIZE))}
                  disabled={loading || offset <= 0}
                  className="px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800 hover:border-zinc-700 disabled:opacity-40 transition-colors"
                >← Prev</button>
                <span>{currentPage} / {totalPages}</span>
                <button
                  onClick={() => void loadData(offset + PAGE_SIZE)}
                  disabled={loading || !transactions || offset + PAGE_SIZE >= transactions.total}
                  className="px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800 hover:border-zinc-700 disabled:opacity-40 transition-colors"
                >Next →</button>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-zinc-800 overflow-hidden">
            <table className="min-w-full">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/80">
                  {['Type', 'Amount', 'Balance After', 'Description', 'Date'].map((h, i) => (
                    <th key={h} className={`px-5 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium ${i === 0 ? 'text-left' : i >= 1 && i <= 2 ? 'text-right' : 'text-left'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/60">
                {(transactions?.items ?? []).map(tx => (
                  <tr key={tx.id} className="bg-zinc-950 hover:bg-zinc-900/40 transition-colors">
                    <td className="px-5 py-3.5">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium uppercase tracking-wider border ${txBadgeClass(tx.transaction_type)}`}>
                        {txLabel(tx.transaction_type)}
                      </span>
                    </td>
                    <td className={`px-5 py-3.5 text-right text-sm font-semibold tabular-nums ${tx.credits_delta >= 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {tx.credits_delta >= 0 ? '+' : ''}{tx.credits_delta.toLocaleString()}
                    </td>
                    <td className="px-5 py-3.5 text-right text-sm tabular-nums text-zinc-400">{tx.credits_after.toLocaleString()}</td>
                    <td className="px-5 py-3.5 text-sm text-zinc-500 max-w-xs truncate">{tx.description || '—'}</td>
                    <td className="px-5 py-3.5 text-xs text-zinc-600 whitespace-nowrap">{formatTs(tx.created_at)}</td>
                  </tr>
                ))}
                {!loading && (transactions?.items.length ?? 0) === 0 && (
                  <tr>
                    <td colSpan={5} className="px-5 py-12 text-center text-sm text-zinc-600">No transactions yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Root
// ─────────────────────────────────────────────────────────────────────────────

export default function MatchaWorkBilling() {
  const { user } = useAuth();
  return user?.role === 'admin' ? <AdminBillingView /> : <ClientBillingView />;
}
