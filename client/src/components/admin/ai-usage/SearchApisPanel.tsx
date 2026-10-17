import { Search } from 'lucide-react'
import type { AiUsageProviderRollup, ApiQuota } from '../../../types/aiUsage'
import { fmtCost, fmtCount, quotaView, relTime } from './format'

// The per-API view of the paid search APIs' ledger rows, plus what each has
// left this period.

const TONE: Record<ReturnType<typeof quotaView>['tone'], string> = {
  ok: 'text-zinc-100',
  low: 'text-amber-300',
  out: 'text-red-300',
  muted: 'text-zinc-500',
  error: 'text-red-300',
}

const BAR: Record<ReturnType<typeof quotaView>['tone'], string> = {
  ok: 'bg-emerald-500/60',
  low: 'bg-amber-500/70',
  out: 'bg-red-500/70',
  muted: 'bg-zinc-700',
  error: 'bg-zinc-700',
}

function QuotaCard({
  quota,
  usage,
  active,
  onSelect,
}: {
  quota: ApiQuota
  usage: AiUsageProviderRollup | undefined
  active: boolean
  onSelect: () => void
}) {
  const view = quotaView(quota)
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`text-left p-3 rounded-lg border transition-colors ${
        active ? 'bg-zinc-800 border-zinc-600' : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] uppercase tracking-wider text-zinc-500">{quota.label}</p>
        {quota.plan && (
          <span className="text-[10px] text-zinc-500 truncate">
            {quota.plan}
            {quota.monthly_price != null && ` · $${quota.monthly_price}/mo`}
          </span>
        )}
      </div>
      <p className={`text-2xl font-semibold mt-0.5 ${TONE[view.tone]}`}>{view.headline}</p>
      {view.leftShare != null && (
        <div className="mt-1.5 h-1 rounded-full bg-zinc-800 overflow-hidden">
          <div className={`h-full ${BAR[view.tone]}`} style={{ width: `${Math.round(view.leftShare * 100)}%` }} />
        </div>
      )}
      {view.detail && <p className="text-[11px] text-zinc-500 mt-1">{view.detail}</p>}
      {quota.extra_credits != null && quota.extra_credits > 0 && (
        <p className="text-[11px] text-zinc-500">includes {fmtCount(quota.extra_credits)} extra credits</p>
      )}
      <p className="text-[11px] text-zinc-400 mt-1.5">
        This window: {fmtCount(usage?.calls ?? 0)} requests
        {usage && usage.cost_usd != null && ` · ${fmtCost(usage.cost_usd)}`}
        {usage && usage.errors > 0 && <span className="text-amber-400"> · {usage.errors} failed</span>}
      </p>
      {quota.note && <p className="text-[10px] text-zinc-600 mt-1">{quota.note}</p>}
      {quota.observed_at && <p className="text-[10px] text-zinc-600">seen {relTime(quota.observed_at)}</p>}
    </button>
  )
}

export function SearchApisPanel({
  quotas,
  providers,
  loading,
  error,
  selectedProvider,
  onSelectProvider,
}: {
  quotas: ApiQuota[]
  providers: AiUsageProviderRollup[]
  loading: boolean
  error: string | null
  selectedProvider: string | null
  onSelectProvider: (provider: string) => void
}) {
  const byProvider = new Map(providers.map((p) => [p.provider, p]))
  return (
    <div className="mb-4">
      <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        <Search size={11} /> Search APIs
        {loading && <span className="normal-case tracking-normal font-normal text-zinc-600">checking…</span>}
      </p>
      {error && <p className="mb-2 text-xs text-red-400">Couldn't check search API quotas: {error}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {quotas.map((q) => (
          <QuotaCard
            key={q.provider}
            quota={q}
            usage={byProvider.get(q.provider)}
            active={selectedProvider === q.provider}
            onSelect={() => onSelectProvider(q.provider)}
          />
        ))}
      </div>
      <p className="mt-1.5 text-[11px] text-zinc-500">
        Click a card to see its requests in the call log. SearchAPI and SerpApi are monthly plans, so their
        requests carry no per-request cost.
      </p>
    </div>
  )
}
