import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Package, SlidersHorizontal, AlertTriangle, Pencil, Search } from 'lucide-react'
import { cappeApi, CappeApiError } from '../../api'
import SurfaceShell, { centsToMoney } from '../../components/SurfaceShell'
import TaxSettingsCard from '../../components/TaxSettingsCard'
import ShippingSettingsCard from '../../components/ShippingSettingsCard'
import StockAdjustModal from '../../components/StockAdjustModal'
import ImageUpload from '../../components/ImageUpload'
import type { CappeBookingType, CappeFulfillment, CappeProduct, CappeProductOptionGroupInput } from '../../types'
import { parseMoneyCents, parseSignedMoneyCents } from '../../utils/money'

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

// `choices` is the comma-separated list behind a `select` question.
type IntakeRow = { label: string; type: string; required: boolean; choices: string }
// `id` is the stored row an option/group continues: sending it back is what
// keeps option ids stable across a save (orders and the stock ledger point at them).
type OptRow = { id?: string; name: string; price: string; stock: string }
type OptGroupRow = { id?: string; name: string; select_type: 'single' | 'multi'; required: boolean; options: OptRow[] }
const EMPTY = { name: '', description: '', price: '', sku: '', inventory: '', low_stock_threshold: '', image_url: '', digital_file_url: '', booking_type_id: '', category: '' }

const stockText = (value: number | null | undefined) => (value == null ? '' : String(value))
const sameSet = (a: string[], b: string[]) => [...a].sort().join() === [...b].sort().join()

export default function Shop() {
  const { siteId } = useParams<{ siteId: string }>()
  const [products, setProducts] = useState<CappeProduct[] | null>(null)
  const [bookingTypes, setBookingTypes] = useState<CappeBookingType[]>([])
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [fulfillment, setFulfillment] = useState<CappeFulfillment>('physical')
  const [requireApproval, setRequireApproval] = useState(false)
  const [intervals, setIntervals] = useState<('week' | 'month')[]>([])
  const [subscriptionDiscount, setSubscriptionDiscount] = useState('0')
  const [form, setForm] = useState(EMPTY)
  const [intake, setIntake] = useState<IntakeRow[]>([])
  const [optionGroups, setOptionGroups] = useState<OptGroupRow[]>([])
  const [adjustProduct, setAdjustProduct] = useState<CappeProduct | null>(null)
  const [editing, setEditing] = useState<CappeProduct | null>(null)
  const [publish, setPublish] = useState(true)
  const [query, setQuery] = useState('')

  // The product's own count, or any variant's, at or under the alert level.
  const isLowStock = (p: CappeProduct) => {
    if (p.fulfillment !== 'physical' || p.low_stock_threshold == null) return false
    const limit = p.low_stock_threshold
    const counts = [p.inventory, ...p.option_groups.flatMap((g) => g.options.map((o) => o.inventory))]
    return counts.some((n) => n != null && n <= limit)
  }

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

  function resetForm() {
    setForm(EMPTY)
    setIntake([])
    setOptionGroups([])
    setFulfillment('physical')
    setRequireApproval(false)
    setIntervals([])
    setSubscriptionDiscount('0')
    setEditing(null)
    setPublish(true)
  }

  // Bring the form's stock boxes in line with the shelf (after an adjustment in
  // the stock modal, or after a save was refused because stock had moved).
  function syncStock(product: CappeProduct) {
    setEditing(product)
    setForm((f) => ({ ...f, inventory: stockText(product.inventory) }))
    const shelf = new Map(product.option_groups.flatMap((g) => g.options).map((o) => [o.id, o.inventory]))
    setOptionGroups((groups) => groups.map((g) => ({
      ...g,
      options: g.options.map((o) => (o.id && shelf.has(o.id) ? { ...o, stock: stockText(shelf.get(o.id)) } : o)),
    })))
  }

  function editProduct(product: CappeProduct) {
    setEditing(product)
    setForm({
      name: product.name,
      description: product.description || '',
      price: String(product.price_cents / 100),
      sku: product.sku || '',
      inventory: stockText(product.inventory),
      low_stock_threshold: product.low_stock_threshold == null ? '' : String(product.low_stock_threshold),
      image_url: product.image_url || '',
      digital_file_url: product.digital_file_url || '',
      booking_type_id: product.booking_type_id || '',
      category: product.category || '',
    })
    setFulfillment(product.fulfillment)
    setRequireApproval(product.requires_approval)
    setIntervals(product.subscription_intervals || [])
    setSubscriptionDiscount(String((product.subscription_discount_bps || 0) / 100))
    setIntake(product.intake_fields.map((field) => ({
      label: field.label, type: field.type, required: field.required, choices: (field.options || []).join(', '),
    })))
    setOptionGroups(product.option_groups.map((group) => ({
      id: group.id,
      name: group.name,
      select_type: group.select_type,
      required: group.required,
      options: group.options.map((option) => ({
        id: option.id,
        name: option.name,
        price: String(option.price_delta_cents / 100),
        stock: stockText(option.inventory),
      })),
    })))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function saveProduct(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) return
    setAdding(true)
    setError(null)
    // Refuse an unreadable price instead of saving a truncated one:
    // parseFloat('1,299') is 1, so a $1,299 product used to save as $1.00.
    const priceCents = form.price.trim() === '' ? 0 : parseMoneyCents(form.price)
    if (priceCents === null) {
      setError('Enter the price as a plain amount, e.g. 29 or 29.99')
      setAdding(false)
      return
    }
    const badOption = optionGroups
      .flatMap((g) => g.options)
      .find((o) => o.name.trim() && o.price.trim() !== '' && parseSignedMoneyCents(o.price) === null)
    if (badOption) {
      setError(`Option "${badOption.name.trim()}" — enter the price change as a plain amount, e.g. 2.50 or -0.50`)
      setAdding(false)
      return
    }
    try {
      const discount = Number(subscriptionDiscount)
      if (!Number.isFinite(discount) || discount < 0 || discount > 50) throw new Error('Subscription discount must be between 0 and 50%')
      const physical = fulfillment === 'physical'
      const stock = (raw: string) => (physical && raw !== '' ? parseInt(raw, 10) : null)
      const subIntervals = ['physical', 'digital'].includes(fulfillment) ? intervals : []
      const subDiscount = subIntervals.length ? Math.round(discount * 100) : 0
      const details = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        price_cents: priceCents,
        sku: form.sku.trim() || null,
        low_stock_threshold: physical && form.low_stock_threshold !== '' ? parseInt(form.low_stock_threshold, 10) : null,
        image_url: form.image_url.trim() || null,
        digital_file_url: fulfillment === 'digital' ? form.digital_file_url.trim() || null : null,
        booking_type_id: fulfillment === 'booking' ? form.booking_type_id || null : null,
        requires_approval: requireApproval,
        intake_fields: wantsIntake
          ? intake.filter((f) => f.label.trim()).map((f) => ({
              key: keyFromLabel(f.label), label: f.label.trim(), type: f.type, required: f.required,
              ...(f.type === 'select'
                ? { options: f.choices.split(',').map((c) => c.trim()).filter(Boolean) }
                : {}),
            }))
          : [],
        category: form.category.trim() || null,
      }
      const emptySelect = wantsIntake
        ? intake.find((f) => f.label.trim() && f.type === 'select' && !f.choices.split(',').some((c) => c.trim()))
        : undefined
      if (emptySelect) throw new Error(`"${emptySelect.label.trim()}" is a dropdown — add at least one choice for it`)
      // Stock is sent only when this save is changing it, with the count the
      // form was showing: a save that isn't about stock must not write a stale
      // number over sales made since the form loaded.
      const groupsFor = (was: CappeProduct | null): CappeProductOptionGroupInput[] => {
        const shelf = new Map((was?.option_groups || []).flatMap((g) => g.options).map((o) => [o.id, o.inventory ?? null]))
        return optionGroups.filter((g) => g.name.trim()).map((g) => ({
          ...(g.id ? { id: g.id } : {}),
          name: g.name.trim(), select_type: g.select_type, required: g.required,
          options: g.options.filter((o) => o.name.trim()).map((o) => {
            const next = stock(o.stock)
            const known = o.id !== undefined && shelf.has(o.id)
            const before = known ? shelf.get(o.id as string) ?? null : null
            const stockChange = known
              ? (next === before ? {} : { inventory: next, expected_inventory: before })
              : (next === null ? {} : { inventory: next })
            return {
              ...(o.id ? { id: o.id } : {}),
              name: o.name.trim(),
              price_delta_cents: o.price.trim() === '' ? 0 : (parseSignedMoneyCents(o.price) ?? 0),
              ...stockChange,
            }
          }),
        }))
      }
      if (editing) {
        const nextStock = stock(form.inventory)
        const subscriptionChanged = !sameSet(subIntervals, editing.subscription_intervals || [])
          || subDiscount !== (editing.subscription_discount_bps || 0)
        // Only what changed goes in the request for the three things the API
        // treats as an event: stock (logged, and refused if it moved),
        // fulfillment and subscription settings (both plan-gated). Status is
        // changed from the list, never as a side effect of a save — this used
        // to republish every draft or archived product that was edited.
        const updated = await cappeApi.put<CappeProduct>(`/sites/${siteId}/products/${editing.id}`, {
          ...details,
          option_groups: groupsFor(editing),
          ...(fulfillment !== editing.fulfillment ? { fulfillment } : {}),
          ...(nextStock !== editing.inventory ? { inventory: nextStock, expected_inventory: editing.inventory } : {}),
          ...(subscriptionChanged ? { subscription_intervals: subIntervals, subscription_discount_bps: subDiscount } : {}),
        })
        setProducts((products) => (products || []).map((product) => product.id === updated.id ? updated : product))
      } else {
        const created = await cappeApi.post<CappeProduct>(`/sites/${siteId}/products`, {
          ...details,
          fulfillment,
          status: publish ? 'active' : 'draft',
          inventory: stock(form.inventory),
          option_groups: groupsFor(null),
          subscription_intervals: subIntervals,
          subscription_discount_bps: subDiscount,
        })
        setProducts((products) => [...(products || []), created])
      }
      resetForm()
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to ${editing ? 'save' : 'add'} product`)
      if (editing && e instanceof CappeApiError && e.status === 409) {
        // Stock moved while the form was open. Show what the shelf holds now so
        // the next save starts from the truth; everything else typed is kept.
        cappeApi.get<CappeProduct>(`/sites/${siteId}/products/${editing.id}`).then((fresh) => {
          setProducts((products) => (products || []).map((product) => product.id === fresh.id ? fresh : product))
          syncStock(fresh)
        }).catch(() => {})
      }
    } finally {
      setAdding(false)
    }
  }

  async function setStatus(prod: CappeProduct, status: string) {
    setError(null)
    try {
      const updated = await cappeApi.put<CappeProduct>(`/sites/${siteId}/products/${prod.id}`, { status })
      setProducts((p) => (p || []).map((x) => (x.id === prod.id ? updated : x)))
      if (editing?.id === updated.id) setEditing(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not change ${prod.name}`)
    }
  }

  async function remove(prod: CappeProduct) {
    if (!window.confirm(`Delete "${prod.name}"? This can't be undone. Past orders keep their line for it. To hide it instead, set it to archived.`)) return
    setError(null)
    try {
      await cappeApi.delete(`/sites/${siteId}/products/${prod.id}`)
      setProducts((p) => (p || []).filter((x) => x.id !== prod.id))
      if (editing?.id === prod.id) resetForm()
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not delete ${prod.name}`)
    }
  }

  const needle = query.trim().toLowerCase()
  const shown = (products || []).filter((p) => !needle
    || [p.name, p.category, p.sku].some((v) => (v || '').toLowerCase().includes(needle)))

  const meta = (p: CappeProduct) => {
    if (p.fulfillment === 'physical') return p.inventory === null ? 'unlimited' : p.inventory <= 0 ? 'sold out' : `${p.inventory} in stock`
    if (p.fulfillment === 'digital') return p.digital_file_url ? 'file attached' : 'no file yet'
    if (p.fulfillment === 'booking') return 'booking'
    return 'service'
  }

  return (
    <SurfaceShell title="Shop" subtitle="Anything you sell — goods, downloads, services, or bookable sessions.">
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      <TaxSettingsCard siteId={siteId || ''} />
      <ShippingSettingsCard siteId={siteId || ''} />

      <form onSubmit={saveProduct} className="mb-6 space-y-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-zinc-100">{editing ? `Edit ${editing.name}` : 'Add product'}</h2>
          {editing && <button type="button" onClick={resetForm} className="text-xs font-medium text-zinc-400 hover:text-zinc-200">Cancel edit</button>}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" className={`sm:col-span-2 ${input}`} />
          <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price (USD)" type="number" step="0.01" min="0" className={input} />
        </div>
        <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" rows={2} className={input} />
        <div className="grid gap-3 sm:grid-cols-3">
          <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Category — e.g. Drinks, Pastries (optional, groups your storefront)" className={`sm:col-span-2 ${input}`} />
          <input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} placeholder="SKU (optional)" maxLength={120} className={input} />
        </div>

        {/* fulfillment */}
        <div>
          <label className="mb-1 block text-xs font-medium text-zinc-400">Type</label>
          <div className="grid gap-2 sm:grid-cols-4">
            {FULFILLMENTS.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={() => {
                  setFulfillment(f.value)
                  if (!['physical', 'digital'].includes(f.value)) {
                    setIntervals([])
                    setSubscriptionDiscount('0')
                  }
                }}
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
            {editing && (
              <p className="text-xs text-zinc-500 sm:col-span-2">
                Changing a stock number here is recorded in the product&apos;s stock history. For a delivery, damage or a
                return, use <SlidersHorizontal className="inline h-3 w-3" /> Adjust stock in the list instead — it records why.
              </p>
            )}
          </div>
        )}

        {['physical', 'digital'].includes(fulfillment) && (
          <fieldset className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 text-sm text-zinc-300">
            <legend className="px-1 text-xs font-medium text-zinc-400">Subscribe &amp; save</legend>
            <div className="flex flex-wrap items-center gap-4">
              {(['week', 'month'] as const).map((value) => (
                <label key={value} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={intervals.includes(value)}
                    disabled={requireApproval}
                    onChange={(event) => setIntervals((old) => event.target.checked
                      ? [...old, value]
                      : old.filter((interval) => interval !== value))}
                    className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-emerald-500"
                  />
                  Every {value}
                </label>
              ))}
              <label className="flex items-center gap-2">
                Discount (%)
                <input
                  className="w-24 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100 disabled:opacity-50"
                  type="number"
                  min="0"
                  max="50"
                  step="0.01"
                  disabled={!intervals.length || requireApproval}
                  value={subscriptionDiscount}
                  onChange={(event) => setSubscriptionDiscount(event.target.value)}
                />
              </label>
            </div>
            {requireApproval && <p className="mt-2 text-xs text-zinc-500">Subscriptions are unavailable for products that require approval.</p>}
          </fieldset>
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
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <input value={f.label} onChange={(e) => setIntake((xs) => xs.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} placeholder="Question label" className={`flex-1 ${input}`} />
                  <select value={f.type} onChange={(e) => setIntake((xs) => xs.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100">
                    {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <label className="flex items-center gap-1 text-xs text-zinc-500">
                    <input type="checkbox" checked={f.required} onChange={(e) => setIntake((xs) => xs.map((x, j) => (j === i ? { ...x, required: e.target.checked } : x)))} className="h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-emerald-500" /> req
                  </label>
                  <button type="button" onClick={() => setIntake((xs) => xs.filter((_, j) => j !== i))} aria-label="Remove question" className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
                  {f.type === 'select' && (
                    <input value={f.choices} onChange={(e) => setIntake((xs) => xs.map((x, j) => (j === i ? { ...x, choices: e.target.value } : x)))} placeholder="Choices, separated by commas — e.g. Small, Medium, Large" aria-label="Dropdown choices" className={`basis-full ${input}`} />
                  )}
                </div>
              ))}
              <button type="button" onClick={() => setIntake((xs) => [...xs, { label: '', type: 'text', required: false, choices: '' }])} className="text-xs font-medium text-emerald-400 hover:text-emerald-300">+ Add question</button>
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
          <input
            type="checkbox"
            checked={requireApproval}
            onChange={(event) => {
              setRequireApproval(event.target.checked)
              if (event.target.checked) {
                setIntervals([])
                setSubscriptionDiscount('0')
              }
            }}
            className="h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500"
          />
          Review &amp; approve each order before it's confirmed
        </label>

        {!editing && (
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            <input type="checkbox" checked={publish} onChange={(event) => setPublish(event.target.checked)} className="h-4 w-4 rounded border-zinc-600 bg-zinc-950 text-emerald-500" />
            Show in my shop right away <span className="text-xs text-zinc-500">(untick to save as a draft)</span>
          </label>
        )}

        <button type="submit" disabled={adding} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
          {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : editing ? <Pencil className="h-4 w-4" /> : <Plus className="h-4 w-4" />} {editing ? 'Save changes' : 'Add product'}
        </button>
      </form>

      {products === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : products.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Package className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No products yet.
        </div>
      ) : (
        <>
        {products.length > 6 && (
          <label className="mb-3 flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-400 focus-within:border-emerald-500">
            <Search className="h-4 w-4 shrink-0" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products by name, category or SKU" aria-label="Search products" className="w-full bg-transparent text-zinc-100 placeholder:text-zinc-500 outline-none" />
          </label>
        )}
        {shown.length === 0 && <p className="py-8 text-center text-sm text-zinc-500">No products match “{query.trim()}”.</p>}
        <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900 empty:hidden">
          {shown.map((p) => (
            <div key={p.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3">
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
                  {p.category ? `${p.category} · ` : ''}{centsToMoney(p.price_cents, p.currency)} · {meta(p)}{p.sku ? ` · SKU ${p.sku}` : ''}
                  {p.option_groups?.length ? ` · ${p.option_groups.length} option${p.option_groups.length > 1 ? 's' : ''}` : ''}
                </div>
              </div>
              {p.fulfillment === 'physical' && (
                <button onClick={() => setAdjustProduct(p)} title="Adjust stock" aria-label={`Adjust stock for ${p.name}`} className="text-zinc-400 hover:text-emerald-400"><SlidersHorizontal className="h-4 w-4" /></button>
              )}
              <button onClick={() => editProduct(p)} title={`Edit ${p.name}`} aria-label={`Edit ${p.name}`} className="text-zinc-400 hover:text-emerald-400"><Pencil className="h-4 w-4" /></button>
              <select value={p.status} onChange={(e) => setStatus(p, e.target.value)} aria-label={`Status of ${p.name}`} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100">
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <button onClick={() => remove(p)} title={`Delete ${p.name}`} aria-label={`Delete ${p.name}`} className="text-zinc-400 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
        </>
      )}

      {adjustProduct && (
        <StockAdjustModal
          siteId={siteId || ''}
          product={adjustProduct}
          onClose={() => setAdjustProduct(null)}
          onUpdated={(u) => {
            setProducts((p) => (p || []).map((x) => (x.id === u.id ? u : x)))
            setAdjustProduct(u)
            // Keep an open edit form on the same count, or its next save would
            // be refused as stale.
            if (editing?.id === u.id) syncStock(u)
          }}
        />
      )}
    </SurfaceShell>
  )
}
