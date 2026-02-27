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
    <div className="max-w-5xl mx-auto space-y-12">

      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Billing & Credits</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Manage credit balances across all customer accounts</p>
        </div>
      </div>

      {notice && (
        <div className="border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-xs text-emerald-400 flex items-center justify-between">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="text-zinc-600 hover:text-zinc-300 ml-4">✕</button>
        </div>
      )}
      {error && (
        <div className="border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-400">{error}</div>
      )}

      {!loading && (
        <div className="grid grid-cols-3 gap-px bg-white/10 border border-white/10">
          {[
            { label: 'Credits in Use', value: totalRemaining.toLocaleString(), sub: 'across all accounts' },
            { label: 'Total Purchased', value: totalPurchased.toLocaleString(), sub: 'via Stripe' },
            { label: 'Total Granted', value: totalGranted.toLocaleString(), sub: 'manual grants' },
          ].map(s => (
            <div key={s.label} className="bg-zinc-950 px-6 py-6">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">{s.label}</div>
              <div className="text-4xl font-light font-mono text-white">{s.value}</div>
              <div className="text-[10px] text-zinc-600 mt-2 font-mono">{s.sub}</div>
            </div>
          ))}
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Customer Accounts</div>
          <span className="text-[10px] text-zinc-600 font-mono">{companies.length} companies</span>
        </div>
        <div className="border border-white/10">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-white/10">
                {['Company', 'Credits Remaining', 'Purchased', 'Granted', 'Last Activity', ''].map(h => (
                  <th key={h} className={`px-5 py-3 text-[10px] uppercase tracking-widest text-zinc-600 font-bold ${h === 'Company' || h === '' ? 'text-left' : 'text-right'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading && (
                <tr><td colSpan={6} className="px-5 py-12 text-center text-xs text-zinc-600 animate-pulse">Loading…</td></tr>
              )}
              {!loading && companies.length === 0 && (
                <tr><td colSpan={6} className="px-5 py-12 text-center text-xs text-zinc-600">No companies found.</td></tr>
              )}
              {companies.map(c => {
                const low = c.credits_remaining > 0 && c.credits_remaining < 20;
                const empty = c.credits_remaining <= 0;
                return (
                  <tr key={c.company_id} className="bg-zinc-950 hover:bg-zinc-900/30 transition-colors">
                    <td className="px-5 py-4">
                      <div className="text-sm text-zinc-200">{c.company_name}</div>
                      {c.company_status === 'pending' && (
                        <div className="text-[10px] text-amber-500 uppercase tracking-wider mt-0.5">Pending approval</div>
                      )}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <span className={`text-sm font-mono ${empty ? 'text-red-400' : low ? 'text-amber-400' : 'text-zinc-100'}`}>
                        {c.credits_remaining.toLocaleString()}
                      </span>
                      {(empty || low) && (
                        <div className="text-[10px] text-zinc-600 mt-0.5 font-mono">{empty ? 'out of credits' : 'running low'}</div>
                      )}
                    </td>
                    <td className="px-5 py-4 text-right text-sm font-mono text-zinc-500">{c.total_credits_purchased.toLocaleString()}</td>
                    <td className="px-5 py-4 text-right text-sm font-mono text-zinc-500">{c.total_credits_granted.toLocaleString()}</td>
                    <td className="px-5 py-4 text-right text-[11px] text-zinc-600 font-mono">{c.updated_at ? formatDate(c.updated_at) : '—'}</td>
                    <td className="px-5 py-4 text-right">
                      <button
                        onClick={() => openGrant(c)}
                        className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-zinc-400 hover:text-white border border-white/10 hover:border-white/30 transition-all"
                      >
                        Grant
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {grantTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
          onClick={e => { if (e.target === e.currentTarget) setGrantTarget(null); }}
        >
          <div className="bg-zinc-950 border border-white/10 w-full max-w-sm mx-4">
            <div className="px-6 py-5 border-b border-white/10">
              <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Grant Credits</div>
              <div className="text-base text-white mt-1">{grantTarget.company_name}</div>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="flex items-center justify-between border border-white/10 px-4 py-3">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">Current balance</span>
                <span className="text-sm font-mono text-zinc-200">{grantTarget.credits_remaining.toLocaleString()}</span>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">
                  Credits <span className="text-zinc-600 normal-case font-normal">(negative to deduct)</span>
                </label>
                <input
                  type="number"
                  value={grantAmount}
                  onChange={e => setGrantAmount(e.target.value)}
                  placeholder="500"
                  autoFocus
                  className="w-full bg-zinc-900 border border-white/10 text-zinc-100 text-sm px-3.5 py-2.5 focus:outline-none focus:border-white/30 placeholder:text-zinc-700 transition-colors"
                />
                {amountIsValid && (
                  <p className="mt-1.5 text-[11px] text-zinc-500 font-mono">
                    New balance: <span className="text-zinc-300">{Math.max(0, grantTarget.credits_remaining + parsedAmount).toLocaleString()}</span>
                  </p>
                )}
              </div>
              <div>
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">
                  Note <span className="text-zinc-600 normal-case font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  value={grantNote}
                  onChange={e => setGrantNote(e.target.value)}
                  placeholder="e.g. Courtesy credits for onboarding"
                  className="w-full bg-zinc-900 border border-white/10 text-zinc-100 text-sm px-3.5 py-2.5 focus:outline-none focus:border-white/30 placeholder:text-zinc-700 transition-colors"
                />
              </div>
              {grantError && <p className="text-xs text-red-400">{grantError}</p>}
            </div>
            <div className="px-6 py-4 border-t border-white/10 flex items-center justify-end gap-3">
              <button
                onClick={() => setGrantTarget(null)}
                className="px-4 py-2 text-xs uppercase tracking-wider text-zinc-500 hover:text-zinc-200 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void submitGrant()}
                disabled={granting || !amountIsValid}
                className="px-5 py-2 text-xs uppercase tracking-wider font-bold bg-white text-zinc-950 hover:bg-zinc-100 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                {granting
                  ? 'Applying…'
                  : amountIsValid
                    ? `Apply ${parsedAmount > 0 ? '+' : ''}${parsedAmount.toLocaleString()}`
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
    <div className="max-w-4xl mx-auto space-y-12">

      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Billing & Credits</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Credits are shared across all admins in your organization</p>
        </div>
      </div>

      {notice && (
        <div className="border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-xs text-emerald-400 flex items-center justify-between">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="text-zinc-600 hover:text-zinc-300 ml-4">✕</button>
        </div>
      )}
      {error && (
        <div className="border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-400">{error}</div>
      )}

      {/* Balance + subscription */}
      <div className="grid grid-cols-2 gap-px bg-white/10 border border-white/10">
        <div className="bg-zinc-950 p-8">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">Credits Remaining</div>
          <div className={`text-6xl font-light font-mono ${credits <= 0 ? 'text-red-400' : low ? 'text-amber-400' : 'text-white'}`}>
            {credits.toLocaleString()}
          </div>
          <div className="mt-6 pt-6 border-t border-white/10 grid grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] text-zinc-600 uppercase tracking-widest mb-1">Purchased</div>
              <div className="text-sm font-mono text-zinc-300">{(balance?.total_credits_purchased ?? 0).toLocaleString()}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-600 uppercase tracking-widest mb-1">Granted</div>
              <div className="text-sm font-mono text-zinc-300">{(balance?.total_credits_granted ?? 0).toLocaleString()}</div>
            </div>
          </div>
          {credits <= 0 && <div className="mt-4 text-xs text-red-400">Out of credits — purchase a pack below to continue.</div>}
          {low && <div className="mt-4 text-xs text-amber-400">Running low — fewer than 10 credits remaining.</div>}
        </div>

        {activeSub ? (
          <div className="bg-zinc-950 p-8">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-1.5 h-1.5 bg-emerald-400 animate-pulse" />
              <div className="text-[10px] text-emerald-400 uppercase tracking-widest font-bold">Auto-Renew Active</div>
            </div>
            <div className="text-4xl font-light font-mono text-white">{activeSub.credits_per_cycle?.toLocaleString()}</div>
            <div className="text-[10px] text-zinc-500 mt-1 font-mono uppercase tracking-wider">credits / month</div>
            <div className="mt-6 pt-6 border-t border-white/10 space-y-2 text-[11px] text-zinc-500 font-mono">
              {activeSub.amount_cents && <div>{formatCents(activeSub.amount_cents)} billed monthly</div>}
              {activeSub.current_period_end && <div>Renews {formatDate(activeSub.current_period_end)}</div>}
            </div>
            {activeSub.canceled_at ? (
              <div className="mt-4 text-[11px] text-amber-400">Cancels at period end</div>
            ) : (
              <button
                onClick={() => void handleCancelSub()}
                disabled={cancelingSub}
                className="mt-4 text-[11px] text-zinc-600 hover:text-red-400 uppercase tracking-wider transition-colors disabled:opacity-50"
              >
                {cancelingSub ? 'Canceling…' : 'Cancel subscription'}
              </button>
            )}
          </div>
        ) : (
          <div className="bg-zinc-950 p-8 flex flex-col items-center justify-center text-center">
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-1">No active subscription</div>
            <div className="text-[10px] text-zinc-600 font-mono">Enable auto-renew on any pack below to subscribe.</div>
          </div>
        )}
      </div>

      {/* Credit packs */}
      <div>
        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-1">Top Up Credits</div>
        <div className="text-[10px] text-zinc-600 font-mono mb-6">All credits go into a shared pool. A $2.50 processing fee applies.</div>
        <div className="grid grid-cols-2 gap-px bg-white/10 border border-white/10">
          {packs.map(pack => {
            const autoRenew  = autoRenewFlags[pack.pack_id] ?? false;
            const isBuying   = buyingPackId === pack.pack_id;
            const isBlocked  = Boolean(buyingPackId) && !isBuying;
            const hasThisSub = activeSub?.pack_id === pack.pack_id && !activeSub.canceled_at;

            return (
              <div key={pack.pack_id} className="bg-zinc-950 p-8 flex flex-col gap-6">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-2">{pack.label}</div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-5xl font-light font-mono text-white">{pack.credits.toLocaleString()}</span>
                      <span className="text-[10px] text-zinc-500 uppercase tracking-wider">credits</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-light font-mono text-white">{formatCents(pack.amount_cents)}</div>
                    <div className="text-[10px] text-zinc-600 mt-1 font-mono">incl. {formatCents(pack.fee_cents)} fee</div>
                  </div>
                </div>

                <div className="flex items-center justify-between gap-4 border border-white/10 px-4 py-3">
                  <div>
                    <div className="text-[10px] text-zinc-400 uppercase tracking-wider font-bold">Auto-renew monthly</div>
                    <div className="text-[10px] text-zinc-600 mt-0.5 font-mono">
                      {autoRenew ? `${formatCents(pack.amount_cents)}/mo · renews automatically` : 'One-time purchase'}
                    </div>
                  </div>
                  <button
                    onClick={() => setAutoRenewFlags(p => ({ ...p, [pack.pack_id]: !p[pack.pack_id] }))}
                    role="switch"
                    aria-checked={autoRenew}
                    className={`relative w-10 h-[22px] transition-colors flex-shrink-0 focus:outline-none ${autoRenew ? 'bg-emerald-500' : 'bg-zinc-700'}`}
                  >
                    <span className={`absolute top-[3px] left-[3px] w-4 h-4 bg-white shadow-sm transition-transform ${autoRenew ? 'translate-x-[18px]' : 'translate-x-0'}`} />
                  </button>
                </div>

                {hasThisSub && !autoRenew ? (
                  <div className="flex items-center justify-center gap-1.5 py-2 text-[11px] text-emerald-400 uppercase tracking-wider">
                    <span>✓</span> <span>Auto-renewing</span>
                  </div>
                ) : (
                  <button
                    onClick={() => void handleBuy(pack.pack_id)}
                    disabled={isBuying || isBlocked}
                    className="w-full py-3 bg-white text-zinc-950 text-xs font-bold uppercase tracking-widest hover:bg-zinc-100 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
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
      </div>

      {/* Transaction history */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Transaction History</div>
          {transactions && transactions.total > PAGE_SIZE && (
            <div className="flex items-center gap-3 text-[11px] text-zinc-500">
              <button
                onClick={() => void loadData(Math.max(0, offset - PAGE_SIZE))}
                disabled={loading || offset <= 0}
                className="px-3 py-1 border border-white/10 hover:border-white/20 disabled:opacity-40 uppercase tracking-wider transition-colors"
              >← Prev</button>
              <span className="font-mono">{currentPage} / {totalPages}</span>
              <button
                onClick={() => void loadData(offset + PAGE_SIZE)}
                disabled={loading || !transactions || offset + PAGE_SIZE >= transactions.total}
                className="px-3 py-1 border border-white/10 hover:border-white/20 disabled:opacity-40 uppercase tracking-wider transition-colors"
              >Next →</button>
            </div>
          )}
        </div>

        <div className="border border-white/10">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-white/10">
                {['Type', 'Amount', 'Balance After', 'Description', 'Date'].map((h, i) => (
                  <th key={h} className={`px-5 py-3 text-[10px] uppercase tracking-widest text-zinc-600 font-bold ${i === 0 ? 'text-left' : i >= 1 && i <= 2 ? 'text-right' : 'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {(transactions?.items ?? []).map(tx => (
                <tr key={tx.id} className="bg-zinc-950 hover:bg-zinc-900/30 transition-colors">
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest border ${txBadgeClass(tx.transaction_type)}`}>
                      {txLabel(tx.transaction_type)}
                    </span>
                  </td>
                  <td className={`px-5 py-3.5 text-right text-sm font-mono ${tx.credits_delta >= 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {tx.credits_delta >= 0 ? '+' : ''}{tx.credits_delta.toLocaleString()}
                  </td>
                  <td className="px-5 py-3.5 text-right text-sm font-mono text-zinc-500">{tx.credits_after.toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-sm text-zinc-500 max-w-xs truncate">{tx.description || '—'}</td>
                  <td className="px-5 py-3.5 text-[11px] text-zinc-600 whitespace-nowrap font-mono">{formatTs(tx.created_at)}</td>
                </tr>
              ))}
              {!loading && (transactions?.items.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-12 text-center text-xs text-zinc-600">No transactions yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
