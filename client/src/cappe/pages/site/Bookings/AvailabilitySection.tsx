import type { Dispatch, SetStateAction } from 'react'
import { Loader2, Trash2, Save } from 'lucide-react'
import { WEEKDAYS } from '../../../components/SurfaceShell'
import type { CappeBookingType, CappeAvailabilitySlot, CappeStaff } from '../../../types'
import { unavailableStaffWindowIndexes } from '../../../utils/bookingAvailability'
import { hhmm, inputCls } from './constants'

interface AvailabilitySectionProps {
  slots: CappeAvailabilitySlot[]
  setSlots: Dispatch<SetStateAction<CappeAvailabilitySlot[]>>
  setSlot: (i: number, patch: Partial<CappeAvailabilitySlot>) => void
  types: CappeBookingType[]
  staff: CappeStaff[]
  addSlot: () => void
  saveAvailability: () => void
  savingAvail: boolean
  /** A shared (all-locations) row shown inside a location's view: read-only. */
  isShared?: (row: CappeAvailabilitySlot) => boolean
}

export function AvailabilitySection({
  slots, setSlots, setSlot, types, staff, addSlot, saveAvailability, savingAvail, isShared = () => false,
}: AvailabilitySectionProps) {
  const unavailableIndexes = unavailableStaffWindowIndexes(slots, types)

  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-zinc-100">Weekly availability</h2>
      <p className="mb-3 text-xs text-zinc-500">Staff-specific hours are public only for appointment types assigned to that staff member.</p>
      <div className="space-y-2">
        {slots.map((s, i) => {
          const locked = isShared(s)
          return (
          <fieldset key={i} disabled={locked} className={`flex flex-wrap items-center gap-2 ${locked ? 'opacity-60' : ''}`}>
            <select value={s.weekday} onChange={(e) => setSlot(i, { weekday: parseInt(e.target.value, 10) })} className={inputCls}>
              {WEEKDAYS.map((d, idx) => <option key={idx} value={idx}>{d}</option>)}
            </select>
            <input type="time" value={hhmm(s.start_time)} onChange={(e) => setSlot(i, { start_time: e.target.value })} className={inputCls} />
            <span className="text-zinc-400">to</span>
            <input type="time" value={hhmm(s.end_time)} onChange={(e) => setSlot(i, { end_time: e.target.value })} className={inputCls} />
            <select value={s.booking_type_id ?? ''} onChange={(e) => setSlot(i, { booking_type_id: e.target.value || null })} className={inputCls}>
              <option value="">All types</option>
              {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            {staff.length > 0 && (
              <select value={s.staff_id ?? ''} onChange={(e) => setSlot(i, { staff_id: e.target.value || null })} className={inputCls}>
                <option value="">Any staff</option>
                {staff.map((st) => <option key={st.id} value={st.id}>{st.name}</option>)}
              </select>
            )}
            {locked ? <span title="Shared by every location — change it in the All locations view" className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-semibold uppercase text-zinc-400">All locations</span> : <button type="button" aria-label="Remove window" onClick={() => setSlots((sl) => sl.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>}
            {unavailableIndexes.has(i) && (
              <p className="basis-full text-xs text-amber-400">
                This window is not connected to an active appointment type. Assign {staff.find((person) => person.id === s.staff_id)?.name ?? 'this staff member'} to a service, or change the window to Any staff.
              </p>
            )}
          </fieldset>
          )
        })}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={addSlot} className="text-xs font-medium text-emerald-400 hover:underline">+ Add window</button>
        <button onClick={saveAvailability} disabled={savingAvail} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
          {savingAvail ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save availability
        </button>
      </div>
    </section>
  )
}
