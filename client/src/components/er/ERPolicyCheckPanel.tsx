import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import { Badge, Button, type BadgeVariant } from '../ui'

// ── Types ──────────────────────────────────────────────────────────────────────

type ViolationEvidence = {
  source_document_id: string
  quote: string
  location: string
  how_it_violates: string
}

type PolicyViolation = {
  policy_section: string
  policy_text: string
  severity: 'major' | 'minor'
  evidence: ViolationEvidence[]
  analysis: string
}

type PolicyCheckResponse = {
  analysis: {
    violations: unknown[]
    policies_potentially_applicable?: string[]
    summary?: string
  }
  source_documents: string[]
  generated_at: string | null
}

type Props = {
  caseId: string
}

const severityVariant: Record<string, BadgeVariant> = {
  major: 'danger',
  minor: 'warning',
}

function normalizeViolations(payload: unknown): PolicyViolation[] {
  if (!Array.isArray(payload)) return []
  return payload
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map((item) => {
      const evidence = Array.isArray(item.evidence)
        ? item.evidence
            .filter((e): e is Record<string, unknown> => !!e && typeof e === 'object')
            .map((e) => ({
              source_document_id: typeof e.source_document_id === 'string' ? e.source_document_id : '',
              quote: typeof e.quote === 'string' ? e.quote : '',
              location: typeof e.location === 'string' ? e.location : '',
              how_it_violates: typeof e.how_it_violates === 'string' ? e.how_it_violates : '',
            }))
        : []
      return {
        policy_section: typeof item.policy_section === 'string' ? item.policy_section : '',
        policy_text: typeof item.policy_text === 'string' ? item.policy_text : '',
        severity: item.severity === 'major' ? 'major' as const : 'minor' as const,
        evidence,
        analysis: typeof item.analysis === 'string' ? item.analysis : '',
      }
    })
}

// ── Component ──────────────────────────────────────────────────────────────────

export function ERPolicyCheckPanel({ caseId }: Props) {
  const [violations, setViolations] = useState<PolicyViolation[]>([])
  const [policiesChecked, setPoliciesChecked] = useState(0)
  const [generatedAt, setGeneratedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Fetch existing policy check on mount
  useEffect(() => {
    let cancelled = false
    async function fetchExisting() {
      try {
        const res = await api.get<PolicyCheckResponse>(`/er/cases/${caseId}/analysis/policy-check`)
        if (cancelled) return
        if (res.generated_at) {
          setViolations(normalizeViolations(res.analysis.violations))
          setPoliciesChecked(res.analysis.policies_potentially_applicable?.length ?? res.source_documents.length)
          setGeneratedAt(res.generated_at)
        }
      } catch {
        // No existing check
      }
    }
    fetchExisting()
    return () => { cancelled = true }
  }, [caseId])

  async function runCheck() {
    setLoading(true)
    setError('')
    try {
      const postRes = await api.post<{ status: string }>(`/er/cases/${caseId}/analysis/policy-check`)

      if (postRes.status === 'queued') {
        // Poll until ready
        for (let i = 0; i < 30; i++) {
          await new Promise((r) => setTimeout(r, 2000))
          const res = await api.get<PolicyCheckResponse>(`/er/cases/${caseId}/analysis/policy-check`)
          if (res.generated_at && res.generated_at !== generatedAt) {
            setViolations(normalizeViolations(res.analysis.violations))
            setPoliciesChecked(res.analysis.policies_potentially_applicable?.length ?? res.source_documents.length)
            setGeneratedAt(res.generated_at)
            return
          }
        }
        setError('Policy check is taking longer than expected. Please refresh.')
      } else {
        // Sync — fetch result
        const res = await api.get<PolicyCheckResponse>(`/er/cases/${caseId}/analysis/policy-check`)
        setViolations(normalizeViolations(res.analysis.violations))
        setPoliciesChecked(res.analysis.policies_potentially_applicable?.length ?? res.source_documents.length)
        setGeneratedAt(res.generated_at)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Policy check failed')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-500 py-8 text-center">Running policy check against company handbook...</p>
  }

  if (!generatedAt) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500 mb-4">
          Compare uploaded evidence against all active company policies and handbook to identify violations.
        </p>
        <Button onClick={runCheck}>Run Policy Check</Button>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center gap-3 bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-2.5">
        <span className="text-[11px] text-zinc-400">
          {policiesChecked} {policiesChecked === 1 ? 'source' : 'sources'} checked
        </span>
        <span className="text-zinc-700">·</span>
        <span className={`text-[11px] font-medium ${violations.length > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
          {violations.length} violation{violations.length !== 1 ? 's' : ''} found
        </span>
      </div>

      {/* No violations */}
      {violations.length === 0 && (
        <div className="text-center py-6">
          <p className="text-sm text-zinc-400">No policy violations identified.</p>
          <p className="text-xs text-zinc-600 mt-1">
            Evidence was reviewed against all active company policies. No clear violations were found.
          </p>
        </div>
      )}

      {/* Violation cards */}
      {violations.map((v, i) => (
        <div key={i} className="border border-zinc-800 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Badge variant={severityVariant[v.severity] ?? 'neutral'}>
              {v.severity} violation
            </Badge>
          </div>

          {v.policy_section && (
            <h4 className="text-sm font-medium text-zinc-100">{v.policy_section}</h4>
          )}

          {v.policy_text && v.policy_text !== '""' && (
            <div className="border-l-2 border-zinc-700 pl-3">
              <p className="text-sm text-zinc-400 italic leading-relaxed">"{v.policy_text}"</p>
            </div>
          )}

          {v.evidence.map((e, j) => (
            <div key={j} className="border-l-2 border-zinc-700 pl-3 space-y-1">
              <p className="text-sm text-zinc-200 leading-relaxed">"{e.quote}"</p>
              <p className="text-xs text-zinc-500">{e.how_it_violates}</p>
              {e.location && (
                <p className="text-[11px] text-zinc-600 font-mono">{e.location}</p>
              )}
            </div>
          ))}

          {v.analysis && (
            <p className="text-xs text-zinc-500 leading-relaxed">{v.analysis}</p>
          )}
        </div>
      ))}

      {/* Regenerate */}
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={runCheck}>
          Re-run Check
        </Button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
