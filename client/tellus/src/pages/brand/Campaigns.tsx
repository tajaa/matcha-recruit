import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { QRCodeCanvas } from 'qrcode.react'
import { Ban, Copy, MapPin, Pause, Palette, Play, Plus, QrCode, ScanLine, Trash2 } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { promoApi } from '../../api/promo'
import { Button, Card, Chip, Empty, ErrorText, Input, Modal, Select, Spinner, Textarea } from '../../components/ui'
import type { PromoCampaign, ScannerDevice, Store } from '../../api/types'

function absoluteUrl(path: string) {
  return `${window.location.origin}${path}`
}

function campaignTone(status: PromoCampaign['status']): string | undefined {
  if (status === 'active') return 'positive'
  if (status === 'cancelled') return 'negative'
  return undefined
}

function CreateCampaignModal({ open, onClose, onCreated, stores }: {
  open: boolean
  onClose: () => void
  onCreated: (created: PromoCampaign) => void
  stores: Store[]
}) {
  const [title, setTitle] = useState('')
  const [rewardText, setRewardText] = useState('')
  const [description, setDescription] = useState('')
  // Kept as strings, not numbers: Number('') is 0, so clearing the field to
  // retype it used to POST max_claims: 0, fail the backend's ge=1, and surface
  // FastAPI's raw validation array. Parsed and range-checked on submit.
  const [maxClaims, setMaxClaims] = useState('50')
  const [expiryDays, setExpiryDays] = useState('30')
  const [endsAt, setEndsAt] = useState('')
  const [campaignType, setCampaignType] = useState<'qr' | 'location'>('qr')
  const [storeId, setStoreId] = useState('')
  const [radiusMiles, setRadiusMiles] = useState(5)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  function reset() {
    setTitle(''); setRewardText(''); setDescription(''); setMaxClaims('50'); setExpiryDays('30'); setEndsAt('')
    setCampaignType('qr'); setStoreId(''); setRadiusMiles(5); setErr('')
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    const claims = Number(maxClaims)
    const days = Number(expiryDays)
    if (!Number.isInteger(claims) || claims < 1 || claims > 10000) {
      setErr('Claim limit must be a whole number between 1 and 10,000.'); return
    }
    if (!Number.isInteger(days) || days < 1 || days > 365) {
      setErr('Card validity must be a whole number of days between 1 and 365.'); return
    }
    setSaving(true)
    try {
      const created = await promoApi.createCampaign({
        title, reward_text: rewardText, description: description || null,
        max_claims: claims, card_expiry_days: days,
        ends_at: endsAt ? new Date(endsAt).toISOString() : null,
        campaign_type: campaignType,
        store_id: campaignType === 'location' ? storeId : null,
        radius_miles: campaignType === 'location' ? radiusMiles : null,
      })
      reset(); onClose(); onCreated(created)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not create campaign')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={() => { reset(); onClose() }} title="New promo campaign">
      <form onSubmit={submit} className="space-y-3">
        <Input label="Title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Today only: free coffee" />
        <Input label="Reward" required value={rewardText} onChange={(e) => setRewardText(e.target.value)}
          placeholder="What the card is good for, e.g. One free coffee" />
        <Textarea label="Description (optional)" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        <Select label="Campaign type" value={campaignType} onChange={(e) => setCampaignType(e.target.value as 'qr' | 'location')}
          options={[{ value: 'qr', label: 'QR campaign' }, { value: 'location', label: 'Location campaign' }]} />
        {campaignType === 'location' && (
          <div className="space-y-3 rounded-lg border border-tu-border p-3">
            <Select label="Store location" value={storeId} onChange={(e) => setStoreId(e.target.value)}
              options={[{ value: '', label: 'Select a store' }, ...stores.map((s) => ({ value: s.id, label: `${s.name}${s.city ? ` · ${s.city}` : ''}` }))]}
              required />
            <label className="block text-sm">
              <span className="mb-1 block text-tu-dim">Push radius: {radiusMiles} miles</span>
              <input className="w-full accent-tu-accent" type="range" min={1} max={10} step={0.5}
                value={radiusMiles} onChange={(e) => setRadiusMiles(Number(e.target.value))} />
            </label>
            <p className="text-xs text-tu-faint">Only followers with a fresh device location inside this radius can receive and claim it.</p>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Input label="Claim limit" type="number" min={1} max={10000} value={maxClaims}
            onChange={(e) => setMaxClaims(e.target.value)} />
          <Input label="Card valid for (days)" type="number" min={1} max={365} value={expiryDays}
            onChange={(e) => setExpiryDays(e.target.value)} />
        </div>
        <Input label="Ends (optional)" type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
        <ErrorText>{err}</ErrorText>
        <Button type="submit" loading={saving} disabled={campaignType === 'location' && !storeId} className="w-full"><Plus className="h-4 w-4" /> Create campaign</Button>
      </form>
    </Modal>
  )
}

function CampaignCard({ campaign, onChanged }: { campaign: PromoCampaign; onChanged: () => void }) {
  const navigate = useNavigate()
  const [showQr, setShowQr] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState('')
  const claimUrl = absoluteUrl(campaign.claim_url)
  const isLocation = campaign.campaign_type === 'location'

  async function togglePause() {
    setBusy(true); setErr('')
    try {
      await promoApi.patchCampaign(campaign.id, { status: campaign.status === 'active' ? 'paused' : 'active' })
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not update campaign')
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    if (!confirm('Cancel this campaign? Every unredeemed card is invalidated immediately.')) return
    setBusy(true); setErr(''); setResult('')
    try {
      const { invalidated_count } = await promoApi.cancelCampaign(campaign.id)
      setResult(`Campaign cancelled. ${invalidated_count} outstanding card(s) invalidated.`)
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not cancel campaign')
    } finally {
      setBusy(false)
    }
  }

  async function push() {
    if (!confirm(`Push this offer to followers within ${campaign.radius_miles} miles of ${campaign.store_name}?`)) return
    setBusy(true); setErr(''); setResult('')
    try {
      const result = await promoApi.pushCampaign(campaign.id)
      setResult(
        result.pushed
          ? `Pushed to ${result.sent_count} follower${result.sent_count === 1 ? '' : 's'} with a fresh in-radius location.`
          : `No followers were near ${campaign.store_name || 'the store'} just now — you can try pushing again later.`
      )
      onChanged()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not push campaign')
    } finally { setBusy(false) }
  }

  const stats = campaign.stats
  return (
    <Card className={campaign.status === 'cancelled' ? 'opacity-60' : ''}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          {campaign.flyer_image_url && (
            <img src={campaign.flyer_image_url} alt="" className="h-20 w-16 shrink-0 rounded border border-tu-border object-cover" />
          )}
          <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold">{campaign.title}</h3>
            <Chip tone={campaignTone(campaign.status)}>{campaign.status}</Chip>
            {isLocation && <Chip tone="positive"><MapPin className="mr-1 inline h-3 w-3" />location · push only</Chip>}
          </div>
          <p className="text-sm text-tu-dim">{campaign.reward_text}</p>
          <p className="mt-1 text-xs text-tu-faint">
            {campaign.claim_count} / {campaign.max_claims} claimed
            {stats ? ` · ${stats.redeemed} redeemed · ${stats.outstanding} outstanding` : ''}
            {campaign.ends_at ? ` · ends ${new Date(campaign.ends_at).toLocaleString()}` : ''}
            {campaign.campaign_type === 'location' ? ` · ${campaign.store_name || 'store'} · ${campaign.radius_miles} mi` : ''}
            {campaign.campaign_type === 'location' && campaign.push_sent_at ? ` · pushed to ${campaign.push_sent_count}` : ''}
          </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {campaign.status !== 'cancelled' && (
            <Button variant="soft" onClick={() => navigate(`/brand/campaigns/${campaign.id}/design`)}>
              <Palette className="h-4 w-4" /> {campaign.has_design ? 'Edit flyer' : 'Design flyer'}
            </Button>
          )}
          {campaign.campaign_type === 'location' && campaign.status === 'active' && !campaign.push_sent_at && (
            <Button variant="soft" loading={busy} onClick={push}><MapPin className="h-4 w-4" /> Push</Button>
          )}
          {!isLocation && (
            <>
              <Button variant="soft" onClick={() => setShowQr((v) => !v)}><QrCode className="h-4 w-4" /> QR</Button>
              <Button variant="soft" onClick={() => navigator.clipboard.writeText(claimUrl)}><Copy className="h-4 w-4" /></Button>
            </>
          )}
          {campaign.status !== 'cancelled' && (
            <Button variant="soft" loading={busy} onClick={togglePause}>
              {campaign.status === 'active' ? <><Pause className="h-4 w-4" /> Pause</> : <><Play className="h-4 w-4" /> Resume</>}
            </Button>
          )}
          {campaign.status !== 'cancelled' && (
            <Button variant="ghost" loading={busy} onClick={cancel} className="text-tu-bad"><Ban className="h-4 w-4" /> Cancel</Button>
          )}
        </div>
      </div>
      <ErrorText>{err}</ErrorText>
      {result && <p className="mt-2 text-xs text-tu-good">{result}</p>}
      {showQr && !isLocation && (
        <div className="mt-4 flex flex-col items-center gap-2 border-t border-tu-border pt-4">
          <div className="rounded-xl bg-white p-3"><QRCodeCanvas value={claimUrl} size={160} /></div>
          <p className="break-all text-center text-xs text-tu-faint">{claimUrl}</p>
        </div>
      )}
    </Card>
  )
}

function ScannersSection() {
  const [stores, setStores] = useState<Store[]>([])
  const [scanners, setScanners] = useState<ScannerDevice[]>([])
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState('')
  const [storeId, setStoreId] = useState('')
  const [label, setLabel] = useState('')
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState('')
  const [qrToken, setQrToken] = useState<string | null>(null)

  async function load() {
    setLoading(true); setLoadErr('')
    try {
      const [s, sc] = await Promise.all([
        tellusApi.get<Store[]>('/stores'),
        promoApi.listScanners(),
      ])
      setStores(s); setScanners(sc)
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : 'Could not load scanners')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { void load() }, [])

  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(''); setCreating(true)
    try {
      await promoApi.createScanner({ store_id: storeId, label: label || undefined })
      setStoreId(''); setLabel(''); await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not create scanner')
    } finally {
      setCreating(false)
    }
  }

  async function revoke(id: string) {
    if (!confirm('Revoke this scanner? The device will stop being able to redeem cards.')) return
    try {
      await promoApi.revokeScanner(id); await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not revoke scanner')
    }
  }

  if (loading) return <Spinner />
  if (loadErr) {
    return (
      <section className="space-y-4">
        <h2 className="text-lg font-bold">Counter scanners</h2>
        <ErrorText>{loadErr}</ErrorText>
        <Button variant="soft" onClick={() => void load()}>Retry</Button>
      </section>
    )
  }

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-bold">Counter scanners</h2>
      {stores.length === 0 ? (
        <Empty>Add a store first (Stores &amp; QR) before minting a scanner.</Empty>
      ) : (
        <Card>
          <form onSubmit={create} className="grid gap-3 sm:grid-cols-4">
            <Select label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}
              options={[{ value: '', label: 'Select a store' }, ...stores.map((s) => ({ value: s.id, label: s.name }))]}
              required />
            <div className="sm:col-span-2"><Input label="Label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Front register" /></div>
            <div className="flex items-end">
              <Button type="submit" loading={creating} className="w-full" disabled={!storeId}><ScanLine className="h-4 w-4" /> Create</Button>
            </div>
          </form>
        </Card>
      )}
      <ErrorText>{err}</ErrorText>

      {scanners.length === 0 ? <Empty>No scanners yet.</Empty> : (
        <div className="space-y-3">
          {scanners.map((sc) => {
            const scannerUrl = absoluteUrl(sc.scanner_url)
            return (
              <Card key={sc.id} className={sc.is_active ? '' : 'opacity-50'}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">{sc.label || 'Scanner'}</p>
                    <p className="text-xs text-tu-faint">{sc.store_name}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="soft" onClick={() => setQrToken(qrToken === sc.token ? null : sc.token)}><QrCode className="h-4 w-4" /> QR</Button>
                    <Button variant="soft" onClick={() => navigator.clipboard.writeText(scannerUrl)}><Copy className="h-4 w-4" /></Button>
                    {sc.is_active && <Button variant="ghost" onClick={() => revoke(sc.id)} className="text-tu-bad"><Trash2 className="h-4 w-4" /></Button>}
                  </div>
                </div>
                {qrToken === sc.token && (
                  <div className="mt-4 flex flex-col items-center gap-2 border-t border-tu-border pt-4">
                    <div className="rounded-xl bg-white p-3"><QRCodeCanvas value={scannerUrl} size={160} /></div>
                    <p className="break-all text-center text-xs text-tu-faint">{scannerUrl}</p>
                    <p className="text-center text-xs text-tu-faint">Open this link on the counter device — no login needed.</p>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </section>
  )
}

export default function BrandCampaigns() {
  const navigate = useNavigate()
  const [campaigns, setCampaigns] = useState<PromoCampaign[]>([])
  const [stores, setStores] = useState<Store[]>([])
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState('')
  const [modalOpen, setModalOpen] = useState(false)

  async function load() {
    setLoading(true); setLoadErr('')
    try {
      const [campaigns, stores] = await Promise.all([
        promoApi.listCampaigns(),
        tellusApi.get<Store[]>('/stores'),
      ])
      setCampaigns(campaigns); setStores(stores)
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : 'Could not load campaigns')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { void load() }, [])

  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold">Promo campaigns</h1>
          <Button onClick={() => setModalOpen(true)}><Plus className="h-4 w-4" /> New campaign</Button>
        </div>

        {loading ? <Spinner /> : loadErr ? (
          <div className="space-y-3">
            <ErrorText>{loadErr}</ErrorText>
            <Button variant="soft" onClick={() => void load()}>Retry</Button>
          </div>
        ) : campaigns.length === 0 ? (
          <Empty>No campaigns yet. Create one to generate a claimable QR flyer.</Empty>
        ) : (
          <div className="space-y-3">
            {campaigns.map((c) => <CampaignCard key={c.id} campaign={c} onChanged={load} />)}
          </div>
        )}
      </section>

      <ScannersSection />

      {/* Straight into the designer after create — a campaign with no flyer is
          a QR nobody can see, so laying one out is the real next step. */}
      <CreateCampaignModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={(created) => navigate(`/brand/campaigns/${created.id}/design`)}
        stores={stores}
      />
    </div>
  )
}
