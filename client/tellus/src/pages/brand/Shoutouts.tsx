import { useEffect, useState } from 'react'
import { Check, Clipboard, ExternalLink, Eye, Link2, Plus, Search, ShieldCheck, X } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { shoutoutApi } from '../../api/shoutouts'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, Empty, ErrorText, Input, Select, Spinner, Textarea } from '../../components/ui'
import type {
  LoyaltySocialSubmission,
  ShoutoutConfig,
  ShoutoutHandle,
  ShoutoutMention,
  ShoutoutOffer,
  ShoutoutPlatform,
  Store,
} from '../../api/types'

const PLATFORMS: { value: ShoutoutPlatform; label: string }[] = [
  { value: 'instagram', label: 'Instagram' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'x', label: 'X' },
]

const EMPTY_CONFIG: ShoutoutConfig = {
  is_enabled: false, brand_terms: [], exclude_terms: [], default_store_id: null,
  offer_title: null, offer_terms: null, offer_expiry_days: 14, min_confidence: 60,
  lookback_days: 14, handles: [],
  platform_coverage: { instagram: 'partial', tiktok: 'poor', youtube: 'good', facebook: 'partial', x: 'good' },
  last_scanned_at: null, next_scan_after: null,
}

function splitTerms(value: string) {
  return [...new Set(value.split(',').map((term) => term.trim()).filter(Boolean))]
}

function joinTerms(values: string[]) {
  return values.join(', ')
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Never'
}

function MentionRow({ brandId, mention, stores, defaults, onChange }: {
  brandId: string
  mention: ShoutoutMention
  stores: Store[]
  defaults: ShoutoutConfig
  onChange: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [offerOpen, setOfferOpen] = useState(false)
  const [storeId, setStoreId] = useState(defaults.default_store_id ?? '')
  const [title, setTitle] = useState(defaults.offer_title ?? '')
  const [terms, setTerms] = useState(defaults.offer_terms ?? '')
  const [expiryDays, setExpiryDays] = useState(defaults.offer_expiry_days)

  async function decide(decision: 'approve' | 'reject') {
    setBusy(true); setError('')
    try {
      if (decision === 'approve') {
        const offer = await shoutoutApi.approve(brandId, mention.id, {
          store_id: storeId || null, title, terms: terms || null, expiry_days: expiryDays,
        })
        await navigator.clipboard.writeText(offer.claim_url)
        alert('Offer created and link copied. Send it to the customer manually.')
        setOfferOpen(false)
      } else {
        await shoutoutApi.reject(brandId, mention.id)
      }
      onChange()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update this mention')
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2 border-b border-tu-border px-4 py-4 last:border-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Chip>{mention.platform}</Chip>
            <Chip tone={mention.confidence >= 80 ? 'positive' : undefined}>{mention.confidence}% confidence</Chip>
            {mention.author_handle && <span className="text-xs text-tu-faint">@{mention.author_handle}</span>}
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-tu-dim">{mention.excerpt || 'No excerpt returned.'}</p>
          {mention.matched_terms.length > 0 && <p className="mt-1 text-xs text-tu-faint">Matched: {mention.matched_terms.join(', ')}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <a href={mention.post_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-tu-accent hover:underline">
            Open post <ExternalLink className="h-3.5 w-3.5" />
          </a>
          <Button size="sm" loading={busy} onClick={() => setOfferOpen(true)}><Check className="h-3.5 w-3.5" /> Send offer</Button>
          <Button size="sm" variant="danger" loading={busy} onClick={() => void decide('reject')}><X className="h-3.5 w-3.5" /> Reject</Button>
        </div>
      </div>
      {offerOpen && (
        <div className="mt-3 space-y-3 rounded-lg border border-tu-accent/30 bg-tu-accent/5 p-3">
          <p className="text-sm font-semibold">Configure this thank-you</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Select label="Redeem at" value={storeId} onChange={(e) => setStoreId(e.target.value)} options={[{ value: '', label: 'Choose a store' }, ...stores.map((store) => ({ value: store.id, label: store.name }))]} />
            <Input label="Reward title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="A thank-you from us" />
          </div>
          <Textarea label="Terms (optional)" rows={2} value={terms} onChange={(e) => setTerms(e.target.value)} />
          <Input label="Expires in days" type="number" min={1} max={365} value={expiryDays} onChange={(e) => setExpiryDays(Number(e.target.value))} />
          <div className="flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={() => setOfferOpen(false)}>Cancel</Button><Button size="sm" loading={busy} disabled={!storeId || !title.trim()} onClick={() => void decide('approve')}><Link2 className="h-3.5 w-3.5" /> Create and copy link</Button></div>
        </div>
      )}
      <ErrorText>{error}</ErrorText>
    </div>
  )
}

function Configuration({ brandId, stores, onSaved }: { brandId: string; stores: Store[]; onSaved: (config: ShoutoutConfig) => void }) {
  const [config, setConfig] = useState<ShoutoutConfig>(EMPTY_CONFIG)
  const [brandTerms, setBrandTerms] = useState('')
  const [excludeTerms, setExcludeTerms] = useState('')
  const [platform, setPlatform] = useState<ShoutoutPlatform>('instagram')
  const [handle, setHandle] = useState('')
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let live = true
    shoutoutApi.getConfig(brandId).then((next) => {
      if (!live) return
      setConfig(next); setBrandTerms(joinTerms(next.brand_terms)); setExcludeTerms(joinTerms(next.exclude_terms))
      onSaved(next)
    }).catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load radar configuration') })
    return () => { live = false }
  }, [brandId, onSaved])

  function addHandle() {
    const normalized = handle.trim().replace(/^@/, '').toLowerCase()
    if (!normalized || config.handles.some((item) => item.platform === platform && item.handle === normalized)) return
    setConfig((current) => ({ ...current, handles: [...current.handles, { platform, handle: normalized }] }))
    setHandle('')
  }

  function removeHandle(item: ShoutoutHandle) {
    setConfig((current) => ({ ...current, handles: current.handles.filter((candidate) => candidate !== item) }))
  }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError('')
    try {
      const next = await shoutoutApi.putConfig(brandId, {
        brand_terms: splitTerms(brandTerms), exclude_terms: splitTerms(excludeTerms),
        default_store_id: config.default_store_id, offer_title: config.offer_title,
        offer_terms: config.offer_terms, offer_expiry_days: config.offer_expiry_days,
        min_confidence: config.min_confidence, lookback_days: config.lookback_days, handles: config.handles,
      })
      setConfig(next); onSaved(next)
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save configuration') }
    finally { setSaving(false) }
  }

  async function toggle() {
    setBusy(true); setError('')
    try {
      const next = await shoutoutApi.setEnabled(brandId, !config.is_enabled)
      setConfig(next); onSaved(next)
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not update radar status') }
    finally { setBusy(false) }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2"><Search className="h-4 w-4 text-tu-accent" /><h2 className="font-semibold">Radar configuration</h2></div>
          <p className="mt-1 text-sm text-tu-dim">Find public customer posts. Nothing is sent or awarded until you approve it.</p>
        </div>
        <Button variant={config.is_enabled ? 'soft' : 'primary'} loading={busy} onClick={() => void toggle()}>
          {config.is_enabled ? 'Pause radar' : 'Enable radar'}
        </Button>
      </div>
      <form onSubmit={save} className="mt-5 space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Textarea label="Brand terms (comma separated)" rows={2} value={brandTerms} onChange={(e) => setBrandTerms(e.target.value)} placeholder="brand name, product, campaign" />
          <Textarea label="Exclude terms (comma separated)" rows={2} value={excludeTerms} onChange={(e) => setExcludeTerms(e.target.value)} placeholder="job, giveaway, complaint" />
        </div>
        <div>
          <span className="mb-1 block text-xs font-medium text-tu-dim">Brand handles</span>
          <div className="flex flex-wrap gap-2">
            {config.handles.map((item) => <Chip key={`${item.platform}:${item.handle}`}><button type="button" onClick={() => removeHandle(item)} className="mr-1 hover:text-tu-bad">×</button>{item.platform}: @{item.handle}</Chip>)}
          </div>
          <div className="mt-2 flex gap-2">
            <Select value={platform} onChange={(e) => setPlatform(e.target.value as ShoutoutPlatform)} options={PLATFORMS} />
            <Input value={handle} onChange={(e) => setHandle(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addHandle() } }} placeholder="@yourbrand" />
            <Button type="button" variant="soft" onClick={addHandle}><Plus className="h-4 w-4" /> Add</Button>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Select label="Default reward store" value={config.default_store_id ?? ''} onChange={(e) => setConfig((current) => ({ ...current, default_store_id: e.target.value || null }))}
            options={[{ value: '', label: 'Select a store' }, ...stores.map((store) => ({ value: store.id, label: `${store.name}${store.city ? ` · ${store.city}` : ''}` }))]} />
          <Input label="Reward title" value={config.offer_title ?? ''} onChange={(e) => setConfig((current) => ({ ...current, offer_title: e.target.value || null }))} placeholder="A thank-you from us" />
        </div>
        <Textarea label="Reward terms (optional)" rows={2} value={config.offer_terms ?? ''} onChange={(e) => setConfig((current) => ({ ...current, offer_terms: e.target.value || null }))} placeholder="One per customer. Redeem at the selected store." />
        <div className="grid gap-3 sm:grid-cols-3">
          <Input label="Offer expires in days" type="number" min={1} max={365} value={config.offer_expiry_days} onChange={(e) => setConfig((current) => ({ ...current, offer_expiry_days: Number(e.target.value) }))} />
          <Input label="Minimum confidence" type="number" min={0} max={100} value={config.min_confidence} onChange={(e) => setConfig((current) => ({ ...current, min_confidence: Number(e.target.value) }))} />
          <Input label="Look back (days)" type="number" min={1} max={90} value={config.lookback_days} onChange={(e) => setConfig((current) => ({ ...current, lookback_days: Number(e.target.value) }))} />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-tu-faint">Last scan: {formatDate(config.last_scanned_at)} · Google Search grounding only</p>
          <Button type="submit" loading={saving}><ShieldCheck className="h-4 w-4" /> Save configuration</Button>
        </div>
        <ErrorText>{error}</ErrorText>
      </form>
    </Card>
  )
}

function OfferList({ brandId, offers, onChange }: { brandId: string; offers: ShoutoutOffer[]; onChange: () => void }) {
  async function revoke(offer: ShoutoutOffer) {
    if (!confirm('Revoke this offer? The customer will no longer be able to claim it.')) return
    try { await shoutoutApi.revokeOffer(brandId, offer.id); onChange() }
    catch (e) { alert(e instanceof Error ? e.message : 'Could not revoke offer') }
  }
  if (!offers.length) return <Empty>No approved offers yet.</Empty>
  return <div className="space-y-2">{offers.map((offer) => (
    <div key={offer.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-tu-border px-3 py-3">
      <div><p className="font-medium">{offer.reward_text}</p><p className="text-xs text-tu-faint">{offer.store_name || 'Store'} · code {offer.short_code} · expires {new Date(offer.claim_expires_at).toLocaleDateString()}</p></div>
      <div className="flex items-center gap-2"><Chip tone={offer.status === 'claimed' ? 'positive' : offer.status === 'revoked' ? 'negative' : undefined}>{offer.status}</Chip><Button size="sm" variant="soft" onClick={() => navigator.clipboard.writeText(offer.claim_url)}><Clipboard className="h-3.5 w-3.5" /> Copy link</Button>{offer.status !== 'revoked' && <Button size="sm" variant="ghost" onClick={() => void revoke(offer)}>Revoke</Button>}</div>
    </div>
  ))}</div>
}

function SocialSubmissions({ brandId }: { brandId: string }) {
  const [rows, setRows] = useState<LoyaltySocialSubmission[]>([])
  const [loading, setLoading] = useState(true)
  async function load() { try { setRows(await shoutoutApi.socialSubmissions(brandId)) } finally { setLoading(false) } }
  useEffect(() => { void load() }, [brandId])
  async function decide(id: string, decision: 'approve' | 'reject') { await shoutoutApi.decideSocial(brandId, id, decision); await load() }
  return <Card><div className="flex items-center gap-2"><Eye className="h-4 w-4 text-tu-accent" /><h2 className="font-semibold">Customer-submitted posts</h2></div><p className="mt-1 text-sm text-tu-dim">Separate from radar detections. These are customer-submitted loyalty entries and their existing points workflow.</p>{loading ? <Spinner /> : rows.length === 0 ? <Empty>No customer submissions.</Empty> : <div className="mt-4 divide-y divide-tu-border">{rows.map((row) => <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="font-medium">{row.platform} · {row.status}</p><a className="text-xs text-tu-accent hover:underline" href={row.post_url} target="_blank" rel="noreferrer">{row.post_url}</a></div>{row.status === 'pending' && <div className="flex gap-2"><Button size="sm" onClick={() => void decide(row.id, 'approve')}>Approve</Button><Button size="sm" variant="danger" onClick={() => void decide(row.id, 'reject')}>Reject</Button></div>}</div>)}</div>}</Card>
}

export default function BrandShoutouts() {
  const { brandId } = useParams()
  const [stores, setStores] = useState<Store[]>([])
  const [mentions, setMentions] = useState<ShoutoutMention[]>([])
  const [offers, setOffers] = useState<ShoutoutOffer[]>([])
  const [radarConfig, setRadarConfig] = useState<ShoutoutConfig>(EMPTY_CONFIG)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  if (!brandId) return <ErrorText>Business not found.</ErrorText>
  const currentBrandId = brandId

  async function loadQueue() {
    try {
      const [nextMentions, nextOffers] = await Promise.all([shoutoutApi.listMentions(currentBrandId), shoutoutApi.listOffers(currentBrandId)])
      setMentions(nextMentions); setOffers(nextOffers)
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not load shoutouts') }
    finally { setLoading(false) }
  }
  useEffect(() => { void Promise.all([tellusApi.get<Store[]>('/stores'), loadQueue()]).then(([nextStores]) => setStores(nextStores)).catch((e) => setError(e instanceof Error ? e.message : 'Could not load shoutouts')) }, [brandId])

  return <div className="space-y-6"><div><div className="flex items-center gap-2"><Link2 className="h-5 w-5 text-tu-accent" /><h1 className="text-xl font-bold">Shoutouts</h1></div><p className="mt-1 text-sm text-tu-dim">Turn verified public customer love into a store-bound thank-you, one approval at a time.</p></div><ErrorText>{error}</ErrorText><Configuration brandId={brandId} stores={stores} onSaved={setRadarConfig} /><section className="space-y-3"><div className="flex items-center justify-between"><div><h2 className="font-semibold">Review queue</h2><p className="text-sm text-tu-dim">Only grounded mentions appear here.</p></div><Chip>{mentions.length} pending</Chip></div>{loading ? <Spinner /> : mentions.length === 0 ? <Empty>No pending mentions. Enable the radar to start searching.</Empty> : <Card className="p-0"><div>{mentions.map((mention) => <MentionRow key={mention.id} brandId={brandId} mention={mention} stores={stores} defaults={radarConfig} onChange={() => void loadQueue()} />)}</div></Card>}</section><section className="space-y-3"><div><h2 className="font-semibold">Approved offers</h2><p className="text-sm text-tu-dim">Copy the link and send it manually to the customer.</p></div><OfferList brandId={brandId} offers={offers} onChange={() => void loadQueue()} /></section><SocialSubmissions brandId={brandId} /></div>
}
