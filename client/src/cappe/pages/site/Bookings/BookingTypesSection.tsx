import type { Dispatch, SetStateAction } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type { CappeBookingType, CappePricingMode, CappeStaff } from '../../../types'
import { money, inputCls } from './constants'
import type { TypeForm } from './types'

interface BookingTypesSectionProps {
  types: CappeBookingType[]
  typeForm: TypeForm
  setTypeForm: Dispatch<SetStateAction<TypeForm>>
  addType: (e: React.FormEvent) => void
  staff: CappeStaff[]
  patchType: (id: string, patch: Partial<CappeBookingType>) => void
  removeType: (id: string) => void
  toggleTypeStaff: (t: CappeBookingType, staffId: string) => void
}

export function BookingTypesSection({
  types, typeForm, setTypeForm, addType, staff, patchType, removeType, toggleTypeStaff,
}: BookingTypesSectionProps) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-zinc-100">Appointment types</h2>
      <form onSubmit={addType} className="mb-4 grid gap-2 sm:grid-cols-2">
        <input value={typeForm.name} onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })} placeholder="Name — e.g. Wedding shoot" className={inputCls} />
        <input value={typeForm.description} onChange={(e) => setTypeForm({ ...typeForm, description: e.target.value })} placeholder="Short description (optional)" className={`sm:col-span-2 ${inputCls}`} />
        <div className="flex gap-2">
          <input value={typeForm.duration_minutes} onChange={(e) => setTypeForm({ ...typeForm, duration_minutes: e.target.value })} type="number" min="1" placeholder="min" className={`w-24 ${inputCls}`} />
          <select value={typeForm.pricing_mode} onChange={(e) => setTypeForm({ ...typeForm, pricing_mode: e.target.value as CappePricingMode })} className={inputCls}>
            <option value="flat">Flat price</option>
            <option value="hourly">Per hour</option>
          </select>
          <input value={typeForm.price} onChange={(e) => setTypeForm({ ...typeForm, price: e.target.value })} type="number" min="0" step="0.01" placeholder={typeForm.pricing_mode === 'hourly' ? '$/hr' : '$'} className={`w-24 ${inputCls}`} />
        </div>
        <div className="flex gap-2">
          <input value={typeForm.category} onChange={(e) => setTypeForm({ ...typeForm, category: e.target.value })} placeholder="Category — e.g. Color (optional)" className={`flex-1 ${inputCls}`} />
          <input value={typeForm.buffer} onChange={(e) => setTypeForm({ ...typeForm, buffer: e.target.value })} type="number" min="0" step="5" title="Buffer minutes between appointments" placeholder="buffer min" className={`w-28 ${inputCls}`} />
        </div>
        {staff.length > 0 && (
          <div className="sm:col-span-2">
            <div className="mb-1 text-xs text-zinc-400">Who performs it (none = shared calendar)</div>
            <div className="flex flex-wrap gap-1.5">
              {staff.map((s) => {
                const on = typeForm.staffIds.includes(s.id)
                return (
                  <button key={s.id} type="button" onClick={() => setTypeForm((f) => ({ ...f, staffIds: on ? f.staffIds.filter((x) => x !== s.id) : [...f.staffIds, s.id] }))}
                    className={`rounded-full border px-2.5 py-1 text-xs ${on ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-zinc-700 text-zinc-400 hover:bg-zinc-800'}`}>
                    {s.name}
                  </button>
                )
              })}
            </div>
          </div>
        )}
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={typeForm.requires_approval} onChange={(e) => setTypeForm({ ...typeForm, requires_approval: e.target.checked })} className="h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
          Require my approval before it books
        </label>
        <button type="submit" className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"><Plus className="h-4 w-4" /> Add type</button>
      </form>
      {types.length === 0 ? (
        <p className="text-sm text-zinc-400">No appointment types yet.</p>
      ) : (
        <ul className="divide-y divide-zinc-800">
          {types.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <span className="text-zinc-200">{t.name}</span>
                {t.category && <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{t.category}</span>}
                <span className="text-zinc-400"> · {t.duration_minutes} min · {t.pricing_mode === 'hourly' ? `${money(t.price_cents)}/hr` : money(t.price_cents)}{t.buffer_minutes ? ` · ${t.buffer_minutes}m buffer` : ''}</span>
                {t.description && <div className="truncate text-xs text-zinc-500">{t.description}</div>}
                {staff.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] text-zinc-500">Staff:</span>
                    {staff.map((s) => {
                      const on = (t.staff_ids || []).includes(s.id)
                      return (
                        <button key={s.id} type="button" onClick={() => toggleTypeStaff(t, s.id)}
                          className={`rounded-full border px-2 py-0.5 text-[11px] ${on ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-zinc-700 text-zinc-500 hover:bg-zinc-800'}`}>
                          {s.name}
                        </button>
                      )
                    })}
                    {(t.staff_ids || []).length === 0 && <span className="text-[11px] text-zinc-600">shared calendar</span>}
                  </div>
                )}
              </div>
              <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                <input type="checkbox" checked={t.requires_approval} onChange={(e) => patchType(t.id, { requires_approval: e.target.checked })} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
                Needs approval
              </label>
              <button onClick={() => removeType(t.id)} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
