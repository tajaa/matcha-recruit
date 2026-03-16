import { useState, useEffect, useRef } from 'react'
import { api } from '../../api/client'
import { Badge, Button, type BadgeVariant } from '../ui'
import type { SimilarCasesAnalysis, SimilarCaseMatch } from '../../types/er'
import { categoryLabel, outcomeLabel, statusLabel } from '../../types/er'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

type Props = { caseId: string }

export function ERSimilarCasesPanel({ caseId }: Props) {
  const [data, setData] = useState<SimilarCasesAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [phase, setPhase] = useState('')
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  function streamSimilarCases(refresh = false) {
    setLoading(true)
    setError('')
    setPhase('')
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    const token = localStorage.getItem('matcha_access_token')
    const url = `${BASE}/er/cases/${caseId}/analysis/similar-cases${refresh ? '?refresh=true' : ''}`

    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
        const reader = res.body?.getReader()
        if (!reader) throw new Error('No response body')
        const decoder = new TextDecoder()
        let buf = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })

          const lines = buf.split('\n')
          buf = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (raw === '[DONE]') { setLoading(false); return }
            try {
              const msg = JSON.parse(raw)
              if (msg.type === 'phase') setPhase(msg.message ?? '')
              if (msg.type === 'complete') { setData(msg.data); setLoading(false); return }
            } catch { /* skip malformed */ }
          }
        }
        setLoading(false)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setError(e instanceof Error ? e.message : 'Failed to find similar cases')
          setLoading(false)
        }
      })
  }

  // Fetch cached on mount
  useEffect(() => {
    let cancelled = false
    api.get<SimilarCasesAnalysis>(`/er/cases/${caseId}/analysis/similar-cases`)
      .then((res) => { if (!cancelled && res.generated_at) setData(res) })
      .catch(() => {})
    return () => { cancelled = true; abortRef.current?.abort() }
  }, [caseId])

  if (loading) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500">{phase || 'Finding similar cases...'}</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500 mb-4">Find similar past cases to identify patterns and precedents.</p>
        <Button onClick={() => streamSimilarCases()}>Find Similar Cases</Button>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>
    )
  }

  const total = Object.values(data.outcome_distribution).reduce((a, b) => a + b, 0) || 1

  return (
    <div className="space-y-4">
      {/* Cache indicator */}
      {data.from_cache && (
        <p className="text-[11px] text-zinc-600">
          From cache &middot; {new Date(data.generated_at).toLocaleDateString()}
        </p>
      )}

      {/* Pattern summary */}
      {data.pattern_summary && (
        <div className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
          <p className="text-sm text-zinc-300">{data.pattern_summary}</p>
        </div>
      )}

      {/* Outcome distribution */}
      {Object.keys(data.outcome_distribution).length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 space-y-2">
          <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Outcome Distribution</p>
          {Object.entries(data.outcome_distribution).map(([key, count]) => (
            <div key={key} className="flex items-center gap-2">
              <span className="text-xs text-zinc-400 w-32 shrink-0">{outcomeLabel[key] ?? key}</span>
              <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-emerald-500/60"
                  style={{ width: `${(count / total) * 100}%` }}
                />
              </div>
              <span className="text-[11px] text-zinc-500 w-6 text-right">{count}</span>
            </div>
          ))}
        </div>
      )}

      {/* Case match cards */}
      {data.matches.length === 0 && (
        <p className="text-sm text-zinc-400 text-center py-4">No similar cases found.</p>
      )}

      {data.matches.map((m: SimilarCaseMatch) => (
        <div key={m.case_id} className="border border-zinc-800 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-zinc-500">{m.case_number}</span>
              <h4 className="text-sm font-medium text-zinc-100">{m.title}</h4>
            </div>
            <span className="text-sm font-mono text-emerald-400">{Math.round(m.similarity_score * 100)}%</span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {m.category && <Badge variant="neutral">{categoryLabel[m.category] ?? m.category}</Badge>}
            {m.outcome && <Badge variant="neutral">{outcomeLabel[m.outcome] ?? m.outcome}</Badge>}
            <Badge variant="neutral">{statusLabel[m.status] ?? m.status}</Badge>
            {m.resolution_days != null && (
              <span className="text-[11px] text-zinc-500">{m.resolution_days}d to resolve</span>
            )}
          </div>

          {m.common_factors.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {m.common_factors.map((f, i) => (
                <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">{f}</span>
              ))}
            </div>
          )}

          {m.relevance_note && (
            <p className="text-xs text-zinc-500 italic">{m.relevance_note}</p>
          )}
        </div>
      ))}

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={() => streamSimilarCases(true)}>Refresh</Button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
