import { useState } from 'react'
import { api } from '../../api/client'
import { Badge, Button, type BadgeVariant } from '../ui'
import type { TimelineAnalysisResponse, TimelineEvent } from '../../types/er'

const confidenceVariant: Record<string, BadgeVariant> = {
  high: 'success',
  medium: 'warning',
  low: 'danger',
}

type ERTimelinePanelProps = {
  caseId: string
  timeline: TimelineAnalysisResponse | null
  onTimelineChange: (t: TimelineAnalysisResponse | null) => void
}

export function ERTimelinePanel({ caseId, timeline, onTimelineChange }: ERTimelinePanelProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expandedQuotes, setExpandedQuotes] = useState<Set<number>>(new Set())

  async function generate() {
    setLoading(true)
    setError('')
    try {
      await api.post(`/er/cases/${caseId}/analysis/timeline`)
      const res = await api.get<TimelineAnalysisResponse>(
        `/er/cases/${caseId}/analysis/timeline`,
      )
      onTimelineChange(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate timeline')
    } finally {
      setLoading(false)
    }
  }

  async function fetchExisting() {
    setLoading(true)
    setError('')
    try {
      const res = await api.get<TimelineAnalysisResponse>(
        `/er/cases/${caseId}/analysis/timeline`,
      )
      if (res.generated_at) {
        onTimelineChange(res)
      }
    } catch {
      // No existing timeline
    } finally {
      setLoading(false)
    }
  }

  // On first render with no timeline, try fetching existing
  if (!timeline && !loading && !error) {
    fetchExisting()
    return <p className="text-sm text-zinc-500 py-8 text-center">Checking for timeline...</p>
  }

  if (loading) {
    return <p className="text-sm text-zinc-500 py-8 text-center">Analyzing timeline...</p>
  }

  if (!timeline || !timeline.generated_at) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500 mb-4">
          Generate a chronological timeline from uploaded documents.
        </p>
        <Button onClick={generate}>Generate Timeline</Button>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>
    )
  }

  const { events, gaps_identified, timeline_summary } = timeline.analysis

  function toggleQuote(idx: number) {
    setExpandedQuotes((prev) => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      {timeline_summary && (
        <div className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
          <p className="text-sm text-zinc-300">{timeline_summary}</p>
        </div>
      )}

      {/* Timeline */}
      {events.length > 0 && (
        <div className="relative pl-6 border-l-2 border-zinc-700 space-y-4">
          {events.map((ev: TimelineEvent, i: number) => (
            <div key={i} className="relative">
              <div className="absolute -left-[1.6rem] top-1 w-2.5 h-2.5 rounded-full bg-zinc-600 border-2 border-zinc-900" />
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-zinc-400">
                    {ev.date}{ev.time ? ` ${ev.time}` : ''}
                  </span>
                  <Badge variant={confidenceVariant[ev.confidence] ?? 'neutral'}>
                    {ev.confidence}
                  </Badge>
                </div>
                <p className="text-sm text-zinc-200">{ev.description}</p>
                {ev.participants.length > 0 && (
                  <p className="text-xs text-zinc-500 mt-1">
                    Participants: {ev.participants.join(', ')}
                  </p>
                )}
                {ev.evidence_quote && (
                  <button
                    type="button"
                    className="text-xs text-zinc-500 hover:text-zinc-300 mt-1 cursor-pointer"
                    onClick={() => toggleQuote(i)}
                  >
                    {expandedQuotes.has(i) ? 'Hide' : 'Show'} evidence
                  </button>
                )}
                {expandedQuotes.has(i) && ev.evidence_quote && (
                  <p className="text-xs text-zinc-500 mt-1 italic border-l-2 border-zinc-700 pl-2">
                    &ldquo;{ev.evidence_quote}&rdquo;
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Gaps */}
      {gaps_identified.length > 0 && (
        <div className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-3">
          <p className="text-xs font-medium text-amber-400 mb-2">Gaps Identified</p>
          <ul className="space-y-1">
            {gaps_identified.map((gap, i) => (
              <li key={i} className="text-xs text-amber-300/70">- {gap}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={generate}>
          Regenerate
        </Button>
      </div>
    </div>
  )
}
