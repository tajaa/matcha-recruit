import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Package, SlidersHorizontal, AlertTriangle } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell, { centsToMoney } from '../../../components/cappe/SurfaceShell'
import TaxSettingsCard from '../../../components/cappe/TaxSettingsCard'
import StockAdjustModal from '../../../components/cappe/StockAdjustModal'
import ImageUpload from '../../../components/cappe/ImageUpload'
import type { CappeBookingType, CappeFulfillment, CappeProduct } from '../../../types/cappe'

const STATUSES = ['active', 'draft', 'archived'] as const
const FIELD_TYPES = ['text', 'email', 'textarea', 'number', 'tel', 'date', 'select']
const DELIVERABLE_ACCEPT = '.pdf,.zip,.doc,.docx,.xls,.xlsx,.csv,.txt,image/*'

const FULFILLMENTS: { value: CappeFulfillment; label: string; hint: string }[] = [
  { value: 'physical', label: 'Physical good', hint: 'A shipped item with stock' },
  { value: 'digital', label: 'Digital download', hint: 'Buyer downloads a file you upload' },
  { value: 'service', label: 'Service / package', hint: 'You deliver a result (e.g. a report, photos)' },
  { value: 'booking', label: 'Booking / session', hint: 'Buyer reserves a time slot' },
]

const fulfillBadge: Record<string, string> = {
  physical: 'bg-zinc-800 text-zinc-300',
  digital: 'bg-sky-500/15 text-sky-400',
  service: 'bg-violet-500/15 text-violet-400',
  booking: 'bg-amber-500/15 text-amber-400',
}

const input = 'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500'

function keyFromLabel(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'field'
}

type IntakeRow = { label: string; type: string; required: boolean }
type OptRow = { name: string; price: string; stock: string }
type OptGroupRow = { name: string; select_type: 'single' | 'multi'; required: boolean; options: OptRow[] }
const EMPTY = { name: '', description: '', price: '', inventory: '', low_stock_threshold: '', image_url: '', digital_file_url: '', booking_type_id: '', category: '' }

export default function Shop() {
  const { siteId } = useParams<{ siteId: string }>()
  const [products, setProducts] = useState<CappeProduct[] | null>(null)
  const [bookingTypes, setBookingTypes] = useState<CappeBookingType[]>([])
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [fulfillment, setFulfillment] = useState<CappeFulfillment>('physical')
  const [requireApproval, setRequireApproval] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [intake, setIntake] = useState<IntakeRow[]>([])
  const [optionGroups, setOptionGroups] = useState<OptGroupRow[]>([])
  const [adjustProduct, setAdjustProduct] = useState<CappeProduct | null>(null)

  const isLowStock = (p: CappeProduct) =>
    p.fulfillment === 'physical' && p.inventory != null && p.low_stock_threshold != null && p.inventory <= p.low_stock_threshold

  // option-group editors
  const setGroup = (gi: number, patch: Partial<OptGroupRow>) =>
    setOptionGroups((gs) => gs.map((g, j) => (j === gi ? { ...g, ...patch } : g)))
  const setOpt = (gi: number, oi: number, patch: Partial<OptRow>) =>
    setOptionGroups((gs) => gs.map((g, j) => (j === gi ? { ...g, options: g.options.map((o, k) => (k === oi ? { ...o, ...patch } : o)) } : g)))

  useEffect(() => {
    cappeApi.get<CappeProduct[]>(`/sites/${siteId}/products`).then(setProducts)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load products'))
    cappeApi.get<CappeBookingType[]>(`/sites/${siteId}/booking-types`).then(setBookingTypes).catch(() => {})
  }, [siteId])

  const wantsIntake = fulfillment === 'service' || fulfillment === 'booking'

  async function addProduct(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) return
    setAdding(true)
    setError(null)
    try {
      const created = await cappeApi.post<CappeProduct>(`/sites/${siteId}/products`, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        price_cents: Math.round(parseFloat(form.price || '0') * 100),
        status: 'active',
        fulfillment,
        inventory: fulfillment === 'physical' && form.inventory !== '' ? parseInt(form.inventory, 10) : null,
        low_stock_threshold: fulfillment === 'physical' && form.low_stock_threshold !== '' ? parseInt(form.low_stock_threshold, 10) : null,
        image_url: form.image_url.trim() || null,
        digital_file_url: fulfillment === 'digital' ? form.digital_file_url.trim() || null : null,
        booking_type_id: fulfillment === 'booking' ? form.booking_type_id || null : null,
        requires_approval: requireApproval,
        intake_fields: wantsIntake
          ? intake.filter((f) => f.label.trim()).map((f) => ({
              key: keyFromLabel(f.label), label: f.label.trim(), type: f.type, required: f.required,
            }))
          : [],
        category: form.category.trim() || null,
        option_groups: optionGroups
          .filter((g) => g.name.trim())
          .map((g) => ({
            name: g.name.trim(), select_type: g.select_type, required: g.required,
            options: g.options.filter((o) => o.name.trim()).map((o) => ({
              name: o.name.trim(), price_delta_cents: Math.round(parseFloat(o.price || '0') * 100),
              inventory: fulfillment === 'physical' && o.stock !== '' ? parseInt(o.stock, 10) : null,
            })),
          })),
      })
      setProducts((p) => [...(p || []), created])
      setForm(EMPTY); setIntake([]); setOptionGroups([]); setFulfillment('physical'); setRequireApproval(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add product')
    } finally {
      setAdding(false)
    }
  }

  async function setStatus(prod: CappeProduct, status: string) {
    const updated = await cappeApi.put<CappeProduct>(`/sites/${siteId}/products/${prod.id}`, { status })
    setProducts((p) => (p || []).map((x) => (x.id === prod.id ? updated : x)))
  }

  async function remove(id: string) {
    await cappeApi.delete(`/sites/${siteId}/products/${id}`)
    setProducts((p) => (p || []).filter((x) => x.id !== id))
  }

  const meta = (p: CappeProduct) => {
    if (p.fulfillment === 'physical') return p.inventory === null ? 'unlimited' : `${p.inventory} in stock`
    if (p.fulfillment === 'digital') return p.digital_file_url ? 'file attached' : 'no file yet'
    if (p.fulfillment === 'booking') return 'booking'
    return 'service'
  }

  return (
    <SurfaceShell title="Shop" subtitle="Anything you sell — goods, downloads, services, or bookable sessions.">
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      <TaxSettingsCard siteId={siteId || ''} />

      <form onSubmit={addProduct} className="mb-6 space-y-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
        <div className="grid gap-3 sm:grid-cols-3">
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" className={`sm:col-span-2 ${input}`} />
          <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price (USD)" type="number" step="0.01" min="0" className={input} />
        </div>
        <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" rows={2} className={input} />
        <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Category — e.g. Drinks, Pastries (optional, groups your storefront)" className={input} />

        {/* fulfillment */}
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">Type</label>
          <div className="grid gap-2 sm:grid-cols-4">
            {FULFILLMENTS.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={() => setFulfillment(f.value)}
                className={`rounded-lg border px-3 py-2 text-left text-sm transition ${
                  fulfillment === f.value
                    ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300'
                    : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'
                }`}
              >
                <div className="font-medium">{f.label}</div>
                <div className="text-[11px] text-zinc-500">{f.hint}</div>
              </button>
            ))}
          </div>
        </div>

        {/* conditional fields */}
        {fulfillment === 'physical' && (
          <div className="grid gap-3 sm:grid-cols-2">
            <input value={form.inventory} onChange={(e) => setForm({ ...form, inventory: e.target.value })} placeholder="Stock (blank = unlimited)" type="number" min="0" className={input} />
            <input value={form.low_stock_threshold} onChange={(e) => setForm({ ...form, low_stock_threshold: e.target.value })} placeholder="Low-stock alert at… (optional)" type="number" min="0" className={input} />
          </div>
        )}
        {fulfillment === 'digital' && (
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Deliverable file (buyer downloads this once paid)</label>
            <ImageUpload siteId={siteId || ''} value={form.digital_file_url} onChange={(url) => setForm({ ...form, digital_file_url: url })} placeholder="File URL" endpoint="/upload-file" accept={DELIVERABLE_ACCEPT} kind="file" />
          </div>
        )}
        {fulfillment === 'booking' && (
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-400">Booking type (time + duration)</label>
            {bookingTypes.length === 0 ? (
              <p className="text-xs text-amber-400">Create a booking type in the Bookings tab first.</p>
            ) : (
              <select value={form.booking_type_id} onChange={(e) => setForm({ ...form, booking_type_id: e.target.value })} className={input}>
                <option value="">Select…</option>
                {bookingTypes.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.duration_minutes} min)</option>)}
              </select>
            )}
          </div>
        )}

        {/* intake questions for service/booking */}
        {wantsIntake && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
            <div className="mb-2 text-xs font-medium text-zinc-400">Intake questions (asked at checkout)</div>
            <div className="space-y-2">
              {intake.map((f, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input value={f.label} onChange={(e) => setIntake((xs) => xs.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} placeholder="Question label" className={`flex-1 ${input}`} />
                  <select value={f.type} onChange={(e) => setIntake((xs) => xs.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100">
                    {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <label className="flex items-center gap-1 text-xs text-zinc-500">
                    <input type="checkbox" checked={f.required} onChange={(e) => setIntake((xs) => xs.map((x, j) => (j === i ? { ...x, required: e.target.checked } : x)))} className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-emerald-500" /> req
                  </label>
                  <button type="button" onClick={() => setIntake((xs) => xs.filter((_, j) => j !== i))} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                </div>
              ))}
              <button type="button" onClick={() => setIntake((xs) => [...xs, { label: '', type: 'text', required: false }])} className="text-xs font-medium text-emerald-400 hover:text-emerald-300">+ Add question</button>
            </div>
          </div>
        )}

        {/* options (size, milk, add-ons) */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
          <div className="mb-2 text-xs font-medium text-zinc-400">Options — size, milk, add-ons (each can change the price)</div>
          <div className="space-y-3">
            {optionGroups.map((g, gi) => (
              <div key={gi} className="rounded-lg border border-zinc-800 p-2.5">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <input value={g.name} onChange={(e) => setGroup(gi, { name: e.target.value })} placeholder="Group (e.g. Size)" className={`min-w-0 flex-1 ${input}`} />
                  <select value={g.select_type} onChange={(e) => setGroup(gi, { select_type: e.target.value as 'single' | 'multi' })} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100">
                    <option value="single">Pick one</option>
                    <option value="multi">Pick many</option>
                  </select>
                  <label className="flex items-center gap-1 text-xs text-zinc-500">
                    <input type="checkbox" checked={g.required} onChange={(e) => setGroup(gi, { required: e.target.checked })} className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-emerald-500" /> req
                  </label>
                  <button type="button" onClick={() => setOptionGroups((gs) => gs.filter((_, j) => j !== gi))} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                </div>
                <div className="space-y-1.5 pl-1">
                  {g.options.map((o, oi) => (
                    <div key={oi} className="flex items-center gap-2">
                      <input value={o.name} onChange={(e) => setOpt(gi, oi, { name: e.target.value })} placeholder="Option (e.g. Large)" className={`flex-1 ${input}`} />
                      <input value={o.price} onChange={(e) => setOpt(gi, oi, { price: e.target.value })} placeholder="+$0.00" type="number" step="0.01" className={`w-24 ${input}`} />
                      {fulfillment === 'physical' && (
                        <input value={o.stock} onChange={(e) => setOpt(gi, oi, { stock: e.target.value })} placeholder="stock" type="number" min="0" title="Per-variant stock (blank = untracked)" className={`w-20 ${input}`} />
                      )}
                      <button type="button" onClick={() => setGroup(gi, { options: g.options.filter((_, k) => k !== oi) })} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                    </div>
                  ))}
                  <button type="button" onClick={() => setGroup(gi, { options: [...g.options, { name: '', price: '', stock: '' }] })} className="text-xs font-medium text-emerald-400 hover:text-emerald-300">+ Add option</button>
                </div>
              </div>
            ))}
            <button type="button" onClick={() => setOptionGroups((gs) => [...gs, { name: '', select_type: 'single', required: false, options: [{ name: '', price: '', stock: '' }] }])} className="text-xs font-medium text-emerald-400 hover:text-emerald-300">+ Add option group</button>
          </div>
        </div>

        <ImageUpload siteId={siteId || ''} value={form.image_url} onChange={(url) => setForm({ ...form, image_url: url })} placeholder="Cover image URL (optional)" />

        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={requireApproval} onChange={(e) => setRequireApproval(e.target.checked)} className="h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
          Review &amp; approve each order before it's confirmed
        </label>

        <button type="submit" disabled={adding} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
          {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add product
        </button>
      </form>

      {products === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : products.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Package className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No products yet.
        </div>
      ) : (
        <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
          {products.map((p) => (
            <div key={p.id} className="flex items-center gap-4 px-5 py-3">
              <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-zinc-800">
                {p.image_url && <img src={p.image_url} alt="" className="h-full w-full object-cover" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium text-zinc-100">{p.name}</span>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${fulfillBadge[p.fulfillment] || fulfillBadge.physical}`}>{p.fulfillment}</span>
                  {isLowStock(p) && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-400"><AlertTriangle className="h-3 w-3" /> low stock</span>
                  )}
                </div>
                <div className="text-xs text-zinc-500">
                  {p.category ? `${p.category} · ` : ''}{centsToMoney(p.price_cents, p.currency)} · {meta(p)}
                  {p.option_groups?.length ? ` · ${p.option_groups.length} option${p.option_groups.length > 1 ? 's' : ''}` : ''}
                </div>
              </div>
              {p.fulfillment === 'physical' && (
                <button onClick={() => setAdjustProduct(p)} title="Adjust stock" className="text-zinc-400 hover:text-emerald-400"><SlidersHorizontal className="h-4 w-4" /></button>
              )}
              <select value={p.status} onChange={(e) => setStatus(p, e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <button onClick={() => remove(p.id)} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
      )}

      {adjustProduct && (
        <StockAdjustModal
          siteId={siteId || ''}
          product={adjustProduct}
          onClose={() => setAdjustProduct(null)}
          onUpdated={(u) => { setProducts((p) => (p || []).map((x) => (x.id === u.id ? u : x))); setAdjustProduct(u) }}
        />
      )}
    </SurfaceShell>
  )
}
