import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { useToast } from '../ui'
import {
  fetchMealBreakWaiver,
  updateMealBreakWaiver,
} from '../../api/employees/employeeSchedule'
import type { MealBreakWaiverAttestation } from '../../types/employeeSchedule'

function today() {
  return new Date().toISOString().slice(0, 10)
}

export function MealBreakWaiverPanel({ employeeId }: { employeeId: string }) {
  const { toast } = useToast()
  const [waiver, setWaiver] = useState<MealBreakWaiverAttestation | null>(null)
  const [onFile, setOnFile] = useState(false)
  const [effectiveFrom, setEffectiveFrom] = useState(today())
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    fetchMealBreakWaiver(employeeId)
      .then((next) => {
        if (!active) return
        setWaiver(next)
        setOnFile(next.on_file)
        setEffectiveFrom(next.effective_from ?? today())
        setNote(next.note ?? '')
      })
      .catch(() => {
        if (active) toast('Could not load meal-break waiver status', 'error')
      })
    return () => { active = false }
  }, [employeeId, toast])

  async function save() {
    setSaving(true)
    try {
      const next = await updateMealBreakWaiver(employeeId, {
        on_file: onFile,
        effective_from: effectiveFrom || null,
        note: note.trim() || null,
      })
      setWaiver(next)
      toast('Meal-break waiver status saved', 'success')
    } catch {
      toast('Could not save meal-break waiver status', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <h3 className="text-sm font-medium text-zinc-200">Meal-break waiver</h3>
      <p className="mt-1 text-xs text-zinc-500">Record whether a waiver is on file. Jurisdictional break rules still decide whether it applies.</p>
      <label className="mt-3 flex items-center gap-2 text-sm text-zinc-300">
        <input type="checkbox" checked={onFile} onChange={(event) => setOnFile(event.target.checked)} className="rounded border-zinc-600 bg-zinc-950" />
        Waiver is on file
      </label>
      <label className="mt-3 block text-[10px] font-medium uppercase tracking-wide text-zinc-500">
        Effective from
        <input type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-2 text-sm text-zinc-200" />
      </label>
      <label className="mt-3 block text-[10px] font-medium uppercase tracking-wide text-zinc-500">
        Manager note
        <textarea rows={2} value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-2 text-sm text-zinc-200" />
      </label>
      {waiver?.attested && waiver.confirmed_at && <p className="mt-2 text-[11px] text-zinc-500">Last confirmed {new Date(waiver.confirmed_at).toLocaleDateString()}.</p>}
      <button onClick={save} disabled={saving} className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-50">
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Save waiver
      </button>
    </section>
  )
}
