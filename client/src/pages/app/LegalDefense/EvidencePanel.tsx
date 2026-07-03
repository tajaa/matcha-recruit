import { useEffect, useState } from 'react'
import { ChevronRight, Loader2 } from 'lucide-react'
import { api } from '../../../api/client'
import type { EvidencePreview, EvidenceRecord } from '../../../api/legalDefense'
import type { IRIncident } from '../../../types/ir'
import type { ERCase } from '../../../types/er'
import { disciplineApi, type DisciplineRecord } from '../../../api/discipline'
import { trainingApi, type TrainingRecord } from '../../../api/training'
import type { AccommodationCase } from '../AccommodationDetail'
import { Button, Modal } from '../../../components/ui'
import { LABEL, SOURCE_META, hum } from './shared'

/** cid is "<kind>:<id>" (see legal_defense.py _src_* builders). Kinds with a
 *  real single-record backend get the full doc-viewer fetch below; the rest
 *  (compliance_req, policy_ack) have no detail beyond the evidence-corpus
 *  summary, which is already the full text (built server-side, not
 *  truncated) — so they just render that. */
const FETCHERS: Record<string, (id: string) => Promise<unknown>> = {
  incident: (id) => api.get<IRIncident>(`/ir/incidents/${id}`),
  er_case: (id) => api.get<ERCase>(`/er/cases/${id}`),
  discipline: (id) => disciplineApi.get(id),
  training: (id) => trainingApi.getRecord(id),
  accommodation: (id) => api.get<AccommodationCase>(`/accommodations/${id}`),
}

type Field = { label: string; value: string }

function fmtDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString() : ''
}

/** Builds the field grid + narrative blocks for the fetched record. Kept as
 *  one switch (rather than per-kind components) since each case is a
 *  handful of label/value lines, not real markup. */
function buildDetail(kind: string, data: unknown): { fields: Field[]; narrative: Field[] } {
  switch (kind) {
    case 'incident': {
      const r = data as IRIncident
      return {
        fields: [
          { label: 'Status', value: hum(r.status) },
          { label: 'Severity', value: hum(r.severity) },
          { label: 'Type', value: hum(r.incident_type) },
          { label: 'Location', value: r.location ?? '' },
          { label: 'Reported by', value: r.reported_by_name },
          { label: 'Witnesses', value: r.witnesses?.length ? String(r.witnesses.length) : '' },
        ],
        narrative: [
          { label: 'Description', value: r.description ?? '' },
          { label: 'Root cause', value: r.root_cause ?? '' },
          { label: 'Corrective actions', value: r.corrective_actions ?? '' },
        ],
      }
    }
    case 'er_case': {
      const r = data as ERCase
      return {
        fields: [
          { label: 'Status', value: hum(r.status) },
          { label: 'Category', value: hum(r.category ?? '') },
          { label: 'Outcome', value: hum(r.outcome ?? '') },
          { label: 'Involved employees', value: r.involved_employees?.length ? String(r.involved_employees.length) : '' },
        ],
        narrative: [{ label: 'Description', value: r.description ?? '' }],
      }
    }
    case 'discipline': {
      const r = data as DisciplineRecord
      return {
        fields: [
          { label: 'Type', value: hum(r.discipline_type) },
          { label: 'Status', value: hum(r.status) },
          { label: 'Severity', value: hum(r.severity) },
          { label: 'Infraction', value: hum(r.infraction_type) },
          { label: 'Issued', value: fmtDate(r.issued_date) },
          { label: 'Review date', value: fmtDate(r.review_date) },
          { label: 'Signature', value: hum(r.signature_status) },
        ],
        narrative: [
          { label: 'Description', value: r.description ?? '' },
          { label: 'Outcome notes', value: r.outcome_notes ?? '' },
        ],
      }
    }
    case 'training': {
      const r = data as TrainingRecord
      return {
        fields: [
          { label: 'Status', value: hum(r.status) },
          { label: 'Type', value: hum(r.training_type) },
          { label: 'Provider', value: r.provider ?? '' },
          { label: 'Score', value: r.score != null ? String(r.score) : '' },
          { label: 'Assigned', value: fmtDate(r.assigned_date) },
          { label: 'Due', value: fmtDate(r.due_date) },
          { label: 'Completed', value: fmtDate(r.completed_date) },
          { label: 'Expires', value: fmtDate(r.expiration_date) },
        ],
        narrative: [{ label: 'Notes', value: r.notes ?? '' }],
      }
    }
    case 'accommodation': {
      const r = data as AccommodationCase
      return {
        fields: [
          { label: 'Status', value: hum(r.status) },
          { label: 'Disability category', value: hum(r.disability_category ?? '') },
        ],
        narrative: [
          { label: 'Description', value: r.description ?? '' },
          { label: 'Requested accommodation', value: r.requested_accommodation ?? '' },
          { label: 'Approved accommodation', value: r.approved_accommodation ?? '' },
          { label: 'Denial reason', value: r.denial_reason ?? '' },
          { label: 'Undue hardship analysis', value: r.undue_hardship_analysis ?? '' },
        ],
      }
    }
    default:
      return { fields: [], narrative: [] }
  }
}

type Selected = { record: EvidenceRecord; sourceLabel: string }
type Detail = { loading: boolean; data: unknown; error: string | null }

/** Evidence browser: every in-scope source expands to its record list —
 *  ref, one-line summary, date. Data is the already-fetched preview corpus.
 *  Clicking a record opens it as a doc-viewer modal in place — it never
 *  navigates away from the matter workbench. */
export function EvidencePanel({ evidence }: { evidence: EvidencePreview | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [selected, setSelected] = useState<Selected | null>(null)
  const [detail, setDetail] = useState<Detail>({ loading: false, data: null, error: null })

  useEffect(() => {
    if (!selected) return
    const [kind, id] = selected.record.cid.split(':')
    const fetcher = FETCHERS[kind]
    if (!fetcher) {
      setDetail({ loading: false, data: null, error: null })
      return
    }
    let cancelled = false
    setDetail({ loading: true, data: null, error: null })
    fetcher(id)
      .then((data) => { if (!cancelled) setDetail({ loading: false, data, error: null }) })
      .catch((e) => { if (!cancelled) setDetail({ loading: false, data: null, error: e instanceof Error ? e.message : 'Failed to load' }) })
    return () => { cancelled = true }
  }, [selected])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
        <span className={LABEL}>Evidence</span>
        <span className="font-mono text-[11px] tabular-nums text-zinc-500">
          {evidence ? `${evidence.total} records` : '…'}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {!evidence ? (
          <p className="px-4 py-2 text-xs text-zinc-600">Loading the record…</p>
        ) : evidence.total === 0 ? (
          <p className="px-4 py-2 text-xs text-zinc-500">
            No records fall inside the matter's evidence window. Widen the window when creating the matter to pull more history in.
          </p>
        ) : (
          <>
            {SOURCE_META.map((meta) => {
              const src = evidence.sources[meta.key]
              if (!src || src.records.length === 0) return null
              const isOpen = !!open[meta.key]
              const Icon = meta.icon
              return (
                <div key={meta.key} className="border-t border-white/[0.04] first:border-t-0">
                  <button
                    onClick={() => setOpen((o) => ({ ...o, [meta.key]: !o[meta.key] }))}
                    className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-white/[0.02]"
                  >
                    <ChevronRight className={`h-3 w-3 shrink-0 text-zinc-600 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    <Icon className="h-3.5 w-3.5 shrink-0 text-emerald-400/80" />
                    <span className="flex-1 truncate text-xs text-zinc-300">{src.label}</span>
                    <span className="font-mono text-[11px] tabular-nums text-zinc-500">{src.records.length}</span>
                  </button>
                  {isOpen && (
                    <div className="border-t border-white/[0.04] bg-white/[0.01] pb-1">
                      {src.records.map((r) => (
                        <button
                          key={r.cid}
                          onClick={() => setSelected({ record: r, sourceLabel: src.label })}
                          className="block w-full px-4 py-1.5 pl-9 text-left transition-colors hover:bg-white/[0.03]"
                        >
                          <div className="flex items-baseline justify-between gap-2 font-mono text-[10px] tabular-nums">
                            <span className="truncate text-zinc-400">{r.ref || '—'}</span>
                            <span className="shrink-0 text-zinc-600">{r.when || ''}</span>
                          </div>
                          <div className="truncate text-[11px] leading-snug text-zinc-500" title={r.summary}>
                            {r.summary}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {evidence.notes.length > 0 && (
              <div className="border-t border-white/[0.04] px-4 py-2">
                {evidence.notes.map((n, i) => (
                  <p key={i} className="text-[10px] leading-relaxed text-zinc-600">{n}</p>
                ))}
              </div>
            )}
          </>
        )}
      </div>
      {selected && (
        <Modal open onClose={() => setSelected(null)} title={selected.sourceLabel} width="lg">
          <div className="space-y-3">
            <div className="flex items-baseline justify-between gap-2 font-mono text-xs tabular-nums text-zinc-400">
              <span>{selected.record.ref || '—'}</span>
              <span className="text-zinc-500">{selected.record.when || ''}</span>
            </div>

            {detail.loading && (
              <div className="flex items-center gap-2 py-2 text-xs text-zinc-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading the full record…
              </div>
            )}

            {!detail.loading && detail.error && (
              <div className="space-y-2">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">{selected.record.summary}</p>
                <p className="text-[11px] text-amber-500/80">Couldn't load the full record — showing the evidence summary.</p>
              </div>
            )}

            {!detail.loading && !detail.error && detail.data && (() => {
              const { fields, narrative } = buildDetail(selected.record.cid.split(':')[0], detail.data)
              const shownFields = fields.filter((f) => f.value)
              const shownNarrative = narrative.filter((n) => n.value)
              return (
                <>
                  {shownFields.length > 0 && (
                    <div className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border border-white/[0.06] p-3">
                      {shownFields.map((f) => (
                        <div key={f.label}>
                          <div className="text-[10px] uppercase tracking-wide text-zinc-500">{f.label}</div>
                          <div className="text-sm text-zinc-200">{f.value}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {shownNarrative.map((n) => (
                    <div key={n.label}>
                      <div className="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">{n.label}</div>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">{n.value}</p>
                    </div>
                  ))}
                </>
              )
            })()}

            {!detail.loading && !detail.error && !detail.data && (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">{selected.record.summary}</p>
            )}

            <div className="flex justify-end pt-1">
              <Button variant="secondary" onClick={() => setSelected(null)}>Close</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
