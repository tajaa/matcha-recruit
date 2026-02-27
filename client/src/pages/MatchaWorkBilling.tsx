import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { matchaWork } from '../api/client';
import type {
  MWBillingBalanceResponse,
  MWBillingTransactionsResponse,
  MWCreditPack,
  MWCreditTransaction,
} from '../types/matcha-work';

const PAGE_SIZE = 25;

function formatPrice(amountCents: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(amountCents / 100);
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function transactionLabel(value: MWCreditTransaction['transaction_type']): string {
  switch (value) {
    case 'purchase':
      return 'Purchase';
    case 'grant':
      return 'Admin Grant';
    case 'deduction':
      return 'AI Usage';
    case 'refund':
      return 'Refund';
    default:
      return 'Adjustment';
  }
}

export default function MatchaWorkBilling() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [balance, setBalance] = useState<MWBillingBalanceResponse | null>(null);
  const [packs, setPacks] = useState<MWCreditPack[]>([]);
  const [transactions, setTransactions] = useState<MWBillingTransactionsResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [buyingPackId, setBuyingPackId] = useState<string | null>(null);

  const totalPages = useMemo(() => {
    if (!transactions) return 1;
    return Math.max(1, Math.ceil(transactions.total / transactions.limit));
  }, [transactions]);

  const currentPage = useMemo(() => {
    if (!transactions) return 1;
    return Math.floor(transactions.offset / transactions.limit) + 1;
  }, [transactions]);

  const loadBillingData = useCallback(
    async (nextOffset: number) => {
      try {
        setLoading(true);
        setError(null);

        const [balanceData, packsData, txData] = await Promise.all([
          matchaWork.getBillingBalance(),
          matchaWork.getCreditPacks(),
          matchaWork.getBillingTransactions({ limit: PAGE_SIZE, offset: nextOffset }),
        ]);

        setBalance(balanceData);
        setPacks(packsData);
        setTransactions(txData);
        setOffset(nextOffset);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load billing data');
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadBillingData(0);
  }, [loadBillingData]);

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
    try {
      setBuyingPackId(packId);
      setError(null);
      const session = await matchaWork.createCheckout(packId);
      if (!session.checkout_url) {
        throw new Error('Checkout URL missing from response');
      }
      window.location.href = session.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start checkout');
      setBuyingPackId(null);
    }
  };

  const creditsRemaining = balance?.credits_remaining ?? 0;
  const lowCredits = creditsRemaining > 0 && creditsRemaining < 10;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="inline-flex items-center bg-zinc-800 rounded-lg p-0.5 mb-2">
            <button
              onClick={() => navigate('/app/matcha/work')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Chat
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/chats')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Chats
            </button>
            <button
              onClick={() => navigate('/app/matcha/work/elements')}
              className="px-3 py-1 text-xs rounded text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Matcha Elements
            </button>
            <button className="px-3 py-1 text-xs rounded bg-zinc-700 text-zinc-100">
              Billing
            </button>
          </div>
          <h1 className="text-xl font-semibold text-zinc-100">Matcha Work Billing</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            Buy credits and track usage across your company.
          </p>
        </div>
      </div>

      {notice && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
          {notice}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-zinc-500">Credits Remaining</p>
            <p className="text-4xl font-semibold text-zinc-100 mt-1">{creditsRemaining.toLocaleString()}</p>
            <p className="text-xs text-zinc-500 mt-2">
              Purchased: {(balance?.total_credits_purchased ?? 0).toLocaleString()} | Granted:{' '}
              {(balance?.total_credits_granted ?? 0).toLocaleString()}
            </p>
          </div>
          <button
            onClick={() => {
              const preferred = packs[0]?.pack_id;
              if (preferred) handleBuyPack(preferred);
            }}
            disabled={loading || packs.length === 0 || Boolean(buyingPackId)}
            className="px-4 py-2.5 rounded-lg bg-matcha-600 hover:bg-matcha-700 disabled:opacity-50 text-white text-sm transition-colors"
          >
            {buyingPackId ? 'Redirecting to checkout...' : 'Buy More Credits'}
          </button>
        </div>
        {creditsRemaining <= 0 && (
          <p className="text-sm text-red-300 mt-3">
            You are out of credits. Purchase a credit pack to continue using Matcha Work.
          </p>
        )}
        {lowCredits && (
          <p className="text-sm text-amber-300 mt-3">
            Low credit warning: fewer than 10 credits remain.
          </p>
        )}
      </div>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mb-3">Credit Packs</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {packs.map((pack) => (
            <div key={pack.pack_id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
              <p className="text-xs text-zinc-500 uppercase tracking-wider">{pack.label}</p>
              <p className="text-2xl text-zinc-100 font-semibold mt-1">{pack.credits.toLocaleString()}</p>
              <p className="text-sm text-zinc-400">credits</p>
              <p className="text-lg text-zinc-200 mt-3">{formatPrice(pack.amount_cents, pack.currency.toUpperCase())}</p>
              <button
                onClick={() => handleBuyPack(pack.pack_id)}
                disabled={Boolean(buyingPackId)}
                className="mt-4 w-full px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-sm text-zinc-100 transition-colors"
              >
                {buyingPackId === pack.pack_id ? 'Opening checkout...' : `Buy ${pack.label}`}
              </button>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between gap-3 mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Transaction History</h2>
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <button
              onClick={() => loadBillingData(Math.max(0, offset - PAGE_SIZE))}
              disabled={loading || offset <= 0}
              className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40"
            >
              Prev
            </button>
            <span>
              Page {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => loadBillingData(offset + PAGE_SIZE)}
              disabled={
                loading ||
                !transactions ||
                offset + PAGE_SIZE >= transactions.total
              }
              className="px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-900/40">
          <table className="min-w-full text-sm">
            <thead className="bg-zinc-900/80 text-zinc-400 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-4 py-3">Type</th>
                <th className="text-left px-4 py-3">Credits</th>
                <th className="text-left px-4 py-3">After</th>
                <th className="text-left px-4 py-3">Description</th>
                <th className="text-left px-4 py-3">Date</th>
              </tr>
            </thead>
            <tbody>
              {(transactions?.items || []).map((tx) => (
                <tr key={tx.id} className="border-t border-zinc-800">
                  <td className="px-4 py-3 text-zinc-200">{transactionLabel(tx.transaction_type)}</td>
                  <td className={`px-4 py-3 ${tx.credits_delta >= 0 ? 'text-emerald-300' : 'text-amber-300'}`}>
                    {tx.credits_delta >= 0 ? '+' : ''}
                    {tx.credits_delta}
                  </td>
                  <td className="px-4 py-3 text-zinc-300">{tx.credits_after}</td>
                  <td className="px-4 py-3 text-zinc-400">{tx.description || '—'}</td>
                  <td className="px-4 py-3 text-zinc-500">{formatTimestamp(tx.created_at)}</td>
                </tr>
              ))}
              {(transactions?.items.length ?? 0) === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-zinc-500">
                    No transactions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
