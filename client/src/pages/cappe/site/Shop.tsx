import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Package } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell, { centsToMoney } from '../../../components/cappe/SurfaceShell'
import ImageUpload from '../../../components/cappe/ImageUpload'
import type { CappeProduct } from '../../../types/cappe'

const STATUSES = ['active', 'draft', 'archived'] as const

export default function Shop() {
  const { siteId } = useParams<{ siteId: string }>()
  const [products, setProducts] = useState<CappeProduct[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: '', price: '', inventory: '', image_url: '' })

  useEffect(() => {
    cappeApi
      .get<CappeProduct[]>(`/sites/${siteId}/products`)
      .then(setProducts)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load products'))
  }, [siteId])

  async function addProduct(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim()) return
    setAdding(true)
    setError(null)
    try {
      const created = await cappeApi.post<CappeProduct>(`/sites/${siteId}/products`, {
        name: form.name.trim(),
        price_cents: Math.round(parseFloat(form.price || '0') * 100),
        inventory: form.inventory === '' ? null : parseInt(form.inventory, 10),
        image_url: form.image_url.trim() || null,
        status: 'active',
      })
      setProducts((p) => [...(p || []), created])
      setForm({ name: '', price: '', inventory: '', image_url: '' })
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

  return (
    <SurfaceShell title="Shop" subtitle="Products you sell on this site.">
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      <form onSubmit={addProduct} className="mb-6 grid grid-cols-1 gap-3 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm sm:grid-cols-12">
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Product name"
          className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500 sm:col-span-5"
        />
        <input
          value={form.price}
          onChange={(e) => setForm({ ...form, price: e.target.value })}
          placeholder="Price (USD)"
          type="number"
          step="0.01"
          min="0"
          className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500 sm:col-span-2"
        />
        <input
          value={form.inventory}
          onChange={(e) => setForm({ ...form, inventory: e.target.value })}
          placeholder="Stock (blank = ∞)"
          type="number"
          min="0"
          className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500 sm:col-span-2"
        />
        <button
          type="submit"
          disabled={adding}
          className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60 sm:col-span-3"
        >
          {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add product
        </button>
        <div className="sm:col-span-12">
          <ImageUpload
            siteId={siteId || ''}
            value={form.image_url}
            onChange={(url) => setForm({ ...form, image_url: url })}
            placeholder="Product image URL (optional)"
          />
        </div>
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
                <div className="truncate font-medium text-zinc-100">{p.name}</div>
                <div className="text-xs text-zinc-500">
                  {centsToMoney(p.price_cents, p.currency)} · {p.inventory === null ? 'unlimited' : `${p.inventory} in stock`}
                </div>
              </div>
              <select
                value={p.status}
                onChange={(e) => setStatus(p, e.target.value)}
                className="rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-2 py-1 text-xs"
              >
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <button onClick={() => remove(p.id)} className="text-zinc-400 hover:text-red-400">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </SurfaceShell>
  )
}
