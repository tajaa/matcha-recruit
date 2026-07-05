import { useState, useEffect } from 'react'
import { Shield, AlertTriangle, Loader2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import { fetchEplClientDetail, recordEplAttestation } from '../../../api/broker'
import type { EplReadiness, EplFactor, EplAttestationStatus } from '../../../types/broker'

const EPL_BAND_TONE: Record<string, string> = {
  strong: 'text-emerald-400',
  adequate: 'text-amber-400',
  developing: 'text-orange-400',
  exposed: 'text-red-400',
}
const EPL_BAND_LABEL: Record<string, string> = {
  strong: 'Strong', adequate: 'Adequate', developing: 'Developing', exposed: 'Exposed',
}
const EPL_STATUS_DOT: Record<string, string> = {
  strong: 'bg-emerald-500', partial: 'bg-amber-500', gap: 'bg-red-500',
}
const EPL_ATTEST_OPTIONS = [
  { value: 'unknown', label: 'Not reviewed' },
  { value: 'in_place', label: 'In place' },
  { value: 'partial', label: 'Partial' },
  { value: 'gap', label: 'Gap' },
]

function EplFactorRow({ f }: { f: EplFactor }) {
  const notAssessed = f.assessed === false
  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
      <span className={`h-2 w-2 rounded-full flex-shrink-0 ${notAssessed ? 'bg-zinc-700' : EPL_STATUS_DOT[f.status]}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-zinc-200">{f.label}</span>
          <span className="text-[10px] text-zinc-600">{f.weight} pts</span>
        </div>
        <p className="text-[11px] text-zinc-500 truncate">{f.detail}</p>
      </div>
      {notAssessed ? (
        <span className="text-[10px] text-zinc-500 uppercase tracking-wide shrink-0">Not assessed</span>
      ) : (
        <span className="text-sm font-mono text-zinc-300 w-10 text-right">{f.score}</span>
      )}
    </div>
  )
}

function EplAttestedRow({ f, saving, onSet }: {
  f: EplFactor; saving: boolean; onSet: (s: EplAttestationStatus) => void
}) {
  const status: EplAttestationStatus = f.attestation?.status ?? 'unknown'
  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
      <span className={`h-2 w-2 rounded-full flex-shrink-0 ${EPL_STATUS_DOT[f.status]}`} />
      <div className="flex-1 min-w-0">
        <span className="text-sm text-zinc-200">{f.label}</span>
        <span className="text-[10px] text-zinc-600 ml-2">{f.weight} pts</span>
      </div>
      <div className="flex items-center gap-2">
        {saving && <Loader2 className="h-3.5 w-3.5 text-zinc-500 animate-spin" />}
        <select
          value={status}
          disabled={saving}
          onChange={(e) => onSet(e.target.value as EplAttestationStatus)}
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500"
        >
          {EPL_ATTEST_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
    </div>
  )
}

export function EplTab({ companyId }: { companyId: string }) {
  const [data, setData] = useState<EplReadiness | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [savingKey, setSavingKey] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(false)
    fetchEplClientDetail(companyId)
      .then(setData)
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [companyId])

  async function setAttestation(key: string, status: EplAttestationStatus) {
    setSavingKey(key)
    try {
      const updated = await recordEplAttestation(companyId, key, { status })
      setData(updated)
    } catch { /* leave prior state on failure */ }
    finally { setSavingKey(null) }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-40"><Loader2 className="h-5 w-5 text-zinc-500 animate-spin" /></div>
  }
  if (error || !data) {
    return <Card className="p-5"><p className="text-sm text-zinc-500">Unable to load EPL readiness.</p></Card>
  }

  const derived = data.factors.filter((f) => f.kind === 'derived')
  const attested = data.factors.filter((f) => f.kind === 'attested')

  return (
    <div className="space-y-4">
      {/* Score header */}
      <Card className="p-5">
        <div className="flex items-center gap-5">
          <div className="text-center flex-shrink-0">
            <div className={`text-5xl font-light font-mono ${EPL_BAND_TONE[data.band]}`}>{data.score}</div>
            <div className={`text-[10px] uppercase tracking-widest font-bold mt-1 ${EPL_BAND_TONE[data.band]}`}>{EPL_BAND_LABEL[data.band]}</div>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-medium text-zinc-200 mb-0.5">EPL Underwriting Readiness</h3>
            <p className="text-[11px] text-zinc-500 mb-3">How this client&rsquo;s HR posture maps to what EPL underwriters ask (WTW IMR 2026).</p>
            <div className="h-2 rounded-full overflow-hidden bg-zinc-800">
              <div className="h-full bg-emerald-500/70" style={{ width: `${data.score}%` }} />
            </div>
            <div className="flex gap-4 mt-2 text-[11px] text-zinc-500">
              <span>From data <span className="font-mono text-zinc-300">{data.derived_score}</span>/{data.derived_max ?? 55}</span>
              <span>Attested <span className="font-mono text-zinc-300">{data.attested_score}</span>/{data.attested_max ?? 45}</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Derived factors */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">From your Matcha data</h3>
        </div>
        <div className="space-y-1">
          {derived.map((f) => <EplFactorRow key={f.key} f={f} />)}
        </div>
      </Card>

      {/* Attested factors */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle className="h-4 w-4 text-zinc-500" />
          <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Underwriter asks &mdash; record during review</h3>
        </div>
        <p className="text-[11px] text-zinc-600 mb-4">Matcha has no data source for these. Set each as you confirm it with the client.</p>
        <div className="space-y-1">
          {attested.map((f) => (
            <EplAttestedRow key={f.key} f={f} saving={savingKey === f.key} onSet={(s) => setAttestation(f.key, s)} />
          ))}
        </div>
      </Card>
    </div>
  )
}
