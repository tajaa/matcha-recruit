import { useState, useRef } from 'react'
import { askPayerPolicyQuestion, type PayerPolicySource } from '../../api/compliance'

const PAYER_LABELS: Record<string, string> = {
  medicare: 'Medicare',
  medi_cal: 'Medi-Cal',
  medicaid_other: 'Medicaid',
  commercial: 'Commercial',
  tricare: 'TRICARE',
}

function coverageBadge(status: string) {
  switch (status) {
    case 'covered':
      return { label: 'Covered', cls: 'bg-emerald-900/40 text-emerald-400 border-emerald-700/40' }
    case 'not_covered':
      return { label: 'Not Covered', cls: 'bg-red-900/40 text-red-400 border-red-700/40' }
    default:
      return { label: 'Conditional', cls: 'bg-amber-900/40 text-amber-400 border-amber-700/40' }
  }
}

type Props = {
  locationId?: string | null
  payerContracts?: string[]
}

export function PayerPolicyNavigator({ locationId, payerContracts = [] }: Props) {
  const [query, setQuery] = useState('')
  const [selectedPayer, setSelectedPayer] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer] = useState<string | null>(null)
  const [sources, setSources] = useState<PayerPolicySource[]>([])
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleAsk() {
    const q = query.trim()
    if (!q || loading) return

    setLoading(true)
    setAnswer(null)
    setSources([])
    setError(null)

    try {
      const result = await askPayerPolicyQuestion(
        q,
        locationId ?? undefined,
        selectedPayer || undefined,
      )
      setAnswer(result.answer)
      setSources(result.sources)
    } catch (e: any) {
      setError(e.message || 'Failed to get answer')
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
    setQuery('')
    setAnswer(null)
    setSources([])
    setError(null)
    inputRef.current?.focus()
  }

  const primarySource = sources[0]
  const badge = primarySource ? coverageBadge(primarySource.coverage_status) : null

  return (
    <div>
      {/* Search bar */}
      <div className="flex gap-2">
        {payerContracts.length > 0 && (
          <select
            value={selectedPayer}
            onChange={(e) => setSelectedPayer(e.target.value)}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-700 min-w-[140px]"
          >
            <option value="">All Payers</option>
            {payerContracts.map((p) => (
              <option key={p} value={PAYER_LABELS[p] || p}>
                {PAYER_LABELS[p] || p}
              </option>
            ))}
          </select>
        )}
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
            placeholder="What does Medicare require to approve a brain MRI?"
            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-700 focus:ring-1 focus:ring-indigo-700"
            disabled={loading}
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
      </div>

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}

      {/* Answer panel */}
      {answer && (
        <div className="mt-3 bg-zinc-900/50 border border-zinc-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-indigo-400 uppercase tracking-wide font-medium">Policy Answer</span>
              {badge && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge.cls}`}>
                  {badge.label}
                </span>
              )}
              {primarySource && primarySource.coverage_status !== 'not_covered' && (
                <span className="text-[10px] px-1.5 py-0.5 rounded border bg-zinc-800 text-zinc-400 border-zinc-700">
                  Prior Auth: {sources.some(s => s.coverage_status === 'covered') ? 'Check policy' : 'See details'}
                </span>
              )}
            </div>
            <button onClick={handleClear} className="text-[10px] text-zinc-500 hover:text-zinc-300">
              Clear
            </button>
          </div>

          <p className="text-sm text-zinc-200 leading-6 whitespace-pre-wrap">{answer}</p>

          {/* Sources */}
          {sources.length > 0 && (
            <div className="mt-3 pt-3 border-t border-zinc-800">
              <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Sources ({sources.length})</span>
              <div className="mt-1.5 space-y-1">
                {sources.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="text-indigo-400 font-medium">{s.payer_name}</span>
                    {s.policy_number && <span className="text-zinc-500">{s.policy_number}</span>}
                    {s.policy_title && <span className="text-zinc-400 truncate max-w-[300px]">{s.policy_title}</span>}
                    {s.source_url && (
                      <a
                        href={s.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-500 hover:text-indigo-400 shrink-0"
                      >
                        view policy
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
