import { useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { Card } from '../../../components/ui'
import { useAsync } from '../../../hooks/useAsync'
import { RegisterSpinner } from '../../../components/register/registerKit'
import { getDoReadiness, upsertDoAttestation, type DoStatus } from '../../../api/risk/managementLiability'

const STATUSES: DoStatus[] = ['in_place', 'partial', 'gap', 'unknown']
const BAND_TONE: Record<string, string> = {
  strong: 'text-emerald-400', adequate: 'text-lime-400', developing: 'text-amber-400', exposed: 'text-rose-400',
}
const FACTOR_TONE: Record<string, string> = { strong: 'text-emerald-400', partial: 'text-amber-400', gap: 'text-rose-400' }

export default function ManagementLiability() {
  const { data, loading, setData } = useAsync(() => getDoReadiness(), [], null)
  const [busy, setBusy] = useState<string | null>(null)

  async function setStatus(item_key: string, status: DoStatus) {
    setBusy(item_key)
    try { setData(await upsertDoAttestation({ item_key, status })) } finally { setBusy(null) }
  }

  if (loading) return <RegisterSpinner />
  if (!data) return <p className="text-sm text-zinc-500">Unable to load D&O readiness.</p>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-zinc-400" /> D&O / Management Liability Readiness
        </h1>
        <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Directors & Officers underwriting turns on governance + financial health. Attest each factor to produce a readiness score and a submission-ready checklist.</p>
      </div>

      <Card className="p-5 flex items-center gap-6">
        <div>
          <div className={`text-4xl font-semibold ${BAND_TONE[data.band] || 'text-zinc-200'}`}>{data.score}<span className="text-lg text-zinc-600">/100</span></div>
          <div className={`text-sm capitalize ${BAND_TONE[data.band] || 'text-zinc-400'}`}>{data.band}</div>
        </div>
        <div className="text-sm text-zinc-500">
          <div>Coverage of factor set: {Math.round(data.coverage * 100)}%</div>
          {data.top_gap && <div className="mt-1 text-amber-400">Top gap: {data.top_gap.label} ({data.top_gap.score}/100)</div>}
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-sm font-medium text-zinc-300 mb-3">Factors</h2>
        <div className="space-y-2">
          {data.factors.map((f) => (
            <div key={f.key} className="flex items-center justify-between gap-4 py-2 border-b border-zinc-900 last:border-0">
              <div className="min-w-0">
                <div className="text-sm text-zinc-200">{f.label} <span className="text-xs text-zinc-600">· weight {f.weight}</span></div>
                <div className="text-xs text-zinc-500">{f.detail} · <span className={FACTOR_TONE[f.status] || 'text-zinc-500'}>{f.status}</span></div>
              </div>
              <select
                value={f.attestation?.status || 'unknown'}
                disabled={busy === f.key}
                onChange={(e) => setStatus(f.key, e.target.value as DoStatus)}
                className="shrink-0 bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1.5 text-sm text-zinc-200"
              >
                {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
              </select>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
