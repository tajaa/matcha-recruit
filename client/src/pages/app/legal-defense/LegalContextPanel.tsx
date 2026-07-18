import { useEffect, useState } from 'react'
import { ExternalLink, Landmark, Loader2, Search } from 'lucide-react'
import { Button, Input, Select } from '../../../components/ui'
import { fetchLocations } from '../../../api/compliance'
import type { BusinessLocation } from '../../../types/compliance'
import { updateMatter, type LegalContext, type ResearchRow } from '../../../api/legalDefense'
import { LABEL } from './shared'

/** Jurisdiction chain + external legal research (CourtListener cases +
 *  grounded-Gemini guidance). Informational only — every surface here
 *  carries the same disclaimer: verify with counsel before relying on it. */
export function LegalContextPanel({ legalContext, research, onRunResearch, researching, matterId, onRefresh }: {
  legalContext: LegalContext | null | undefined
  research: ResearchRow | null
  onRunResearch: (includeGuidance?: boolean) => void
  researching: boolean
  matterId: string
  onRefresh: () => void
}) {
  if (!legalContext) {
    return <JurisdictionSetter matterId={matterId} onRefresh={onRefresh} />
  }

  return (
    <div className="border-b border-white/[0.06] px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className={LABEL}>Legal landscape</span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={researching}
            onClick={() => onRunResearch(false)}
            className="text-[11px] text-zinc-500 underline decoration-dotted underline-offset-2 transition-colors hover:text-zinc-300 disabled:opacity-50"
            title="Case law only — skips the slower AI guidance summary"
          >
            Case law only
          </button>
          <Button size="sm" variant="secondary" disabled={researching} onClick={() => onRunResearch(true)}>
            {researching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
            Research
          </Button>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Landmark className="h-3.5 w-3.5 shrink-0 text-emerald-400/80" />
        {legalContext.chain.map((c, i) => (
          <span key={c.id} className="flex items-center gap-1.5">
            {i > 0 && <span className="text-zinc-700">→</span>}
            <span className="rounded-full border border-white/[0.08] px-2 py-0.5 text-[11px] text-zinc-300">
              {c.display_name}
            </span>
          </span>
        ))}
      </div>

      {!research && !researching && (
        <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
          No case law pulled yet — <span className="text-zinc-400">Research</span> finds related court
          decisions and public guidance for this jurisdiction (takes ~2 min).
        </p>
      )}

      {research?.status === 'failed' && (
        <p className="mt-2 text-[11px] text-red-400/90">Research failed: {research.error || 'unknown error'}</p>
      )}

      {/* A persisted 'running' row with no local spinner means the run was
          interrupted (page reload mid-run, backend restart) — say so instead
          of rendering nothing, and leave the button enabled to re-run. */}
      {research?.status === 'running' && !researching && (
        <p className="mt-2 text-[11px] text-amber-500/90">
          A research run was started but never finished (likely interrupted). Run it again.
        </p>
      )}

      {research && research.status === 'complete' && (
        <div className="mt-3 max-h-64 space-y-3 overflow-y-auto">
          {research.error && (
            <p className="text-[10px] text-amber-500/80">{research.error}</p>
          )}
          {/* Complete-but-empty must say so — a silent blank here reads as
              "the request did nothing" (it did run; nothing matched). */}
          {(research.cases?.length ?? 0) === 0 && !research.guidance?.summary && !research.error && (
            <p className="text-[11px] leading-relaxed text-zinc-500">
              Research ran, but no matching cases were found
              {research.query ? <> (searched “{research.query}”)</> : null}.
              Refine the allegation on the matter and run it again.
            </p>
          )}
          {(research.cases?.length ?? 0) > 0 && (
            <div className="space-y-1.5">
              <div className="text-[10px] uppercase tracking-wide text-zinc-600">Cases located</div>
              {research.cases!.map((c) => (
                <a key={c.id} href={c.url} target="_blank" rel="noopener noreferrer"
                  className="block rounded-lg border border-white/[0.06] px-2.5 py-1.5 transition-colors hover:bg-white/[0.02]">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs text-zinc-200">{c.case_name}</span>
                    <ExternalLink className="h-3 w-3 shrink-0 text-zinc-600" />
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-zinc-500">
                    {[c.citation, c.court, c.date_filed].filter(Boolean).join(' · ')}
                  </div>
                </a>
              ))}
            </div>
          )}
          {research.guidance?.summary && (
            <div className="space-y-1.5">
              <div className="text-[10px] uppercase tracking-wide text-zinc-600">Public guidance</div>
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-zinc-400">{research.guidance.summary}</p>
              {research.guidance.key_authorities?.length > 0 && (
                <ul className="space-y-1">
                  {research.guidance.key_authorities.map((a, i) => (
                    <li key={i} className="text-[11px] text-zinc-500">
                      <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-emerald-400/80 hover:text-emerald-300">
                        {a.name}
                      </a>
                      {a.publisher ? ` — ${a.publisher}` : ''}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      <p className="mt-3 text-[10px] leading-relaxed text-zinc-600">
        External research is informational only — not legal advice; verify with counsel.
      </p>
    </div>
  )
}

/** Empty-state replacement: instead of a dead-end "set a location" message,
 *  let the user set the matter's jurisdiction right here — that's what
 *  unlocks governing law + the case-law Research button. */
function JurisdictionSetter({ matterId, onRefresh }: { matterId: string; onRefresh: () => void }) {
  const [locations, setLocations] = useState<BusinessLocation[]>([])
  const [locationId, setLocationId] = useState('')
  const [state, setState] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    fetchLocations().then(setLocations).catch(() => setLocations([]))
  }, [])

  const canSet = Boolean(locationId) || state.trim().length === 2

  async function save() {
    if (!canSet || saving) return
    setSaving(true); setErr(null)
    try {
      await updateMatter(matterId, {
        location_id: locationId || null,
        jurisdiction_state: locationId ? null : state.trim().toUpperCase(),
      })
      onRefresh()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to set jurisdiction')
      setSaving(false)
    }
  }

  return (
    <div className="border-b border-white/[0.06] px-4 py-3">
      <div className={LABEL}>Legal landscape</div>
      <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">
        Set a location or state — it grounds the matter in governing law and unlocks case-law research.
      </p>
      <div className="mt-2 space-y-2">
        {locations.length > 0 && (
          <Select
            value={locationId}
            placeholder="Pick a location…"
            options={locations.map((l) => ({ value: l.id, label: `${l.name || 'Location'} — ${l.city}, ${l.state}` }))}
            onChange={(e) => setLocationId(e.target.value)}
          />
        )}
        {!locationId && (
          <Input
            value={state}
            maxLength={2}
            placeholder={locations.length > 0 ? 'Or a state, e.g. CA' : 'State, e.g. CA'}
            onChange={(e) => setState(e.target.value.toUpperCase())}
          />
        )}
        {err && <p className="text-[11px] text-red-400/90">{err}</p>}
        <Button size="sm" variant="secondary" disabled={!canSet || saving} onClick={() => void save()}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Landmark className="h-3.5 w-3.5" />}
          Set jurisdiction
        </Button>
      </div>
    </div>
  )
}
