import { useEffect, useState } from 'react'
import { QRCodeCanvas } from 'qrcode.react'
import { Copy, Plus, QrCode, Trash2 } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Empty, ErrorText, Input, Select, Spinner } from '../../components/ui'
import type { FeedbackLink, Store } from '../../api/types'

function intakeUrl(token: string) {
  return `${window.location.origin}/tellus/i/${token}`
}

export default function BrandStores() {
  const [stores, setStores] = useState<Store[]>([])
  const [links, setLinks] = useState<FeedbackLink[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  // new store
  const [storeName, setStoreName] = useState('')
  const [storeCity, setStoreCity] = useState('')
  const [storeState, setStoreState] = useState('')
  const [addingStore, setAddingStore] = useState(false)

  // new link
  const [linkStore, setLinkStore] = useState('')
  const [linkLabel, setLinkLabel] = useState('')
  const [addingLink, setAddingLink] = useState(false)

  const [qrToken, setQrToken] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    const [s, l] = await Promise.all([
      tellusApi.get<Store[]>('/stores'),
      tellusApi.get<FeedbackLink[]>('/links'),
    ])
    setStores(s); setLinks(l); setLoading(false)
  }
  useEffect(() => { void load() }, [])

  async function addStore(e: React.FormEvent) {
    e.preventDefault(); setErr(''); setAddingStore(true)
    try {
      await tellusApi.post('/stores', { name: storeName, city: storeCity || null, state: storeState || null })
      setStoreName(''); setStoreCity(''); setStoreState(''); await load()
    } catch (e) { setErr(e instanceof Error ? e.message : 'Could not add store') } finally { setAddingStore(false) }
  }

  async function addLink(e: React.FormEvent) {
    e.preventDefault(); setErr(''); setAddingLink(true)
    try {
      await tellusApi.post('/links', { store_id: linkStore || null, label: linkLabel || null })
      setLinkLabel(''); setLinkStore(''); await load()
    } catch (e) { setErr(e instanceof Error ? e.message : 'Could not create link') } finally { setAddingLink(false) }
  }

  async function revoke(id: string) {
    if (!confirm('Revoke this link? Its QR code will stop working.')) return
    await tellusApi.post(`/links/${id}/revoke`); await load()
  }

  async function deleteStore(id: string) {
    if (!confirm('Delete this store and its links?')) return
    await tellusApi.delete(`/stores/${id}`); await load()
  }

  if (loading) return <Spinner />

  return (
    <div className="space-y-8">
      <ErrorText>{err}</ErrorText>

      {/* Stores */}
      <section className="space-y-4">
        <h1 className="text-lg font-bold">Stores</h1>
        <Card>
          <form onSubmit={addStore} className="grid gap-3 sm:grid-cols-4">
            <div className="sm:col-span-2"><Input label="Store name" required value={storeName} onChange={(e) => setStoreName(e.target.value)} /></div>
            <Input label="City" value={storeCity} onChange={(e) => setStoreCity(e.target.value)} />
            <div className="flex items-end gap-2">
              <div className="flex-1"><Input label="State" value={storeState} onChange={(e) => setStoreState(e.target.value)} /></div>
              <Button type="submit" loading={addingStore}><Plus className="h-4 w-4" /></Button>
            </div>
          </form>
        </Card>
        {stores.length === 0 ? <Empty>No stores yet.</Empty> : (
          <div className="grid gap-3 sm:grid-cols-2">
            {stores.map((s) => (
              <Card key={s.id} className="flex items-center justify-between">
                <div>
                  <p className="font-semibold">{s.name}</p>
                  <p className="text-xs text-tu-faint">{[s.city, s.state].filter(Boolean).join(', ') || 'No location'}</p>
                </div>
                <button onClick={() => deleteStore(s.id)} className="text-tu-faint hover:text-tu-bad"><Trash2 className="h-4 w-4" /></button>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Links */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold">Feedback QR links</h2>
        <Card>
          <form onSubmit={addLink} className="grid gap-3 sm:grid-cols-4">
            <div className="sm:col-span-2"><Input label="Label" value={linkLabel} onChange={(e) => setLinkLabel(e.target.value)} placeholder="e.g. Front counter" /></div>
            <Select label="Store (optional)" value={linkStore} onChange={(e) => setLinkStore(e.target.value)}
              options={[{ value: '', label: 'No specific store' }, ...stores.map((s) => ({ value: s.id, label: s.name }))]} />
            <div className="flex items-end">
              <Button type="submit" loading={addingLink} className="w-full"><QrCode className="h-4 w-4" /> Create</Button>
            </div>
          </form>
        </Card>

        {links.length === 0 ? <Empty>No links yet. Create one to generate a QR code.</Empty> : (
          <div className="space-y-3">
            {links.map((l) => (
              <Card key={l.id} className={l.is_active ? '' : 'opacity-50'}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">{l.label || 'Feedback link'}</p>
                    <p className="text-xs text-tu-faint">{l.store_name || 'All stores'} · {l.use_count} responses{l.max_uses ? ` / ${l.max_uses}` : ''}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="soft" onClick={() => setQrToken(qrToken === l.token ? null : l.token)}><QrCode className="h-4 w-4" /> QR</Button>
                    <Button variant="soft" onClick={() => navigator.clipboard.writeText(intakeUrl(l.token))}><Copy className="h-4 w-4" /></Button>
                    {l.is_active && <Button variant="ghost" onClick={() => revoke(l.id)} className="text-tu-bad">Revoke</Button>}
                  </div>
                </div>
                {qrToken === l.token && (
                  <div className="mt-4 flex flex-col items-center gap-2 border-t border-tu-border pt-4">
                    <div className="rounded-xl bg-white p-3"><QRCodeCanvas value={intakeUrl(l.token)} size={160} /></div>
                    <p className="break-all text-center text-xs text-tu-faint">{intakeUrl(l.token)}</p>
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
