import { useState } from 'react'
import { MessageCircle, Send } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { tellusApi } from '../api/tellusClient'
import { Button, ErrorText } from './ui'
import type { CommsStartResponse, MessagingStore } from '../api/types'

const TOPICS = [
  ['hours', 'Hours & holiday schedule'], ['availability', 'Availability / reservations'],
  ['inventory', 'Product availability'], ['order', 'Order or pickup'],
  ['service', 'Service question'], ['accessibility', 'Accessibility'], ['other', 'Other'],
] as const

export function BusinessMessageComposer({ slug, stores }: { slug: string; stores: MessagingStore[] }) {
  const navigate = useNavigate()
  const [topic, setTopic] = useState('other')
  const [storeId, setStoreId] = useState(stores.length === 1 ? stores[0].id : '')
  const [body, setBody] = useState('')
  const [clientMessageId, setClientMessageId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  async function send() {
    if (body.trim().length < 1) return
    setBusy(true); setErr('')
    try {
      const id = clientMessageId ?? crypto.randomUUID()
      if (!clientMessageId) setClientMessageId(id)
      const result = await tellusApi.post<CommsStartResponse>(`/comms/brands/${slug}/threads`, {
        store_id: storeId || null, topic, body: body.trim(), client_message_id: id,
      })
      navigate(`/messages?thread=${result.thread.id}`)
    } catch (e) { setErr(e instanceof Error ? e.message : 'Could not send message') }
    finally { setBusy(false) }
  }
  return (
    <div className="mx-auto mt-4 max-w-lg rounded-xl border border-tu-border bg-tu-panel p-4 text-left">
      <div className="flex items-center gap-2"><MessageCircle className="h-4 w-4 text-tu-accent" /><h2 className="text-sm font-semibold">Ask this business a question</h2></div>
      <p className="mt-1 text-xs text-tu-faint">A team member will reply here. Messages are not reservations, purchases, or guarantees of hours, inventory, or availability.</p>
      <div className="mt-3 space-y-2">
        {stores.length > 1 && <select value={storeId} onChange={e => setStoreId(e.target.value)} className="w-full rounded-lg border border-tu-border bg-tu-panel2 px-2.5 py-2 text-sm"><option value="">Any location</option>{stores.map(s => <option key={s.id} value={s.id}>{s.name}{s.city ? ` · ${s.city}` : ''}</option>)}</select>}
        <select value={topic} onChange={e => setTopic(e.target.value)} className="w-full rounded-lg border border-tu-border bg-tu-panel2 px-2.5 py-2 text-sm">{TOPICS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <textarea value={body} onChange={e => { setBody(e.target.value); setClientMessageId(null) }} maxLength={4000} rows={3} placeholder="What would you like to know?" className="w-full rounded-lg border border-tu-border bg-tu-panel2 px-2.5 py-2 text-sm placeholder:text-tu-faint focus:border-tu-accent focus:outline-none" />
        <div className="flex items-center justify-between gap-2"><ErrorText>{err}</ErrorText><div className="ml-auto flex gap-2"><Link to={'/login?returnTo=' + encodeURIComponent(`/b/${slug}`)} className="rounded-lg px-3 py-2 text-xs font-semibold text-tu-dim hover:text-tu-text">Log in</Link><Button size="sm" loading={busy} disabled={!body.trim()} onClick={() => void send()}><Send className="h-3.5 w-3.5" /> Send</Button></div></div>
      </div>
    </div>
  )
}
