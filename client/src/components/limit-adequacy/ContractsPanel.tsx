import { useEffect, useRef, useState } from 'react'
import {
  Loader2, Upload, Plus, Trash2, Check, FileText, FileDown, ExternalLink, ShieldAlert,
} from 'lucide-react'
import { Card } from '../ui'
import type {
  ContractRecord, ContractRequirement, ContractReview, CoverageCatalogEntry,
  ContractType, Indemnity, IndemnityDirection, IndemnityForm, IndemnityVerdict, RiskTransfer,
} from '../../types/limitAdequacy'
import {
  fmtMoney, VERDICT_TONE, VERDICT_LABEL, CONTRACT_TYPE_LABEL,
  INDEMNITY_FORM_LABEL, INDEMNITY_DIRECTION_LABEL, EMPTY_INDEMNITY,
} from '../../types/limitAdequacy'
import type { ContractPayload } from '../../api/limitAdequacy'

/** The tenant page and the broker client tab drive the same contract review
 *  against different endpoints. Injecting the calls keeps one UI. `create` and
 *  `remove` are optional — the broker has no manual-entry or delete path. */
export type ContractsApi = {
  upload: (file: File) => Promise<ContractRecord>
  update: (id: string, payload: ContractPayload) => Promise<ContractRecord>
  confirm: (id: string) => Promise<ContractRecord>
  review: (id: string) => Promise<ContractReview>
  reviewPdf: (id: string, name: string) => Promise<void>
  sourceUrl: (id: string) => Promise<{ url: string }>
  create?: (payload: ContractPayload & { name: string; requirements: ContractRequirement[] }) => Promise<ContractRecord>
  remove?: (id: string) => Promise<unknown>
}

const ENDORSEMENTS: { key: keyof ContractRequirement; label: string }[] = [
  { key: 'additional_insured', label: 'Additional insured' },
  { key: 'waiver_of_subrogation', label: 'Waiver of subrogation' },
  { key: 'primary_noncontributory', label: 'Primary & non-contributory' },
]

const CONTRACT_TYPES: ContractType[] = ['lease', 'construction', 'vendor_service', 'msa', 'other']
const FORMS: IndemnityForm[] = ['unclear', 'broad', 'intermediate', 'limited']
const DIRECTIONS: IndemnityDirection[] = ['unclear', 'we_indemnify_them', 'they_indemnify_us', 'mutual']

export const DISCLAIMER =
  'Review limited to insurance and risk-transfer provisions. Not legal advice — have counsel review the full agreement.'

export function parseMoney(s: string): number | null {
  const v = parseFloat(s.replace(/[$,\s]/g, ''))
  return Number.isFinite(v) ? v : null
}

/** Mirrors the server's `_norm_state` — a half-typed code is no code at all. */
function normState(s: string): string | null {
  const v = s.trim().toUpperCase()
  return /^[A-Z]{2}$/.test(v) ? v : null
}

export const inputCls =
  'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

export function Chk({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-zinc-300 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="rounded border-zinc-600 bg-zinc-900 text-emerald-500 focus:ring-0" />
      {label}
    </label>
  )
}

function VerdictBadge({ verdict, provisional }: { verdict?: IndemnityVerdict; provisional?: boolean }) {
  if (!verdict) return null
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded border ${VERDICT_TONE[verdict]}`}>
      {VERDICT_LABEL[verdict]}{provisional ? ' · provisional' : ''}
    </span>
  )
}

export function ContractsPanel({ contracts, catalog, reload, api, title = 'Contracts' }: {
  contracts: ContractRecord[]
  catalog: CoverageCatalogEntry[]
  reload: () => Promise<void>
  api: ContractsApi
  title?: string
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true); setErr(null)
    try {
      const rec = await api.upload(file)
      if (rec.status === 'error') setErr('Could not extract requirements — add them manually below.')
      await reload()
    } catch { setErr('Upload failed. Use a PDF under 15 MB.') } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between mb-1">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">{title}</h3>
        <div className="flex items-center gap-2">
          {api.create && (
            <button onClick={() => setAdding((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700"><Plus className="h-3.5 w-3.5" /> Add manually</button>
          )}
          <button onClick={() => fileRef.current?.click()} disabled={uploading} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-2.5 py-1.5 disabled:opacity-50">
            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Upload PDF
          </button>
          <input ref={fileRef} type="file" accept="application/pdf,.pdf" onChange={onFile} className="hidden" />
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">
        Upload a customer, vendor, lease, or subcontract PDF — we extract the insurance requirements and the
        indemnification clause for you to confirm. The source PDF is retained so every clause finding stays verifiable.
      </p>
      {err && <div className="text-[11px] text-amber-400 mb-2">{err}</div>}

      {adding && api.create && (
        <div className="mb-3">
          <ContractEditor catalog={catalog} api={api} onDone={async () => { setAdding(false); await reload() }} onCancel={() => setAdding(false)} />
        </div>
      )}

      {contracts.length === 0 && !adding ? (
        <p className="text-sm text-zinc-600">No contracts yet — upload one{api.create ? ' or add it manually' : ''}.</p>
      ) : (
        <div className="space-y-1">
          {contracts.map((c) => <ContractRow key={c.id} contract={c} catalog={catalog} reload={reload} api={api} />)}
        </div>
      )}

      <p className="text-[10px] text-zinc-600 mt-4 pt-3 border-t border-zinc-800/50">{DISCLAIMER}</p>
    </Card>
  )
}

function ContractRow({ contract, catalog, reload, api }: {
  contract: ContractRecord; catalog: CoverageCatalogEntry[]; reload: () => Promise<void>; api: ContractsApi
}) {
  const [editing, setEditing] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const labelFor = (k: string) => catalog.find((c) => c.key === k)?.label ?? k

  async function remove() {
    if (!api.remove) return
    setBusy(true)
    try { await api.remove(contract.id); await reload() } finally { setBusy(false) }
  }

  async function confirm() {
    setBusy(true)
    try { await api.confirm(contract.id); await reload() } finally { setBusy(false) }
  }

  async function openSource() {
    try {
      const { url } = await api.sourceUrl(contract.id)
      window.open(url, '_blank', 'noopener')
    } catch { /* no retained source — button is hidden unless has_source */ }
  }

  const ind = contract.indemnity
  return (
    <div className="border-b border-zinc-800/30 last:border-0 py-2">
      <div className="flex items-start gap-3">
        <FileText className="h-4 w-4 text-zinc-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200 flex items-center gap-2 flex-wrap">
            {contract.name}
            <span className="text-[10px] text-zinc-600 uppercase">{contract.status}{contract.ai_available ? ' · AI' : ''}</span>
            {contract.contract_type && <span className="text-[10px] text-zinc-500">{CONTRACT_TYPE_LABEL[contract.contract_type]}</span>}
            {(contract.project_state || contract.governing_state) && (
              <span className="text-[10px] text-zinc-500">{contract.project_state || contract.governing_state}</span>
            )}
            <VerdictBadge verdict={ind?.verdict} provisional={contract.provisional} />
          </div>
          {contract.requirements.length > 0 ? (
            <div className="text-[11px] text-zinc-500 mt-0.5">
              {contract.requirements.map((r, i) => (
                <span key={i} className="mr-3">{labelFor(r.line)}: {fmtMoney(r.per_occurrence)}{r.aggregate ? `/${fmtMoney(r.aggregate)}` : ''}</span>
              ))}
            </div>
          ) : <div className="text-[11px] text-zinc-600 mt-0.5">No requirements extracted — edit to add.</div>}
          {ind && ind.verdict !== 'insurable' && (
            <div className="text-[11px] text-zinc-400 mt-1 flex items-start gap-1.5">
              <ShieldAlert className="h-3.5 w-3.5 text-amber-400/80 mt-px shrink-0" />
              <span>{ind.basis}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={() => setShowReview((v) => !v)} className="text-xs text-zinc-400 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700">Review</button>
          <button onClick={() => setEditing((v) => !v)} className="text-xs text-zinc-400 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700">Edit</button>
          {contract.provisional && (
            <button onClick={confirm} disabled={busy} className="text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded-lg border border-emerald-700/50 disabled:opacity-50">Confirm</button>
          )}
          {contract.has_source && (
            <button onClick={openSource} title="Open the source PDF" className="text-zinc-500 hover:text-zinc-200 p-1"><ExternalLink className="h-4 w-4" /></button>
          )}
          {api.remove && (
            <button onClick={remove} disabled={busy} className="text-zinc-500 hover:text-red-400 p-1"><Trash2 className="h-4 w-4" /></button>
          )}
        </div>
      </div>
      {showReview && <ContractReviewPanel contractId={contract.id} name={contract.name} api={api} />}
      {editing && (
        <div className="mt-2">
          <ContractEditor catalog={catalog} existing={contract} api={api} onDone={async () => { setEditing(false); await reload() }} onCancel={() => setEditing(false)} />
        </div>
      )}
    </div>
  )
}

function ContractReviewPanel({ contractId, name, api }: { contractId: string; name: string; api: ContractsApi }) {
  const [review, setReview] = useState<ContractReview | null>(null)
  const [failed, setFailed] = useState(false)
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    let live = true
    api.review(contractId).then((r) => { if (live) setReview(r) }).catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [contractId])

  async function download() {
    setDownloading(true)
    try { await api.reviewPdf(contractId, name) } finally { setDownloading(false) }
  }

  if (failed) return <p className="mt-2 text-[11px] text-zinc-600">Could not load this contract's review.</p>
  if (!review) return <div className="mt-2 flex items-center gap-2 text-[11px] text-zinc-600"><Loader2 className="h-3 w-3 animate-spin" /> Building review…</div>

  const clause = review.risk_transfer?.indemnity
  return (
    <div className="mt-2 bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 space-y-3">
      {review.provisional && (
        <div className="text-[10px] font-medium text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2 py-1">
          PROVISIONAL — the extracted terms have not been confirmed by a reviewer.
        </div>
      )}
      <div className="flex items-center gap-3 flex-wrap">
        <Stat label="Exposed" value={review.summary.exposed} tone={review.summary.exposed ? 'text-red-400' : 'text-emerald-400'} />
        <Stat label="Compliant" value={review.summary.compliant} tone="text-zinc-200" />
        <Stat label="Endorsement gaps" value={review.summary.endorsement_gaps} tone={review.summary.endorsement_gaps ? 'text-amber-400' : 'text-zinc-200'} />
        <div className="ml-auto">
          <button onClick={download} disabled={downloading} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700 disabled:opacity-50">
            {downloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />} Review PDF
          </button>
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Indemnification</span>
          <VerdictBadge verdict={review.indemnity.verdict} />
        </div>
        <p className="text-[11px] text-zinc-400">{review.indemnity.basis}</p>
        {review.indemnity.statute && (
          <p className="text-[10px] text-zinc-600 mt-0.5">
            {review.indemnity.statute}{review.indemnity.controlling_state ? ` · ${review.indemnity.controlling_state}` : ''}
          </p>
        )}
        {clause?.quote && (
          <blockquote className="mt-2 border-l-2 border-zinc-700 pl-2.5 text-[11px] text-zinc-400 italic">
            “{clause.quote}”{clause.page ? <span className="not-italic text-zinc-600"> (p. {clause.page})</span> : null}
          </blockquote>
        )}
      </div>

      {review.actions.length > 0 && (
        <div>
          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Actions</span>
          <ol className="mt-1 space-y-1 list-decimal list-inside">
            {review.actions.map((a, i) => <li key={i} className="text-[11px] text-zinc-400">{a}</li>)}
          </ol>
        </div>
      )}

      <p className="text-[10px] text-zinc-600 pt-1 border-t border-zinc-800/50">{review.disclaimer}</p>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className={`text-base font-light tabular-nums ${tone}`}>{value}</span>
      <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</span>
    </div>
  )
}

function emptyReq(): ContractRequirement {
  return {
    line: 'gl', per_occurrence: null, aggregate: null, additional_insured: false,
    waiver_of_subrogation: false, primary_noncontributory: false, note: null, quote: null, page: null,
  }
}

function ContractEditor({ catalog, existing, api, onDone, onCancel }: {
  catalog: CoverageCatalogEntry[]; existing?: ContractRecord; api: ContractsApi
  onDone: () => Promise<void>; onCancel: () => void
}) {
  const [name, setName] = useState(existing?.name ?? '')
  const [counterparty, setCounterparty] = useState(existing?.counterparty ?? '')
  const [contractType, setContractType] = useState<ContractType | ''>(existing?.contract_type ?? '')
  const [governingState, setGoverningState] = useState(existing?.governing_state ?? '')
  const [projectState, setProjectState] = useState(existing?.project_state ?? '')
  const [reqs, setReqs] = useState<ContractRequirement[]>(existing?.requirements?.length ? existing.requirements : [emptyReq()])
  const originalInd = existing?.risk_transfer?.indemnity ?? EMPTY_INDEMNITY
  const [ind, setInd] = useState<Indemnity>(originalInd)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  function patch(i: number, p: Partial<ContractRequirement>) {
    setReqs((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...p } : r)))
  }
  function patchInd(p: Partial<Indemnity>) { setInd((v) => ({ ...v, ...p })) }

  async function save() {
    if (!name.trim()) return
    setBusy(true); setErr(null)
    try {
      const cleaned = reqs.filter((r) => r.line)
      const type = contractType || null
      const gov = normState(governingState)
      const proj = normState(projectState)
      const clause: RiskTransfer = { indemnity: ind }
      const indChanged = JSON.stringify(ind) !== JSON.stringify(originalInd)

      if (existing) {
        // PUT is a true PATCH: an unsent field is left alone, and the server
        // un-confirms the contract when a *verdict input* changes value. Sending
        // an unchanged contract_type would strip the confirmation off a renamed
        // contract, so only ship what the user actually edited.
        const payload: ContractPayload = {}
        if (name !== existing.name) payload.name = name
        if ((counterparty || null) !== (existing.counterparty ?? null)) payload.counterparty = counterparty || null
        if (JSON.stringify(cleaned) !== JSON.stringify(existing.requirements)) payload.requirements = cleaned
        if (type !== (existing.contract_type ?? null)) payload.contract_type = type
        if (gov !== (existing.governing_state ?? null)) payload.governing_state = gov
        if (proj !== (existing.project_state ?? null)) payload.project_state = proj
        if (indChanged) payload.risk_transfer = clause
        await api.update(existing.id, payload)
      } else if (api.create) {
        await api.create({
          name, counterparty: counterparty || null, requirements: cleaned,
          contract_type: type, governing_state: gov, project_state: proj,
          ...(ind.present ? { risk_transfer: clause } : {}),
        })
      }
      await onDone()
    } catch {
      setErr('Could not save this contract. Check the state codes (two letters) and try again.')
    } finally { setBusy(false) }
  }

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Field label="Contract name"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme MSA" className={inputCls} /></Field>
        <Field label="Counterparty"><input value={counterparty} onChange={(e) => setCounterparty(e.target.value)} placeholder="Acme Corp" className={inputCls} /></Field>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Field label="Contract type">
          <select value={contractType} onChange={(e) => setContractType(e.target.value as ContractType | '')} className={inputCls}>
            <option value="">—</option>
            {CONTRACT_TYPES.map((t) => <option key={t} value={t}>{CONTRACT_TYPE_LABEL[t]}</option>)}
          </select>
        </Field>
        <Field label="Governing law (state)">
          <input value={governingState} maxLength={2} onChange={(e) => setGoverningState(e.target.value)} placeholder="NY" className={inputCls} />
        </Field>
        <Field label="Project / premises state">
          <input value={projectState} maxLength={2} onChange={(e) => setProjectState(e.target.value)} placeholder="NY" className={inputCls} />
        </Field>
      </div>
      <p className="text-[10px] text-zinc-600 -mt-1">
        For construction contracts the project state controls — most anti-indemnity statutes attach to where the
        work is performed, regardless of the contract's chosen law.
      </p>

      <div className="border-t border-zinc-800 pt-2 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">Indemnification clause</span>
          <Chk checked={ind.present} onChange={(v) => patchInd({ present: v })} label="Contract has one" />
        </div>
        {ind.present && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Form">
                <select value={ind.form} onChange={(e) => patchInd({ form: e.target.value as IndemnityForm })} className={inputCls}>
                  {FORMS.map((f) => <option key={f} value={f}>{INDEMNITY_FORM_LABEL[f]}</option>)}
                </select>
              </Field>
              <Field label="Direction">
                <select value={ind.direction} onChange={(e) => patchInd({ direction: e.target.value as IndemnityDirection })} className={inputCls}>
                  {DIRECTIONS.map((d) => <option key={d} value={d}>{INDEMNITY_DIRECTION_LABEL[d]}</option>)}
                </select>
              </Field>
            </div>
            <div className="flex flex-wrap gap-3">
              <Chk checked={ind.covers_sole_negligence} onChange={(v) => patchInd({ covers_sole_negligence: v })} label="Covers their sole negligence" />
              <Chk checked={ind.defense_obligation} onChange={(v) => patchInd({ defense_obligation: v })} label="Duty to defend" />
            </div>
            {ind.quote && (
              <blockquote className="border-l-2 border-zinc-700 pl-2.5 text-[11px] text-zinc-500 italic">
                “{ind.quote}”{ind.page ? <span className="not-italic text-zinc-600"> (p. {ind.page})</span> : null}
              </blockquote>
            )}
          </>
        )}
      </div>

      <div className="space-y-2">
        {reqs.map((r, i) => (
          <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-lg p-2 space-y-2">
            <div className="flex items-center gap-2">
              <select value={r.line} onChange={(e) => patch(i, { line: e.target.value })} className={`${inputCls} flex-1`}>
                {catalog.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select>
              <input value={r.per_occurrence ?? ''} onChange={(e) => patch(i, { per_occurrence: parseMoney(e.target.value) })} placeholder="per-occ $" className={`${inputCls} w-28`} />
              <input value={r.aggregate ?? ''} onChange={(e) => patch(i, { aggregate: parseMoney(e.target.value) })} placeholder="agg $" className={`${inputCls} w-28`} />
              <button onClick={() => setReqs((rs) => rs.filter((_, idx) => idx !== i))} className="text-zinc-500 hover:text-red-400 p-1"><Trash2 className="h-4 w-4" /></button>
            </div>
            <div className="flex flex-wrap gap-3">
              {ENDORSEMENTS.map((e) => (
                <Chk key={e.key} checked={Boolean(r[e.key])} onChange={(v) => patch(i, { [e.key]: v } as Partial<ContractRequirement>)} label={e.label} />
              ))}
            </div>
          </div>
        ))}
        <button onClick={() => setReqs((rs) => [...rs, emptyReq()])} className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100"><Plus className="h-3.5 w-3.5" /> Add requirement</button>
      </div>

      {err && <div className="text-[11px] text-amber-400">{err}</div>}

      <div className="flex items-center gap-2 pt-1">
        <button onClick={save} disabled={busy || !name.trim()} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save
        </button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}
