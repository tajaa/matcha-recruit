import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import { Badge, Button, type BadgeVariant } from '../ui'
import type { DiscrepancyAnalysisResponse, DiscrepancyItem, CredibilityNote } from '../../types/er'

const severityVariant: Record<string, BadgeVariant> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

type Props = { caseId: string }

export function ERDiscrepanciesPanel({ caseId }: Props) {
  const [data, setData] = useState<DiscrepancyAnalysisResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function generate() {
    setLoading(true)
    setError('')
    try {
      const postRes = await api.post<{ status: string }>(`/er/cases/${caseId}/analysis/discrepancies`)

      if (postRes.status === 'queued') {
        for (let i = 0; i < 30; i++) {
          await new Promise((r) => setTimeout(r, 2000))
          const res = await api.get<DiscrepancyAnalysisResponse>(`/er/cases/${caseId}/analysis/discrepancies`)
          if (res.generated_at) {
            setData(res)
            return
          }
        }
        setError('Analysis is taking longer than expected. Please refresh the page.')
      } else {
        const res = await api.get<DiscrepancyAnalysisResponse>(`/er/cases/${caseId}/analysis/discrepancies`)
        setData(res)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to detect discrepancies')
    } finally {
      setLoading(false)
    }
  }

  // Fetch existing on mount
  useEffect(() => {
    let cancelled = false
    api.get<DiscrepancyAnalysisResponse>(`/er/cases/${caseId}/analysis/discrepancies`)
      .then((res) => { if (!cancelled && res.generated_at) setData(res) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [caseId])

  if (loading) {
    return <p className="text-sm text-zinc-500 py-8 text-center">Detecting discrepancies...</p>
  }

  if (!data || !data.generated_at) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500 mb-2">
          Detect contradictions and inconsistencies across witness statements and documents.
        </p>
        <p className="text-xs text-zinc-600 mb-4">Requires at least 2 completed documents.</p>
        <Button onClick={generate}>Detect Discrepancies</Button>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>
    )
  }

  const discrepancies = data.analysis?.discrepancies ?? []
  const credibility_notes = data.analysis?.credibility_notes ?? []
  const summary = data.analysis?.summary

  return (
    <div className="space-y-4">
      {/* Summary */}
      {summary && (
        <div className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
          <p className="text-sm text-zinc-300">{summary}</p>
        </div>
      )}

      {/* Discrepancy cards */}
      {discrepancies.length === 0 && (
        <p className="text-sm text-zinc-400 text-center py-4">No discrepancies found.</p>
      )}

      {discrepancies.map((d: DiscrepancyItem, i: number) => (
        <div key={i} className="border border-zinc-800 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-medium text-zinc-100">{d.subject}</h4>
            <Badge variant={severityVariant[d.severity] ?? 'neutral'}>{d.severity}</Badge>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="border-l-2 border-zinc-700 pl-3">
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Statement A</p>
              <p className="text-sm text-zinc-300 leading-relaxed">{d.statement_a}</p>
              <p className="text-[11px] text-zinc-600 mt-1">{d.source_a}</p>
            </div>
            <div className="border-l-2 border-zinc-700 pl-3">
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Statement B</p>
              <p className="text-sm text-zinc-300 leading-relaxed">{d.statement_b}</p>
              <p className="text-[11px] text-zinc-600 mt-1">{d.source_b}</p>
            </div>
          </div>

          {d.notes && <p className="text-xs text-zinc-500 italic">{d.notes}</p>}
        </div>
      ))}

      {/* Credibility notes */}
      {credibility_notes.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 space-y-3">
          <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Credibility Notes</p>
          {credibility_notes.map((cn: CredibilityNote, i: number) => (
            <div key={i} className="space-y-1">
              <p className="text-sm text-zinc-200">{cn.witness}</p>
              <p className="text-xs text-zinc-400">{cn.note}</p>
              <div className="flex flex-wrap gap-1.5">
                {cn.factors.map((f, j) => (
                  <span key={j} className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">{f}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={generate}>Regenerate</Button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
