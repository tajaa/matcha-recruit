import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BadgeCheck, Loader2 } from 'lucide-react'
import { fetchPublicCreators } from '../api'
import { useCappeMe } from '../hooks/useCappeMe'
import { ui } from '../components/ui'
import { CREATOR_NICHES, type PublicCreatorCard } from '../types'

const MIN_FOLLOWERS_OPTIONS = [
  { value: '', label: 'Any followers' },
  { value: '1000', label: '1k+' },
  { value: '10000', label: '10k+' },
  { value: '50000', label: '50k+' },
  { value: '100000', label: '100k+' },
  { value: '500000', label: '500k+' },
]

const MAX_RATE_OPTIONS = [
  { value: '', label: 'Any rate' },
  { value: '10000', label: 'Under $100' },
  { value: '25000', label: 'Under $250' },
  { value: '50000', label: 'Under $500' },
  { value: '100000', label: 'Under $1k' },
  { value: '500000', label: 'Under $5k' },
]

const PAGE_SIZE = 12

const compactFollowers = (n: number) => Intl.NumberFormat('en-US', { notation: 'compact' }).format(n)

function CreatorCard({ c }: { c: PublicCreatorCard }) {
  return (
    <Link to={`/cappe/creators/${c.handle}`} className={`${ui.cardHover} block overflow-hidden`}>
      <div className="h-24 bg-zinc-800" style={c.cover_url ? { backgroundImage: `url(${c.cover_url})`, backgroundSize: 'cover', backgroundPosition: 'center' } : undefined} />
      <div className="px-4 pb-4">
        <div className="-mt-8 mb-2 h-16 w-16 overflow-hidden rounded-full border-4 border-zinc-900 bg-zinc-800">
          {c.avatar_url && <img src={c.avatar_url} alt={c.display_name} className="h-full w-full object-cover" />}
        </div>
        <div className="flex items-center gap-1.5">
          <p className="truncate text-sm font-semibold text-zinc-100">{c.display_name}</p>
          {c.reach_verified && <BadgeCheck className="h-4 w-4 shrink-0 text-emerald-400" />}
        </div>
        <p className="truncate text-xs text-zinc-500">@{c.handle}</p>
        {c.bio && <p className="mt-2 line-clamp-2 text-xs text-zinc-400">{c.bio}</p>}
        <div className="mt-2 flex flex-wrap gap-1">
          {c.niches.slice(0, 3).map((n) => (
            <span key={n} className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{n}</span>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
          <span>{c.max_followers > 0 ? `${compactFollowers(c.max_followers)} followers` : ' '}</span>
          {c.min_rate_cents != null && <span className="font-medium text-zinc-300">From ${(c.min_rate_cents / 100).toFixed(0)}</span>}
        </div>
      </div>
    </Link>
  )
}

export default function CreatorDirectory() {
  const { account } = useCappeMe()
  const [niche, setNiche] = useState('')
  const [platform, setPlatform] = useState('')
  const [minFollowers, setMinFollowers] = useState('')
  const [maxRateCents, setMaxRateCents] = useState('')
  const [location, setLocation] = useState('')
  const [q, setQ] = useState('')
  const [qInput, setQInput] = useState('')
  const [verifiedOnly, setVerifiedOnly] = useState(false)
  const [page, setPage] = useState(0)
  const [creators, setCreators] = useState<PublicCreatorCard[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Debounce the search text 300ms before it becomes a real filter.
  useEffect(() => {
    const t = setTimeout(() => { setQ(qInput); setPage(0) }, 300)
    return () => clearTimeout(t)
  }, [qInput])

  useEffect(() => { setPage(0) }, [niche, platform, minFollowers, maxRateCents, location, verifiedOnly])

  const requestSeq = useRef(0)
  useEffect(() => {
    const seq = ++requestSeq.current
    setLoading(true)
    setError(null)
    fetchPublicCreators({
      niche: niche || undefined,
      platform: platform || undefined,
      min_followers: minFollowers ? Number(minFollowers) : undefined,
      max_rate_cents: maxRateCents ? Number(maxRateCents) : undefined,
      location: location || undefined,
      q: q || undefined,
      verified_only: verifiedOnly || undefined,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    })
      .then((res) => {
        if (seq !== requestSeq.current) return
        setCreators(res.creators)
        setTotal(res.total)
      })
      .catch((err: Error) => {
        if (seq !== requestSeq.current) return
        setError(err.message || 'Could not load creators.')
        setCreators([])
        setTotal(0)
      })
      .finally(() => { if (seq === requestSeq.current) setLoading(false) })
  }, [niche, platform, minFollowers, maxRateCents, location, q, verifiedOnly, page])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className={ui.page}>
      <div className="mx-auto max-w-6xl px-6 py-10">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h1 className={ui.heading}>Creator directory</h1>
            <p className={ui.subtitle}>Browse creators open to brand collabs.</p>
          </div>
          {account?.account_type === 'business' && (
            <p className="text-sm text-zinc-500">Click a creator to send an offer</p>
          )}
        </div>

        <div className="mb-6 flex flex-wrap items-center gap-2">
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
            <option value="facebook">Facebook</option>
            <option value="linkedin">LinkedIn</option>
          </select>
          <select value={minFollowers} onChange={(e) => setMinFollowers(e.target.value)} className={`${ui.input} w-auto`}>
            {MIN_FOLLOWERS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={maxRateCents} onChange={(e) => setMaxRateCents(e.target.value)} className={`${ui.input} w-auto`}>
            {MAX_RATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" className={`${ui.input} w-36`} />
          <input value={qInput} onChange={(e) => setQInput(e.target.value)} placeholder="Search creators…" className={`${ui.input} w-48`} />
          <label className="flex items-center gap-1.5 text-sm text-zinc-400">
            <input type="checkbox" checked={verifiedOnly} onChange={(e) => setVerifiedOnly(e.target.checked)} />
            Verified reach only
          </label>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-16 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : error ? (
          <p className="py-16 text-sm text-zinc-500">{error}</p>
        ) : creators.length === 0 ? (
          <p className="py-16 text-sm text-zinc-500">No creators match those filters.</p>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {creators.map((c) => <CreatorCard key={c.handle} c={c} />)}
            </div>
            {totalPages > 1 && (
              <div className="mt-8 flex items-center justify-center gap-3">
                <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} className={ui.btnGhost}>Prev</button>
                <span className="text-sm text-zinc-500">Page {page + 1} of {totalPages}</span>
                <button disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)} className={ui.btnGhost}>Next</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
