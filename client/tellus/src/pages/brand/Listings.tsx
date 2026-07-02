import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, Empty, ErrorText, Input, Select, Spinner, Textarea } from '../../components/ui'
import type { Listing, Redemption } from '../../api/types'

function RedemptionsPanel({ listingId }: { listingId: string }) {
  const [items, setItems] = useState<Redemption[] | null>(null)

  async function load() {
    setItems(await tellusApi.get<Redemption[]>(`/listings/${listingId}/redemptions`))
  }
  useEffect(() => { void load() }, [listingId])

  async function mark(id: string, status: string) {
    await tellusApi.patch(`/redemptions/${id}`, { status }); await load()
  }

  if (items === null) return <Spinner />
  if (items.length === 0) return <p className="p-4 text-sm text-tu-faint">No redemptions yet.</p>
  return (
    <ul className="divide-y divide-tu-border">
      {items.map((r) => (
        <li key={r.id} className="flex items-center justify-between gap-2 px-4 py-3 text-sm">
          <div>
            {r.code && <span className="font-mono tracking-widest text-tu-accent">{r.code}</span>}
            <span className="ml-2 text-xs text-tu-faint">{new Date(r.created_at).toLocaleDateString()}</span>
          </div>
          <div className="flex items-center gap-2">
            <Chip>{r.status}</Chip>
            {r.status === 'issued' && <Button variant="soft" onClick={() => mark(r.id, 'redeemed')}>Mark claimed</Button>}
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function BrandListings() {
  const [listings, setListings] = useState<Listing[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [cost, setCost] = useState(100)
  const [qty, setQty] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [rtype, setRtype] = useState<'code' | 'qr' | 'manual'>('code')

  async function load() {
    setLoading(true)
    setListings(await tellusApi.get<Listing[]>('/listings')); setLoading(false)
  }
  useEffect(() => { void load() }, [])

  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(''); setCreating(true)
    try {
      await tellusApi.post('/listings', {
        title, description: desc || null, points_cost: cost,
        quantity_total: qty ? Number(qty) : null, city: city || null, state: state || null,
        redemption_type: rtype, is_active: true,
      })
      setTitle(''); setDesc(''); setCost(100); setQty(''); setCity(''); setState(''); await load()
    } catch (e) { setErr(e instanceof Error ? e.message : 'Could not create listing') } finally { setCreating(false) }
  }

  async function toggle(l: Listing) {
    await tellusApi.patch(`/listings/${l.id}`, { is_active: !l.is_active }); await load()
  }
  async function remove(l: Listing) {
    if (!confirm('Deactivate this reward?')) return
    await tellusApi.delete(`/listings/${l.id}`); await load()
  }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold">Rewards you offer</h1>

      <Card>
        <form onSubmit={create} className="grid gap-3 sm:grid-cols-2">
          <Input label="Title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Free coffee" />
          <Input label="Points cost" type="number" min={0} value={cost} onChange={(e) => setCost(Number(e.target.value))} />
          <div className="sm:col-span-2"><Textarea label="Description" rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} /></div>
          <Input label="City" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Leave blank = everywhere" />
          <Input label="State" value={state} onChange={(e) => setState(e.target.value)} />
          <Input label="Quantity (blank = unlimited)" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />
          <Select label="Redemption type" value={rtype} onChange={(e) => setRtype(e.target.value as 'code' | 'qr' | 'manual')}
            options={[{ value: 'code', label: 'Code' }, { value: 'qr', label: 'QR' }, { value: 'manual', label: 'Manual' }]} />
          <div className="sm:col-span-2"><Button type="submit" loading={creating}><Plus className="h-4 w-4" /> Add reward</Button></div>
        </form>
      </Card>

      <ErrorText>{err}</ErrorText>

      {loading ? <Spinner /> : listings.length === 0 ? (
        <Empty>No rewards yet. Add one above to fund the marketplace.</Empty>
      ) : (
        <div className="space-y-3">
          {listings.map((l) => (
            <Card key={l.id} className={l.is_active ? '' : 'opacity-60'}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{l.title}</h3>
                    <Chip>{l.points_cost} pts</Chip>
                    {!l.is_active && <Chip tone="negative">inactive</Chip>}
                  </div>
                  <p className="text-xs text-tu-faint">
                    {[l.city, l.state].filter(Boolean).join(', ') || 'Everywhere'} · {l.quantity_claimed} claimed
                    {l.quantity_total != null ? ` / ${l.quantity_total}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="soft" onClick={() => setOpen(open === l.id ? null : l.id)}>Redemptions</Button>
                  <Button variant="soft" onClick={() => toggle(l)}>{l.is_active ? 'Deactivate' : 'Activate'}</Button>
                  <Button variant="ghost" onClick={() => remove(l)} className="text-tu-bad">Delete</Button>
                </div>
              </div>
              {open === l.id && (
                <div className="mt-4 rounded-lg border border-tu-border">
                  <RedemptionsPanel listingId={l.id} />
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
