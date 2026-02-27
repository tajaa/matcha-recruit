import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { matchaWork } from '../api/client';
import type {
  MWBillingBalanceResponse,
  MWBillingTransactionsResponse,
  MWCreditPack,
  MWCreditTransaction,
  MWSubscription,
} from '../types/matcha-work';

const PAGE_SIZE = 25;
const FEE_LABEL = '$2.50 processing fee';

function formatPrice(amountCents: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amountCents / 100);
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function transactionLabel(value: MWCreditTransaction['transaction_type']): string {
  switch (value) {
    case 'purchase': return 'Purchase';
    case 'grant': return 'Admin Grant';
    case 'deduction': return 'AI Usage';
    case 'refund': return 'Refund';
    default: return 'Adjustment';
  }
}

export default function MatchaWorkBilling() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [balance, setBalance] = useState<MWBillingBalanceResponse | null>(null);
  const [packs, setPacks] = useState<MWCreditPack[]>([]);
  const [subscription, setSubscription] = useState<MWSubscription | null>(null);
  const [transactions, setTransactions] = useState<MWBillingTransactionsResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Per-pack: track whether auto-renew toggle is on, and which is loading
  const [autoRenewFlags, setAutoRenewFlags] = useState<Record<string, boolean>>({});
  const [buyingPackId, setBuyingPackId] = useState<string | null>(null);
  const [cancelingSubscription, setCancelingSubscription] = useState(false);

  const totalPages = useMemo(() => {
    if (!transactions) return 1;
    return Math.max(1, Math.ceil(transactions.total / transactions.limit));
  }, [transactions]);

  const currentPage = useMemo(() => {
    if (!transactions) return 1;
    return Math.floor(transactions.offset / transactions.limit) + 1;
  }, [transactions]);

  const loadBillingData = useCallback(async (nextOffset: number) => {
    try {
      setLoading(true);
      setError(null);
      const [balanceData, packsData, subData, txData] = await Promise.all([
        matchaWork.getBillingBalance(),
        matchaWork.getCreditPacks(),
        matchaWork.getSubscription(),
        matchaWork.getBillingTransactions({ limit: PAGE_SIZE, offset: nextOffset }),
      ]);
      setBalance(balanceData);
      setPacks(packsData);
      setSubscription(subData);
      setTransactions(txData);
      setOffset(nextOffset);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load billing data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadBillingData(0); }, [loadBillingData]);

  useEffect(() => {
    if (searchParams.get('success') === '1') {
      setNotice('Payment completed. Credits are being applied now.');
      setSearchParams({}, { replace: true });
      loadBillingData(0);
      return;
    }
    if (searchParams.get('canceled') === '1') {
      setNotice('Checkout canceled. No credits were added.');
      setSearchParams({}, { replace: true });
    }
  }, [loadBillingData, searchParams, setSearchParams]);

  const handleBuyPack = async (packId: string) => {
    const autoRenew = autoRenewFlags[packId] ?? false;
    try {
      setBuyingPackId(packId);
      setError(null);
      const session = await matchaWork.createCheckout(packId, autoRenew);
      if (!session.checkout_url) throw new Error('Checkout URL missing');
      window.location.href = session.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start checkout');
      setBuyingPackId(null);
    }
  };

  const handleCancelSubscription = async () => {
    if (!confirm('Cancel your subscription? You will not be billed again and your current credits remain until used.')) return;
    try {
      setCancelingSubscription(true);
      setError(null);
      await matchaWork.cancelSubscription();
      setNotice('Subscription canceled. It will not renew at the end of the current billing period.');
      loadBillingData(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel subscription');
    } finally {
      setCancelingSubscription(false);
    }
  };

  const creditsRemaining = balance?.credits_remaining ?? 0;
  const lowCredits = creditsRemaining > 0 && creditsRemaining < 10;
  const activeSub = subscription?.active ? subscription : null;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-7">
      {/* Nav */}
      <div>
        <div className="inline-flex items-center bg-zinc-800 rounded-lg p-0.5 mb-3">
          <button onClick={() => navigate('/app/matcha/work')} className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors">Chat</button>
          <button onClick={() => navigate('/app/matcha/work/chats')} className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors">Chats</button>
          <button onClick={() => navigate('/app/matcha/work/elements')} className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors">Matcha Elements</button>
          <button className="px-3 py-1 text-xs rounded bg-zinc-700 text-zinc-100">Billing</button>
        </div>
        <h1 className="text-xl font-semibold text-zinc-100">Matcha Work Billing</h1>
        <p className="text-sm text-zinc-400 mt-0.5">
          Credits are shared across all admins in your organization.
        </p>
      </div>

      {notice && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">{notice}</div>
      )}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
      )}

      {/* Balance card */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
          <div className="flex-1">
            <p className="text-xs uppercase tracking-wider text-zinc-500">Credits Remaining</p>
            <p className="text-4xl font-semibold text-zinc-100 mt-1">{creditsRemaining.toLocaleString()}</p>
            <p className="text-xs text-zinc-500 mt-2">
              Purchased: {(balance?.total_credits_purchased ?? 0).toLocaleString()} &nbsp;·&nbsp;
              Granted: {(balance?.total_credits_granted ?? 0).toLocaleString()}
            </p>
            {creditsRemaining <= 0 && (
              <p className="text-sm text-red-300 mt-2">Out of credits — purchase a pack to continue using Matcha Work.</p>
            )}
            {lowCredits && (
              <p className="text-sm text-amber-300 mt-2">Low credits — fewer than 10 remaining.</p>
            )}
          </div>

          {/* Active subscription badge */}
          {activeSub && (
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 min-w-[220px]">
              <div className="flex items-center gap-1.5 mb-1">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Auto-Renew Active</span>
              </div>
              <p className="text-sm text-zinc-300">
                {activeSub.credits_per_cycle?.toLocaleString()} credits / month
              </p>
              <p className="text-xs text-zinc-500 mt-0.5">
                {activeSub.amount_cents ? formatPrice(activeSub.amount_cents) : ''} billed monthly
              </p>
              {activeSub.current_period_end && (
                <p className="text-xs text-zinc-500 mt-0.5">
                  Next renewal: {formatDate(activeSub.current_period_end)}
                </p>
              )}
              {activeSub.canceled_at ? (
                <p className="text-xs text-amber-400 mt-2">Cancels at period end</p>
              ) : (
                <button
                  onClick={() => void handleCancelSubscription()}
                  disabled={cancelingSubscription}
                  className="mt-2 text-xs text-zinc-500 hover:text-red-400 transition-colors disabled:opacity-50"
                >
                  {cancelingSubscription ? 'Canceling…' : 'Cancel subscription'}
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Credit packs */}
      <section>
        <div className="mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Top Up Credits</h2>
          <p className="text-xs text-zinc-500 mt-0.5">All credits go into a shared pool for your entire team. A {FEE_LABEL} applies to all purchases.</p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {packs.map((pack) => {
            const autoRenew = autoRenewFlags[pack.pack_id] ?? false;
            const isBuying = buyingPackId === pack.pack_id;
            const isBlocked = Boolean(buyingPackId) && !isBuying;
            // Disable one-time buy if already subscribed to this pack
            const hasThisSub = activeSub?.pack_id === pack.pack_id && !activeSub.canceled_at;

            return (
              <div
                key={pack.pack_id}
                className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 flex flex-col gap-4"
              >
                {/* Pack header */}
                <div>
                  <p className="text-xs uppercase tracking-wider text-zinc-500 mb-0.5">{pack.label}</p>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-3xl font-semibold text-zinc-100">{pack.credits.toLocaleString()}</span>
                    <span className="text-sm text-zinc-400">credits</span>
                  </div>
                  <div className="mt-2 space-y-0.5">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">Base price</span>
                      <span className="text-zinc-300">{formatPrice(pack.base_cents)}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-500">Processing fee</span>
                      <span className="text-zinc-500">+{formatPrice(pack.fee_cents)}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm font-semibold border-t border-white/5 pt-1 mt-1">
                      <span className="text-zinc-200">Total charged</span>
                      <span className="text-zinc-100">{formatPrice(pack.amount_cents)}</span>
                    </div>
                  </div>
                </div>

                {/* Auto-renew toggle */}
                <div className="flex items-center justify-between gap-3 rounded-lg bg-zinc-800/60 px-3 py-2">
                  <div>
                    <p className="text-xs font-medium text-zinc-300">Auto-renew monthly</p>
                    <p className="text-[11px] text-zinc-500 mt-0.5">
                      {autoRenew ? `${formatPrice(pack.amount_cents)}/mo · ${pack.credits} credits added each cycle` : 'One-time purchase'}
                    </p>
                  </div>
                  <button
                    onClick={() => setAutoRenewFlags(prev => ({ ...prev, [pack.pack_id]: !prev[pack.pack_id] }))}
                    className={`relative w-10 h-5 rounded-full transition-colors flex-shrink-0 ${
                      autoRenew ? 'bg-emerald-500' : 'bg-zinc-600'
                    }`}
                    role="switch"
                    aria-checked={autoRenew}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${autoRenew ? 'translate-x-5' : 'translate-x-0'}`} />
                  </button>
                </div>

                {/* CTA */}
                {hasThisSub && !autoRenew ? (
                  <div className="text-xs text-emerald-400 text-center py-1">
                    ✓ Auto-renewing — manage above
                  </div>
                ) : (
                  <button
                    onClick={() => void handleBuyPack(pack.pack_id)}
                    disabled={isBuying || isBlocked}
                    className="w-full py-2.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-sm text-zinc-100 font-medium transition-colors"
                  >
                    {isBuying
                      ? 'Redirecting to checkout…'
                      : autoRenew
                      ? `Subscribe — ${formatPrice(pack.amount_cents)}/mo`
                      : `Buy once — ${formatPrice(pack.amount_cents)}`}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Transaction history */}
      <section>
        <div className="flex items-center justify-between gap-3 mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Transaction History</h2>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <button
              onClick={() => loadBillingData(Math.max(0, offset - PAGE_SIZE))}
              disabled={loading || offset <= 0}
              className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40"
            >Prev</button>
            <span>Page {currentPage} / {totalPages}</span>
            <button
              onClick={() => loadBillingData(offset + PAGE_SIZE)}
              disabled={loading || !transactions || offset + PAGE_SIZE >= transactions.total}
              className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40"
            >Next</button>
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-900/40">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-900/80 text-zinc-400 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Credits</th>
                <th className="text-left px-4 py-3">Balance After</th>
                <th className="text-left px-4 py-3">Description</th>
                <th className="text-left px-4 py-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {(transactions?.items || []).map((tx) => (
                <tr key={tx.id} className="border-t border-zinc-800">
                  <td className="px-4 py-3 text-zinc-200">{transactionLabel(tx.transaction_type)}</td>
                  <td className={`px-4 py-3 ${tx.credits_delta >= 0 ? 'text-emerald-300' : 'text-amber-300'}`}>
                    {tx.credits_delta >= 0 ? '+' : ''}{tx.credits_delta}
                  </td>
                  <td className="px-4 py-3 text-zinc-300">{tx.credits_after}</td>
                  <td className="px-4 py-3 text-zinc-400">{tx.description || '—'}</td>
                  <td className="px-4 py-3 text-zinc-500">{formatTimestamp(tx.created_at)}</td>
                </tr>
              ))}
              {(transactions?.items.length ?? 0) === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-zinc-500">No transactions yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
