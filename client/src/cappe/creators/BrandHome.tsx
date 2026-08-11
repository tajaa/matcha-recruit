import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BadgeCheck, BriefcaseBusiness, Handshake, Loader2, Search, Send, Sparkles, Target,
} from 'lucide-react'
import { cappeApi, fetchPublicCreator, fetchPublicCreators } from '../api'
import { useCappeMe } from '../hooks/useCappeMe'
import { badgeFor, ui } from '../components/ui'
import {
  CREATOR_NICHES, fmtCents,
  type Campaign,
  type OfferListItem,
  type PublicCreatorCard,
  type PublicCreatorProfile,
} from '../types'
import { brandCollabPath, creatorPaths, creatorProfilePath } from './creatorPaths'
import SendOfferSheet from './SendOfferSheet'

const MIN_FOLLOWERS_OPTIONS = [
  { value: '', label: 'Any reach' },
  { value: '1000', label: '1k+' },
  { value: '10000', label: '10k+' },
  { value: '50000', label: '50k+' },
  { value: '100000', label: '100k+' },
  { value: '500000', label: '500k+' },
]

const MAX_RATE_OPTIONS = [
  { value: '', label: 'Any rate' },
  { value: '10000', label: '< $100' },
  { value: '25000', label: '< $250' },
  { value: '50000', label: '< $500' },
  { value: '100000', label: '< $1k' },
]

const PAGE_SIZE = 8
const compact = (n: number) => Intl.NumberFormat('en-US', { notation: 'compact' }).format(n)

function Stat({ icon: Icon, label, value }: { icon: typeof Target; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4">
      <Icon className="mb-3 h-4 w-4 text-lime-300" />
      <p className="text-2xl font-semibold tracking-tight text-zinc-50">{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{label}</p>
    </div>
  )
}

function CreatorResult({ creator, onOffer, busy }: {
  creator: PublicCreatorCard
  onOffer: (handle: string) => void
  busy: boolean
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900/75">
      <Link
        to={creatorProfilePath(creator.handle)}
        className="block h-28 bg-zinc-800"
        style={creator.cover_url ? { backgroundImage: `url(${creator.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined}
      />
      <div className="p-4">
        <div className="flex items-start gap-3">
          <Link to={creatorProfilePath(creator.handle)} className="h-14 w-14 shrink-0 overflow-hidden rounded-full border-2 border-zinc-950 bg-zinc-800">
            {creator.avatar_url && <img src={creator.avatar_url} alt={creator.display_name} className="h-full w-full object-cover" />}
          </Link>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <Link to={creatorProfilePath(creator.handle)} className="truncate text-sm font-semibold text-zinc-100 hover:text-lime-300">
                {creator.display_name}
              </Link>
              {creator.reach_verified && <BadgeCheck className="h-4 w-4 shrink-0 text-lime-300" />}
            </div>
            <p className="truncate text-xs text-zinc-500">@{creator.handle}</p>
            <p className="mt-1 text-xs text-zinc-500">
              {creator.max_followers > 0 ? `${compact(creator.max_followers)} followers` : 'Reach not listed'}
              {creator.min_rate_cents != null ? ` · from ${fmtCents(creator.min_rate_cents)}` : ''}
            </p>
          </div>
        </div>
        {creator.bio && <p className="mt-3 line-clamp-2 text-sm leading-5 text-zinc-400">{creator.bio}</p>}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {creator.niches.slice(0, 4).map((n) => (
            <span key={n} className="rounded bg-zinc-800 px-2 py-1 text-[11px] text-zinc-400">{n}</span>
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2">
          <button onClick={() => onOffer(creator.handle)} disabled={busy} className={ui.btnPrimary}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Send offer
          </button>
          <Link to={creatorProfilePath(creator.handle)} className={ui.btnGhost}>View profile</Link>
        </div>
      </div>
    </div>
  )
}

export default function BrandHome() {
  const { account } = useCappeMe()
  const [qInput, setQInput] = useState('')
  const [q, setQ] = useState('')
  const [niche, setNiche] = useState('')
  const [platform, setPlatform] = useState('')
  const [minFollowers, setMinFollowers] = useState('')
  const [maxRateCents, setMaxRateCents] = useState('')
  // Approval makes a creator discoverable. Reach verification is a useful
  // refinement, not a second hidden publication gate.
  const [verifiedOnly, setVerifiedOnly] = useState(false)
  const [creators, setCreators] = useState<PublicCreatorCard[]>([])
  const [total, setTotal] = useState(0)
  const [loadingCreators, setLoadingCreators] = useState(true)
  const [creatorError, setCreatorError] = useState<string | null>(null)
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [offers, setOffers] = useState<OfferListItem[]>([])
  const [loadingOfferHandle, setLoadingOfferHandle] = useState<string | null>(null)
  const [offerProfile, setOfferProfile] = useState<PublicCreatorProfile | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setQ(qInput.trim()), 300)
    return () => clearTimeout(t)
  }, [qInput])

  const requestSeq = useRef(0)
  useEffect(() => {
    const seq = ++requestSeq.current
    setLoadingCreators(true)
    setCreatorError(null)
    fetchPublicCreators({
      q: q || undefined,
      niche: niche || undefined,
      platform: platform || undefined,
      min_followers: minFollowers ? Number(minFollowers) : undefined,
      max_rate_cents: maxRateCents ? Number(maxRateCents) : undefined,
      verified_only: verifiedOnly || undefined,
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((res) => {
        if (seq !== requestSeq.current) return
        setCreators(res.creators)
        setTotal(res.total)
      })
      .catch((err: Error) => {
        if (seq !== requestSeq.current) return
        setCreatorError(err.message || 'Could not load creators.')
        setCreators([])
        setTotal(0)
      })
      .finally(() => { if (seq === requestSeq.current) setLoadingCreators(false) })
  }, [q, niche, platform, minFollowers, maxRateCents, verifiedOnly])

  useEffect(() => {
    cappeApi.get<Campaign[]>('/collab/campaigns').then(setCampaigns).catch(() => setCampaigns([]))
    cappeApi.get<{ offers: OfferListItem[]; total: number }>('/collab/offers?side=brand')
      .then((res) => setOffers(res.offers))
      .catch(() => setOffers([]))
  }, [])

  async function openOffer(handle: string) {
    setLoadingOfferHandle(handle)
    try {
      setOfferProfile(await fetchPublicCreator(handle))
    } finally {
      setLoadingOfferHandle(null)
    }
  }

  const activeOffers = offers.filter((o) => ['sent', 'negotiating', 'accepted', 'active'].includes(o.status)).length
  const campaignCount = campaigns.filter((c) => c.status === 'active').length
  const rateCreators = creators.filter((c) => c.min_rate_cents != null)
  const averageRate = rateCreators.length
    ? rateCreators.reduce((sum, c) => sum + (c.min_rate_cents ?? 0), 0) / rateCreators.length
    : 0

  if (account && account.account_type !== 'business') return null

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-8 rounded-lg border border-zinc-800 bg-zinc-900 px-6 py-6">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-lime-300/20 bg-lime-300/10 px-3 py-1 text-xs font-medium text-lime-200">
              <BriefcaseBusiness className="h-3.5 w-3.5" /> Brand profile
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-zinc-50">
              {account?.name || 'Your brand'} creator workspace
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-400">
              Search vetted Gummfit Creators, build campaigns, and send collaboration offers from the same place.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to={creatorPaths.brandCollabs} className={ui.btnGhost}><Handshake className="h-4 w-4" /> Collabs</Link>
            <Link to={creatorPaths.directory} className={ui.btnPrimary}><Search className="h-4 w-4" /> Full directory</Link>
          </div>
        </div>
      </div>

      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <Stat icon={Target} label="Active campaigns" value={String(campaignCount)} />
        <Stat icon={Handshake} label="Open offers" value={String(activeOffers)} />
        <Stat icon={Sparkles} label="Avg visible starter rate" value={averageRate > 0 ? fmtCents(Math.round(averageRate)) : 'N/A'} />
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <section>
          <div className="mb-4 flex flex-col gap-3 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
            <div className="flex items-center gap-2">
              <Search className="h-4 w-4 text-zinc-500" />
              <input
                value={qInput}
                onChange={(e) => setQInput(e.target.value)}
                placeholder="Search creators by name, handle, or bio"
                className="min-w-0 flex-1 bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <select value={niche} onChange={(e) => setNiche(e.target.value)} className={`${ui.input} w-auto`}>
                <option value="">All niches</option>
                {CREATOR_NICHES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <select value={platform} onChange={(e) => setPlatform(e.target.value)} className={`${ui.input} w-auto`}>
                <option value="">All platforms</option>
                <option value="instagram">Instagram</option>
                <option value="tiktok">TikTok</option>
                <option value="youtube">YouTube</option>
                <option value="x">X</option>
                <option value="twitch">Twitch</option>
              </select>
              <select value={minFollowers} onChange={(e) => setMinFollowers(e.target.value)} className={`${ui.input} w-auto`}>
                {MIN_FOLLOWERS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <select value={maxRateCents} onChange={(e) => setMaxRateCents(e.target.value)} className={`${ui.input} w-auto`}>
                {MAX_RATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <label className="flex items-center gap-2 rounded-lg border border-zinc-800 px-3 py-2 text-sm text-zinc-400">
                <input type="checkbox" checked={verifiedOnly} onChange={(e) => setVerifiedOnly(e.target.checked)} />
                Verified reach
              </label>
            </div>
          </div>

          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-zinc-50">Creators to collaborate with</h2>
            <span className="text-xs text-zinc-500">{total} match{total === 1 ? '' : 'es'}</span>
          </div>

          {loadingCreators ? (
            <div className="flex items-center gap-2 py-16 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading creators...</div>
          ) : creatorError ? (
            <p className="py-16 text-sm text-zinc-500">{creatorError}</p>
          ) : creators.length === 0 ? (
            <p className="py-16 text-sm text-zinc-500">No creators match those filters.</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {creators.map((creator) => (
                <CreatorResult
                  key={creator.handle}
                  creator={creator}
                  onOffer={openOffer}
                  busy={loadingOfferHandle === creator.handle}
                />
              ))}
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-100">Recent offers</h2>
              <Link to={creatorPaths.brandCollabs} className="text-xs font-medium text-lime-300 hover:text-lime-200">View all</Link>
            </div>
            {offers.length === 0 ? (
              <p className="text-sm text-zinc-500">No offers yet. Search creators and send your first brief.</p>
            ) : (
              <div className="space-y-3">
                {offers.slice(0, 5).map((offer) => (
                  <Link key={offer.id} to={brandCollabPath(offer.id)} className="block rounded-lg border border-zinc-800 p-3 hover:border-zinc-700">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium text-zinc-200">{offer.title}</p>
                      <span className={badgeFor(offer.status)}>{offer.status.replace('_', ' ')}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-zinc-500">@{offer.creator_handle} · {offer.total_cents != null ? fmtCents(offer.total_cents, offer.currency) : 'No comp listed'}</p>
                  </Link>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-100">Campaigns</h2>
              <Link to={creatorPaths.brandCollabs} className="text-xs font-medium text-lime-300 hover:text-lime-200">Manage</Link>
            </div>
            {campaigns.length === 0 ? (
              <p className="text-sm text-zinc-500">Create campaigns from Collabs or while sending an offer.</p>
            ) : (
              <div className="space-y-2">
                {campaigns.slice(0, 4).map((campaign) => (
                  <div key={campaign.id} className="rounded-lg bg-zinc-950 p-3">
                    <p className="truncate text-sm font-medium text-zinc-200">{campaign.title}</p>
                    <p className="mt-1 text-xs text-zinc-500">{campaign.offer_count} offer{campaign.offer_count === 1 ? '' : 's'}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>

      {offerProfile && (
        <SendOfferSheet
          profile={offerProfile}
          onClose={() => setOfferProfile(null)}
          onSent={() => setOfferProfile(null)}
        />
      )}
    </div>
  )
}
