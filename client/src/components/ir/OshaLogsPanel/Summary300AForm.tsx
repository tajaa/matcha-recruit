import { Loader2, Save } from 'lucide-react'
import { Button } from '../../ui'
import type { Summary300A } from './types'

interface Summary300AFormProps {
  summary: Summary300A | null
  hours: string
  setHours: (v: string) => void
  avgEmp: string
  setAvgEmp: (v: string) => void
  certBy: string
  setCertBy: (v: string) => void
  certTitle: string
  setCertTitle: (v: string) => void
  certDate: string
  setCertDate: (v: string) => void
  save300a: () => void
  saving: boolean
  saveMsg: string | null
}

// 300A establishment / hours / certification
export function Summary300AForm({
  summary,
  hours,
  setHours,
  avgEmp,
  setAvgEmp,
  certBy,
  setCertBy,
  certTitle,
  setCertTitle,
  certDate,
  setCertDate,
  save300a,
  saving,
  saveMsg,
}: Summary300AFormProps) {
  if (!summary) return null
  return (
    <div className="bg-zinc-900/40 border border-white/[0.06] rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
            300A Establishment Data
          </span>
          <span className="text-[13px] text-zinc-200 font-medium mt-0.5">
            {summary.establishment_name || 'Unnamed establishment'}
            {summary.city && (
              <span className="text-zinc-500 font-normal"> · {summary.city}, {summary.state}</span>
            )}
          </span>
        </div>
        <span className="text-[11px] text-zinc-600">
          EIN {summary.ein || '—'} · NAICS {summary.naics || '—'}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label className="block">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
            Total Hours Worked
          </span>
          <input
            type="number"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            placeholder="e.g. 410000"
            className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2 font-mono"
          />
          <span className="text-[10px] text-zinc-600 mt-1 block">
            Manual entry — HRIS does not provide hours worked.
          </span>
        </label>
        <label className="block">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
            Avg. Employees
          </span>
          <input
            type="number"
            value={avgEmp}
            onChange={(e) => setAvgEmp(e.target.value)}
            className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2 font-mono"
          />
          <span className="text-[10px] text-zinc-600 mt-1 block">
            Auto-counted from the active roster (incl. HRIS/Finch-synced employees); override if needed.
          </span>
        </label>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <label className="block">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Certified By</span>
          <input
            value={certBy}
            onChange={(e) => setCertBy(e.target.value)}
            className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2"
          />
        </label>
        <label className="block">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Title</span>
          <input
            value={certTitle}
            onChange={(e) => setCertTitle(e.target.value)}
            className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2"
          />
        </label>
        <label className="block">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Date</span>
          <input
            type="date"
            value={certDate}
            onChange={(e) => setCertDate(e.target.value)}
            className="mt-1.5 w-full bg-zinc-950 border border-white/10 rounded-lg text-zinc-200 text-sm px-3 py-2"
          />
        </label>
      </div>
      <div className="flex items-center gap-3">
        <Button size="sm" onClick={save300a} disabled={saving}>
          {saving ? <Loader2 size={12} className="mr-1.5 animate-spin" /> : <Save size={12} className="mr-1.5" />}
          Save 300A
        </Button>
        {saveMsg && <span className="text-[12px] text-zinc-400">{saveMsg}</span>}
      </div>
    </div>
  )
}
