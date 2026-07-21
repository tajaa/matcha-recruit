import { useState } from 'react'
import { IRAnalysisPanel } from './IRAnalysisPanel'
import { Badge } from '../ui'
import type { IRPrecedentAnalysis, IRPrecedentMatch, IRScoreBreakdown } from '../../types/ir'
import { typeLabel, statusLabel, severityLabel, SEVERITY_BADGE, STATUS_BADGE } from '../../types/ir'

function ScoreBreakdown({ sb }: { sb: IRScoreBreakdown }) {
  const dims: [string, number][] = [
    ['Type Match', sb.type_match],
    ['Severity', sb.severity_proximity],
    ['Category', sb.category_overlap],
    ['Location', sb.location_similarity],
    ['Temporal', sb.temporal_pattern],
    ['Text', sb.text_similarity],
    ['Root Cause', sb.root_cause_similarity],
  ]
  return (
    <div className="space-y-1 mt-2">
      {dims.map(([label, score]) => (
        <div key={label} className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-500 w-20 shrink-0">{label}</span>
          <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
            <div className="h-full rounded-full bg-emerald-500/60" style={{ width: `${score * 100}%` }} />
          </div>
          <span className="text-[11px] text-zinc-600 w-8 text-right">{Math.round(score * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

function SimilarBody({ result }: { result: IRPrecedentAnalysis }) {
  const [expandedScores, setExpandedScores] = useState<string | null>(null)
  return (
    <div className="space-y-3">
      {result.pattern_summary && (
        <div className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
          <p className="text-sm text-zinc-300">{result.pattern_summary}</p>
        </div>
      )}
      {result.precedents.length === 0 && (
        <p className="text-sm text-zinc-400 text-center py-4">No similar incidents found.</p>
      )}
      {result.precedents.map((p: IRPrecedentMatch) => (
        <div key={p.incident_id} className="border border-zinc-800 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-mono text-zinc-500">{p.incident_number}</span>
              <h4 className="text-sm font-medium text-zinc-100 truncate">{p.title}</h4>
            </div>
            <span className="text-sm font-mono text-emerald-400 shrink-0">{Math.round(p.similarity_score * 100)}%</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="neutral">{typeLabel(p.incident_type)}</Badge>
            <Badge variant={SEVERITY_BADGE[p.severity] ?? 'neutral'}>{severityLabel(p.severity)}</Badge>
            <Badge variant={STATUS_BADGE[p.status] ?? 'neutral'}>{statusLabel(p.status)}</Badge>
            {p.resolution_days != null && (
              <span className="text-[11px] text-zinc-500">{p.resolution_days}d to resolve</span>
            )}
          </div>
          {p.common_factors.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {p.common_factors.map((f, i) => (
                <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">{f}</span>
              ))}
            </div>
          )}
          <button type="button" onClick={() => setExpandedScores(expandedScores === p.incident_id ? null : p.incident_id)}
            className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors">
            {expandedScores === p.incident_id ? 'Hide score breakdown' : 'Show score breakdown'}
          </button>
          {expandedScores === p.incident_id && <ScoreBreakdown sb={p.score_breakdown} />}
        </div>
      ))}
    </div>
  )
}

export function IRSimilarIncidentsPanel({ incidentId }: { incidentId: string }) {
  return (
    <IRAnalysisPanel<IRPrecedentAnalysis>
      incidentId={incidentId}
      analysisType="similar"
      title="Similar Incidents"
      runLabel="Find Similar"
      streamingLabel="Searching..."
      renderResult={(res) => <SimilarBody result={res} />}
    />
  )
}
