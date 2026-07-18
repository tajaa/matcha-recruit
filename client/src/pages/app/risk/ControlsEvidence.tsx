import { useEffect, useState } from 'react'
import { ShieldCheck, FileDown, Loader2, Check, ChevronDown } from 'lucide-react'
import { Card } from '../../../components/ui'
import { fetchControlsRegister, updateControl, downloadControlsPacket } from '../../../api/risk/controlsEvidence'
import type { ControlsRegister, ControlEntry, ControlStatus } from '../../../types/controlsEvidence'

const STATUS_TONE: Record<ControlStatus, string> = {
  strong: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  partial: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  gap: 'text-red-400 bg-red-500/10 border-red-500/20',
  na: 'text-zinc-500 bg-white/5 border-white/10',
}
const STATUS_LABEL: Record<ControlStatus, string> = { strong: 'Strong', partial: 'Partial', gap: 'Gap', na: 'N/A' }

export default function ControlsEvidence() {
  const [reg, setReg] = useState<ControlsRegister | null>(null)
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  function load() {
    setLoading(true)
    fetchControlsRegister().then(setReg).finally(() => setLoading(false))
  }
  useEffect(load, [])

  async function download() {
    setDownloading(true)
    try { await downloadControlsPacket() } finally { setDownloading(false) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (!reg) return <p className="text-sm text-zinc-500">Unable to load controls register.</p>

  const s = reg.summary
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-zinc-400" /> Proof of Controls
          </h1>
          <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Your risk-management controls, auto-compiled from your HR, safety, training, discipline, and compliance records. Verify each and export one underwriter-ready packet — documented controls buy down rate at renewal.</p>
        </div>
        <button onClick={download} disabled={downloading} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50 shrink-0">
          {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Proof-of-Controls packet
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
        <Stat label="Strong" value={s.strong} tone="text-emerald-400" />
        <Stat label="Partial" value={s.partial} tone="text-amber-400" />
        <Stat label="Gap" value={s.gap} tone="text-red-400" />
        <Stat label="Verified" value={`${s.verified}/${s.total}`} tone="text-zinc-200" />
      </div>

      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-1">Risk controls</h3>
        <p className="text-[11px] text-zinc-500 mb-3">Each control is auto-derived from your data. Add a verification note or override the status where you have evidence on file.</p>
        <div className="space-y-1">
          {reg.controls.map((c) => <ControlRow key={c.key} control={c} reload={load} />)}
        </div>
      </Card>
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

function ControlRow({ control, reload }: { control: ControlEntry; reload: () => void }) {
  const [open, setOpen] = useState(false)
  // Seed from the stored override (not '') so saving a note doesn't wipe a prior
  // override back to auto. Pick "(auto)" to explicitly clear the override.
  const [status, setStatus] = useState<ControlStatus | ''>(control.override_status ?? '')
  const [note, setNote] = useState(control.note ?? '')
  const [busy, setBusy] = useState(false)

  async function save(verify: boolean) {
    setBusy(true)
    try {
      await updateControl(control.key, { status: status || null, note: note || null, verified: verify })
      setOpen(false); reload()
    } finally { setBusy(false) }
  }

  return (
    <div className="border-b border-zinc-800/30 last:border-0">
      <div className="flex items-center gap-3 py-2">
        <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase shrink-0 ${STATUS_TONE[control.status]}`}>{STATUS_LABEL[control.status]}</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-zinc-200">
            {control.label}
            {control.verified && <span className="ml-2 inline-flex items-center gap-1 text-[10px] text-emerald-400"><Check className="h-3 w-3" /> verified</span>}
          </div>
          <div className="text-[11px] text-zinc-500 truncate">{control.detail || control.metric || '—'}</div>
        </div>
        <button onClick={() => setOpen((v) => !v)} className="text-zinc-500 hover:text-zinc-200 p-1 shrink-0">
          <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>
      {open && (
        <div className="pb-3 px-1 space-y-2">
          <div className="flex items-center gap-2">
            <label className="text-[10px] text-zinc-500 uppercase">Override status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value as ControlStatus | '')}
              className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500">
              <option value="">(auto: {STATUS_LABEL[control.status]})</option>
              <option value="strong">Strong</option>
              <option value="partial">Partial</option>
              <option value="gap">Gap</option>
              <option value="na">N/A</option>
            </select>
          </div>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
            placeholder="Verification note (e.g. evidence location, reviewer, date)"
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500" />
          <div className="flex items-center gap-2">
            <button onClick={() => save(true)} disabled={busy} className="inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg px-3 py-1.5 disabled:opacity-50">
              <Check className="h-3.5 w-3.5" /> Mark verified
            </button>
            <button onClick={() => save(false)} disabled={busy} className="text-xs text-zinc-300 hover:text-zinc-100 px-3 py-1.5 rounded-lg border border-zinc-700">Save note</button>
          </div>
        </div>
      )}
    </div>
  )
}
