import { useState, type Dispatch, type SetStateAction } from 'react'
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react'
import type { CappeBookingType, CappePricingMode, CappeStaff } from '../../../types'
import { parseMoneyCents } from '../../../utils/money'
import { money, inputCls } from './constants'
import type { TypeForm } from './types'

interface BookingTypesSectionProps {
  types: CappeBookingType[]
  typeForm: TypeForm
  setTypeForm: Dispatch<SetStateAction<TypeForm>>
  addType: (e: React.FormEvent) => void
  staff: CappeStaff[]
  patchType: (id: string, patch: Partial<CappeBookingType>) => Promise<boolean> | void
  removeType: (t: CappeBookingType) => void
  toggleTypeStaff: (t: CappeBookingType, staffId: string) => void
  currency?: string
}

/** " · 2h notice · up to 60 days ahead · changes close 24h before" */
function rulesText(t: CappeBookingType): string {
  const bits = []
  if (t.min_notice_minutes) bits.push(`${+(t.min_notice_minutes / 60).toFixed(1)}h notice`)
  if (t.max_advance_days) bits.push(`up to ${t.max_advance_days} days ahead`)
  if (t.cancel_cutoff_hours) bits.push(`changes close ${t.cancel_cutoff_hours}h before`)
  return bits.length ? ` · ${bits.join(' · ')}` : ''
}

export function BookingTypesSection({
  types, typeForm, setTypeForm, addType, staff, patchType, removeType, toggleTypeStaff, currency = 'USD',
}: BookingTypesSectionProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
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
          <input value={typeForm.price} onChange={(e) => setTypeForm({ ...typeForm, price: e.target.value })} type="number" min="0" step="0.01" placeholder={typeForm.pricing_mode === 'hourly' ? `${currency}/hr` : currency} className={`w-24 ${inputCls}`} />
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
          {types.map((t) => editingId === t.id ? (
            <li key={t.id} className="py-2.5">
              <TypeEditor
                type={t}
                currency={currency}
                onCancel={() => setEditingId(null)}
                onSave={async (patch) => { if (await patchType(t.id, patch)) setEditingId(null) }}
              />
            </li>
          ) : (
            <li key={t.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <span className="text-zinc-200">{t.name}</span>
                {t.status !== 'active' && <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase text-zinc-400">{t.status} — not bookable</span>}
                {t.category && <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{t.category}</span>}
                <span className="text-zinc-400"> · {t.duration_minutes} min · {t.pricing_mode === 'hourly' ? `${money(t.price_cents, currency)}/hr` : money(t.price_cents, currency)}{t.buffer_minutes ? ` · ${t.buffer_minutes}m buffer` : ''}{rulesText(t)}</span>
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
              <button onClick={() => setEditingId(t.id)} aria-label={`Edit ${t.name}`} title={`Edit ${t.name}`} className="text-zinc-400 hover:text-emerald-400"><Pencil className="h-4 w-4" /></button>
              <button onClick={() => removeType(t)} aria-label={`Delete ${t.name}`} title={`Delete ${t.name}`} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** Edit an appointment type in place. Changes apply to new bookings; existing
 *  ones keep the time and price they were booked at. */
function TypeEditor({ type: t, currency, onSave, onCancel }: {
  type: CappeBookingType
  currency: string
  onSave: (patch: Partial<CappeBookingType>) => Promise<void>
  onCancel: () => void
}) {
  const [form, setForm] = useState({
    name: t.name,
    description: t.description || '',
    duration: String(t.duration_minutes),
    pricing_mode: t.pricing_mode,
    price: t.price_cents == null ? '' : String(t.price_cents / 100),
    buffer: String(t.buffer_minutes || 0),
    category: t.category || '',
    status: t.status,
    notice: t.min_notice_minutes ? String(t.min_notice_minutes / 60) : '',
    advance: t.max_advance_days ? String(t.max_advance_days) : '',
    cutoff: t.cancel_cutoff_hours ? String(t.cancel_cutoff_hours) : '',
  })
  const [problem, setProblem] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const duration = parseInt(form.duration, 10)
    const buffer = parseInt(form.buffer, 10)
    const price = form.price.trim() === '' ? 0 : parseMoneyCents(form.price)
    if (!form.name.trim()) { setProblem('Give it a name'); return }
    if (!Number.isFinite(duration) || duration < 1) { setProblem('Enter the length in minutes'); return }
    if (!Number.isFinite(buffer) || buffer < 0) { setProblem('Enter the buffer in minutes (0 for none)'); return }
    if (price === null) { setProblem('Enter the price as a plain amount, e.g. 75 or 75.00'); return }
    const notice = form.notice.trim() === '' ? 0 : Number(form.notice)
    const advance = form.advance.trim() === '' ? null : Number(form.advance)
    const cutoff = form.cutoff.trim() === '' ? 0 : Number(form.cutoff)
    if (!Number.isFinite(notice) || notice < 0 || notice > 720) { setProblem('Minimum notice is 0 to 720 hours'); return }
    if (advance !== null && (!Number.isInteger(advance) || advance < 1 || advance > 730)) { setProblem('Book up to 1 to 730 days ahead, or leave it empty'); return }
    if (!Number.isInteger(cutoff) || cutoff < 0 || cutoff > 720) { setProblem('Changes close 0 to 720 hours before'); return }
    setProblem(null)
    setSaving(true)
    try {
      await onSave({
        name: form.name.trim(), description: form.description.trim() || null,
        duration_minutes: duration, pricing_mode: form.pricing_mode, price_cents: price,
        buffer_minutes: buffer, category: form.category.trim() || null, status: form.status,
        min_notice_minutes: Math.round(notice * 60), max_advance_days: advance, cancel_cutoff_hours: cutoff,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} aria-label={`Edit ${t.name}`} className="grid gap-2 rounded-lg border border-zinc-700 bg-zinc-950/60 p-3 sm:grid-cols-2">
      <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} aria-label="Name" className={inputCls} />
      <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Category (optional)" aria-label="Category" className={inputCls} />
      <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Short description (optional)" aria-label="Description" className={`sm:col-span-2 ${inputCls}`} />
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-xs text-zinc-400">
          <input value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} type="number" min="1" aria-label="Length in minutes" className={`w-20 ${inputCls}`} /> min
        </label>
        <select value={form.pricing_mode} onChange={(e) => setForm({ ...form, pricing_mode: e.target.value as CappePricingMode })} aria-label="Pricing" className={inputCls}>
          <option value="flat">Flat price</option>
          <option value="hourly">Per hour</option>
        </select>
        <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} type="number" min="0" step="0.01" aria-label="Price" placeholder={form.pricing_mode === 'hourly' ? `${currency}/hr` : currency} className={`w-24 ${inputCls}`} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-xs text-zinc-400">
          <input value={form.buffer} onChange={(e) => setForm({ ...form, buffer: e.target.value })} type="number" min="0" step="5" aria-label="Buffer minutes" className={`w-20 ${inputCls}`} /> min buffer
        </label>
        <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as CappeBookingType['status'] })} aria-label="Status" className={inputCls}>
          <option value="active">Bookable</option>
          <option value="archived">Archived — hidden from booking</option>
        </select>
      </div>
      <fieldset className="grid gap-2 sm:col-span-2 sm:grid-cols-3">
        <legend className="mb-1 text-xs font-medium text-zinc-400">Booking rules</legend>
        <label className="text-xs text-zinc-400">Minimum notice (hours)
          <input value={form.notice} onChange={(e) => setForm({ ...form, notice: e.target.value })} inputMode="decimal" placeholder="None" className={`mt-1 w-full ${inputCls}`} />
        </label>
        <label className="text-xs text-zinc-400">Book up to (days ahead)
          <input value={form.advance} onChange={(e) => setForm({ ...form, advance: e.target.value })} inputMode="numeric" placeholder="No limit" className={`mt-1 w-full ${inputCls}`} />
        </label>
        <label className="text-xs text-zinc-400">Online changes close (hours before)
          <input value={form.cutoff} onChange={(e) => setForm({ ...form, cutoff: e.target.value })} inputMode="numeric" placeholder="Up to the start" className={`mt-1 w-full ${inputCls}`} />
        </label>
      </fieldset>
      <p className="text-xs text-zinc-500 sm:col-span-2">Changes apply to new bookings. Existing bookings keep their time and price. Bookings you make yourself skip these rules.</p>
      {problem && <p role="alert" className="text-xs text-red-400 sm:col-span-2">{problem}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save
        </button>
        <button type="button" onClick={onCancel} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
      </div>
    </form>
  )
}
