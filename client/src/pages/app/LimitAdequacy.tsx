import { useEffect, useMemo, useRef, useState } from 'react'
import { Scale, FileDown, Loader2, Upload, Plus, Trash2, ChevronDown, Check, AlertTriangle, FileText } from 'lucide-react'
import { Card } from '../../components/ui'
import {
  fetchLimitReview, fetchCoverage, upsertCoverage, deleteCoverage,
  uploadContract, createContract, updateContract, deleteContract, downloadReviewPdf,
} from '../../api/limitAdequacy'
import type {
  LimitReview, CoverageList, CoverageRow, ReviewLine, ContractRecord, ContractRequirement, CoverageCatalogEntry,
} from '../../types/limitAdequacy'
import { LIMIT_STATUS_TONE, LIMIT_STATUS_LABEL, fmtMoney } from '../../types/limitAdequacy'

const ENDORSEMENTS: { key: keyof ContractRequirement; label: string }[] = [
  { key: 'additional_insured', label: 'Additional insured' },
  { key: 'waiver_of_subrogation', label: 'Waiver of subrogation' },
  { key: 'primary_noncontributory', label: 'Primary & non-contributory' },
]

function parseMoney(s: string): number | null {
  const v = parseFloat(s.replace(/[$,\s]/g, ''))
  return Number.isFinite(v) ? v : null
}

export default function LimitAdequacy() {
  const [review, setReview] = useState<LimitReview | null>(null)
  const [coverage, setCoverage] = useState<CoverageList | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  async function reloadAll() {
    const [r, c] = await Promise.all([fetchLimitReview(), fetchCoverage()])
    setReview(r); setCoverage(c)
  }
  useEffect(() => { reloadAll().finally(() => setLoading(false)) }, [])

  async function download() {
    setDownloading(true)
    try { await downloadReviewPdf() } finally { setDownloading(false) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (!review || !coverage) return <p className="text-sm text-zinc-500">Unable to load limit-adequacy review.</p>

  const s = review.summary
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <Scale className="h-5 w-5 text-zinc-400" /> Limit Adequacy &amp; Contract Review
          </h1>
          <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Record what you carry, upload the contracts that impose insurance requirements, and we diff them — so you find "you carry $1M but a contract requires $2M" before a customer (or underwriter) does.</p>
        </div>
        <button onClick={download} disabled={downloading} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50 shrink-0">
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Review PDF
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
        <Stat label="Contract shortfalls" value={s.contract_shortfalls} tone={s.contract_shortfalls ? 'text-red-400' : 'text-emerald-400'} />
        <Stat label="Below baseline" value={s.baseline_lows} tone={s.baseline_lows ? 'text-amber-400' : 'text-zinc-200'} />
        <Stat label="Lines carried" value={s.lines_carried} tone="text-zinc-200" />
        <Stat label="Contracts" value={s.contracts} tone="text-zinc-200" />
      </div>

      <AdequacyTable lines={review.lines} />
      <CoverageEditor coverage={coverage} reload={reloadAll} />
      <ContractsCard contracts={review.contracts} catalog={coverage.catalog} reload={reloadAll} />
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone: string }) {
  return (
    <div className="bg-zinc-900 px-4 py-4">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{label}</div>
      <div className={`text-2xl font-light font-mono mt-1.5 ${tone}`}>{value}</div>
    </div>
  )
}

/* ──────────────────────── Adequacy table (read view) ──────────────────────── */

function AdequacyTable({ lines }: { lines: ReviewLine[] }) {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-1">Coverage line adequacy</h3>
      <p className="text-[11px] text-zinc-500 mb-3">Carried vs. the highest contract requirement vs. a directional size/venue baseline. Contract shortfalls are hard gaps; baseline is a starting point, not a quote.</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-zinc-600 uppercase tracking-wide border-b border-zinc-800">
              <th className="text-left font-medium py-1.5 pr-2">Line</th>
              <th className="text-right font-medium px-2">Carried</th>
              <th className="text-right font-medium px-2">Contract req.</th>
              <th className="text-right font-medium px-2">Baseline</th>
              <th className="text-left font-medium px-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => {
              const c = l.carried
              const carried = c ? fmtMoney(c.per_occurrence) + (c.aggregate ? ` / ${fmtMoney(c.aggregate)}` : '') : '—'
              const req = l.contract_required
              const reqS = req ? fmtMoney(req.per_occurrence) + (req.aggregate ? ` / ${fmtMoney(req.aggregate)}` : '') : '—'
              return (
                <tr key={l.key} className="border-b border-zinc-800/30 align-top">
                  <td className="py-2 pr-2 text-zinc-200">{l.label}</td>
                  <td className="px-2 text-right font-mono text-zinc-300">{carried}</td>
                  <td className="px-2 text-right font-mono text-zinc-300">{reqS}</td>
                  <td className="px-2 text-right font-mono text-zinc-500">{l.baseline ? fmtMoney(l.baseline.per_occurrence) : '—'}</td>
                  <td className="px-2">
                    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${LIMIT_STATUS_TONE[l.status]}`}>{LIMIT_STATUS_LABEL[l.status]}</span>
                    {l.gap && <div className="text-[11px] text-amber-400/80 mt-1">{l.gap}</div>}
                    {l.endorsement_gaps.length > 0 && (
                      <div className="text-[11px] text-zinc-500 mt-1 flex items-start gap-1">
                        <AlertTriangle className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" />
                        <span>Confirm endorsement{l.endorsement_gaps.length > 1 ? 's' : ''}: {l.endorsement_gaps.map((e) => e.label).join(', ')}</span>
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

/* ──────────────────────── Carried-coverage editor ──────────────────────── */

function CoverageEditor({ coverage, reload }: { coverage: CoverageList; reload: () => Promise<void> }) {
  const byLine = useMemo(() => Object.fromEntries(coverage.lines.map((l) => [l.line, l])), [coverage.lines])
  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-1">Your coverage</h3>
      <p className="text-[11px] text-zinc-500 mb-3">Enter the limits you carry per line. Used to diff against contract requirements above.</p>
      <div className="space-y-1">
        {coverage.catalog.map((cat) => (
          <CoverageLineRow key={cat.key} cat={cat} row={byLine[cat.key]} reload={reload} />
        ))}
      </div>
    </Card>
  )
}

function CoverageLineRow({ cat, row, reload }: { cat: CoverageCatalogEntry; row?: CoverageRow; reload: () => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [carrier, setCarrier] = useState(row?.carrier ?? '')
  const [perOcc, setPerOcc] = useState(row?.per_occurrence != null ? String(row.per_occurrence) : '')
  const [agg, setAgg] = useState(row?.aggregate != null ? String(row.aggregate) : '')
  const [retention, setRetention] = useState(row?.retention != null ? String(row.retention) : '')
  const [expiry, setExpiry] = useState(row?.expiry_date ?? '')
  const [ai, setAi] = useState(row?.additional_insured ?? false)
  const [wos, setWos] = useState(row?.waiver_of_subrogation ?? false)
  const [pnc, setPnc] = useState(row?.primary_noncontributory ?? false)
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    try {
      await upsertCoverage(cat.key, {
        carrier: carrier || null, per_occurrence: parseMoney(perOcc), aggregate: parseMoney(agg),
        retention: parseMoney(retention), expiry_date: expiry || null,
        additional_insured: ai, waiver_of_subrogation: wos, primary_noncontributory: pnc,
      })
      await reload(); setOpen(false)
    } finally { setBusy(false) }
  }
  async function clear() {
    setBusy(true)
    try { await deleteCoverage(cat.key); await reload(); setOpen(false) } finally { setBusy(false) }
  }

  const summary = row ? fmtMoney(row.per_occurrence) + (row.aggregate ? ` / ${fmtMoney(row.aggregate)}` : '') + (row.carrier ? ` · ${row.carrier}` : '') : 'Not entered'
  return (
    <div className="border-b border-zinc-800/30 last:border-0">
      <div className="flex items-center gap-3 py-2">
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200">{cat.label}</div>
          <div className={`text-[11px] truncate ${row ? 'text-zinc-400' : 'text-zinc-600'}`}>{summary}</div>
        </div>
        <button onClick={() => setOpen((v) => !v)} className="text-zinc-500 hover:text-zinc-200 p-1 shrink-0">
          <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>
      {open && (
        <div className="pb-3 px-1 space-y-2">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            <Field label="Per occurrence ($)"><input value={perOcc} onChange={(e) => setPerOcc(e.target.value)} placeholder="1000000" className={inputCls} /></Field>
            <Field label="Aggregate ($)"><input value={agg} onChange={(e) => setAgg(e.target.value)} placeholder="2000000" className={inputCls} /></Field>
            <Field label="Retention / deductible ($)"><input value={retention} onChange={(e) => setRetention(e.target.value)} placeholder="0" className={inputCls} /></Field>
            <Field label="Carrier"><input value={carrier} onChange={(e) => setCarrier(e.target.value)} className={inputCls} /></Field>
            <Field label="Expiry date"><input type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} className={inputCls} /></Field>
          </div>
          {cat.endorsements && (
            <div className="flex flex-wrap gap-3 pt-1">
              <Chk checked={ai} onChange={setAi} label="Additional insured" />
              <Chk checked={wos} onChange={setWos} label="Waiver of subrogation" />
              <Chk checked={pnc} onChange={setPnc} label="Primary & non-contributory" />
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            <button onClick={save} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">
              <Check className="h-3.5 w-3.5" /> Save
            </button>
            {row && <button onClick={clear} disabled={busy} className="inline-flex items-center gap-1 text-xs text-red-400 hover:text-red-300 px-3 py-1.5 rounded-lg border border-zinc-700"><Trash2 className="h-3.5 w-3.5" /> Clear</button>}
          </div>
        </div>
      )}
    </div>
  )
}

/* ──────────────────────────── Contracts ──────────────────────────── */

function ContractsCard({ contracts, catalog, reload }: { contracts: ContractRecord[]; catalog: CoverageCatalogEntry[]; reload: () => Promise<void> }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true); setErr(null)
    try {
      const rec = await uploadContract(file)
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
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Contracts</h3>
        <div className="flex items-center gap-2">
          <button onClick={() => setAdding((v) => !v)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-zinc-100 px-2.5 py-1.5 rounded-lg border border-zinc-700"><Plus className="h-3.5 w-3.5" /> Add manually</button>
          <button onClick={() => fileRef.current?.click()} disabled={uploading} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-2.5 py-1.5 disabled:opacity-50">
            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} Upload PDF
          </button>
          <input ref={fileRef} type="file" accept="application/pdf,.pdf" onChange={onFile} className="hidden" />
        </div>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">Upload a customer/vendor/lease contract — we extract the insurance requirements for you to confirm. The PDF isn't stored, only the extracted requirements.</p>
      {err && <div className="text-[11px] text-amber-400 mb-2">{err}</div>}

      {adding && (
        <div className="mb-3">
          <ContractEditor catalog={catalog} onDone={async () => { setAdding(false); await reload() }} onCancel={() => setAdding(false)} />
        </div>
      )}

      {contracts.length === 0 && !adding ? (
        <p className="text-sm text-zinc-600">No contracts yet — upload one or add it manually.</p>
      ) : (
        <div className="space-y-1">
          {contracts.map((c) => <ContractRow key={c.id} contract={c} catalog={catalog} reload={reload} />)}
        </div>
      )}
    </Card>
  )
}

function ContractRow({ contract, catalog, reload }: { contract: ContractRecord; catalog: CoverageCatalogEntry[]; reload: () => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const labelFor = (k: string) => catalog.find((c) => c.key === k)?.label ?? k

  async function remove() {
    setBusy(true)
    try { await deleteContract(contract.id); await reload() } finally { setBusy(false) }
  }

  return (
    <div className="border-b border-zinc-800/30 last:border-0 py-2">
      <div className="flex items-start gap-3">
        <FileText className="h-4 w-4 text-zinc-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200 flex items-center gap-2">
            {contract.name}
            <span className="text-[10px] text-zinc-600 uppercase">{contract.status}{contract.ai_available ? ' · AI' : ''}</span>
          </div>
          {contract.requirements.length > 0 ? (
            <div className="text-[11px] text-zinc-500 mt-0.5">
              {contract.requirements.map((r, i) => (
                <span key={i} className="mr-3">{labelFor(r.line)}: {fmtMoney(r.per_occurrence)}{r.aggregate ? `/${fmtMoney(r.aggregate)}` : ''}</span>
              ))}
            </div>
          ) : <div className="text-[11px] text-zinc-600 mt-0.5">No requirements extracted — edit to add.</div>}
        </div>
        <button onClick={() => setEditing((v) => !v)} className="text-xs text-zinc-400 hover:text-zinc-100 px-2 py-1 rounded-lg border border-zinc-700 shrink-0">Edit</button>
        <button onClick={remove} disabled={busy} className="text-zinc-500 hover:text-red-400 p-1 shrink-0"><Trash2 className="h-4 w-4" /></button>
      </div>
      {editing && (
        <div className="mt-2">
          <ContractEditor catalog={catalog} existing={contract} onDone={async () => { setEditing(false); await reload() }} onCancel={() => setEditing(false)} />
        </div>
      )}
    </div>
  )
}

function emptyReq(): ContractRequirement {
  return { line: 'gl', per_occurrence: null, aggregate: null, additional_insured: false, waiver_of_subrogation: false, primary_noncontributory: false, note: null }
}

function ContractEditor({ catalog, existing, onDone, onCancel }: {
  catalog: CoverageCatalogEntry[]; existing?: ContractRecord; onDone: () => Promise<void>; onCancel: () => void
}) {
  const [name, setName] = useState(existing?.name ?? '')
  const [counterparty, setCounterparty] = useState(existing?.counterparty ?? '')
  const [reqs, setReqs] = useState<ContractRequirement[]>(existing?.requirements?.length ? existing.requirements : [emptyReq()])
  const [busy, setBusy] = useState(false)

  function patch(i: number, p: Partial<ContractRequirement>) {
    setReqs((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...p } : r)))
  }

  async function save() {
    if (!name.trim()) return
    setBusy(true)
    try {
      const cleaned = reqs.filter((r) => r.line)
      if (existing) await updateContract(existing.id, { name, counterparty: counterparty || null, requirements: cleaned })
      else await createContract({ name, counterparty: counterparty || null, requirements: cleaned })
      await onDone()
    } finally { setBusy(false) }
  }

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <Field label="Contract name"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme MSA" className={inputCls} /></Field>
        <Field label="Counterparty"><input value={counterparty} onChange={(e) => setCounterparty(e.target.value)} placeholder="Acme Corp" className={inputCls} /></Field>
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
      <div className="flex items-center gap-2 pt-1">
        <button onClick={save} disabled={busy || !name.trim()} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save
        </button>
        <button onClick={onCancel} className="text-xs text-zinc-400 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Cancel</button>
      </div>
    </div>
  )
}

/* ──────────────────────────── small bits ──────────────────────────── */

const inputCls = 'bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 w-full'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

function Chk({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-zinc-300 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="rounded border-zinc-600 bg-zinc-900 text-emerald-500 focus:ring-0" />
      {label}
    </label>
  )
}
