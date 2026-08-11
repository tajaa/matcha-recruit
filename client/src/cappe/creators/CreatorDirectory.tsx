import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  BadgeCheck,
  CircleDollarSign,
  Loader2,
  MapPin,
  Search,
  SlidersHorizontal,
  Sparkles,
  TrendingUp,
  UsersRound,
  X,
} from 'lucide-react'
import { fetchPublicCreators } from '../api'
import { useCappeMe } from '../hooks/useCappeMe'
import { CREATOR_NICHES, fmtCents, type PublicCreatorCard } from '../types'
import { creatorPaths, creatorProfilePath } from './creatorPaths'

const MIN_FOLLOWERS_OPTIONS = [
  { value: '', label: 'Any audience' },
  { value: '1000', label: '1K+ audience' },
  { value: '10000', label: '10K+ audience' },
  { value: '50000', label: '50K+ audience' },
  { value: '100000', label: '100K+ audience' },
  { value: '500000', label: '500K+ audience' },
]

const MAX_RATE_OPTIONS = [
  { value: '', label: 'Any rate' },
  { value: '10000', label: 'Under $100' },
  { value: '25000', label: 'Under $250' },
  { value: '50000', label: 'Under $500' },
  { value: '100000', label: 'Under $1K' },
  { value: '500000', label: 'Under $5K' },
]

const PLATFORM_OPTIONS = [
  ['instagram', 'Instagram'],
  ['tiktok', 'TikTok'],
  ['youtube', 'YouTube'],
  ['x', 'X'],
  ['twitch', 'Twitch'],
  ['facebook', 'Facebook'],
  ['linkedin', 'LinkedIn'],
] as const

const PAGE_SIZE = 12
const compactNumber = (n: number) => Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n)
const titleCase = (value: string) => value.charAt(0).toUpperCase() + value.slice(1)

const CARD_BACKGROUNDS = [
  'from-[#c6a7d7] via-[#dfb7a1] to-[#879d72]',
  'from-[#829aa7] via-[#a7b9ac] to-[#d7c69a]',
  'from-[#d1a193] via-[#b7897e] to-[#786971]',
  'from-[#93a77a] via-[#c6b885] to-[#dd9e79]',
]

function creatorBackground(handle: string) {
  const index = Array.from(handle).reduce((sum, char) => sum + char.charCodeAt(0), 0) % CARD_BACKGROUNDS.length
  return CARD_BACKGROUNDS[index]
}

function StatBadge({ icon: Icon, value, label }: {
  icon: typeof UsersRound
  value: string
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-[#10110f]/75 px-2.5 py-1.5 text-[11px] font-semibold text-white shadow-lg shadow-black/10 backdrop-blur-md">
      <Icon className="h-3.5 w-3.5 text-[#d4ff72]" />
      <strong className="font-bold">{value}</strong>
      <span className="text-white/60">{label}</span>
    </span>
  )
}

function CreatorCard({ creator }: { creator: PublicCreatorCard }) {
  const audience = creator.max_followers > 0 ? compactNumber(creator.max_followers) : 'New'
  const engagement = creator.max_engagement_rate != null
    ? `${Number(creator.max_engagement_rate).toFixed(1)}%`
    : null

  return (
    <Link
      to={creatorProfilePath(creator.handle)}
      className="group flex h-full flex-col overflow-hidden rounded-[1.45rem] border border-white/10 bg-[#191b17] transition duration-300 hover:-translate-y-1 hover:border-[#d4ff72]/35 hover:bg-[#1e211b] hover:shadow-[0_22px_65px_rgba(0,0,0,0.32)]"
    >
      <div className={`relative aspect-[4/3] overflow-hidden bg-gradient-to-br ${creatorBackground(creator.handle)}`}>
        {creator.cover_url ? (
          <img
            src={creator.cover_url}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.035]"
          />
        ) : (
          <div className="absolute inset-0 opacity-80">
            <div className="absolute -right-12 -top-16 h-48 w-48 rounded-full border-[34px] border-white/15" />
            <div className="absolute -bottom-20 -left-12 h-56 w-56 rounded-full bg-[#20251b]/35" />
            <div className="absolute bottom-8 left-8 h-20 w-32 rotate-[-18deg] rounded-full border-[16px] border-white/15" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-[#10110f]/85 via-transparent to-[#10110f]/15" />

        <div className="absolute left-4 right-4 top-4 flex items-start justify-between gap-2">
          {creator.reach_verified ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#d4ff72] px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-[#1b2113] shadow-lg">
              <BadgeCheck className="h-3.5 w-3.5" /> Verified reach
            </span>
          ) : <span />}
          {creator.location && (
            <span className="inline-flex max-w-[58%] items-center gap-1 rounded-full border border-white/15 bg-[#10110f]/70 px-2.5 py-1.5 text-[10px] font-medium text-white/80 backdrop-blur-md">
              <MapPin className="h-3 w-3 shrink-0" /><span className="truncate">{creator.location}</span>
            </span>
          )}
        </div>

        <div className="absolute bottom-4 left-4 right-4 flex flex-wrap gap-2">
          <StatBadge icon={UsersRound} value={audience} label="audience" />
          {engagement && <StatBadge icon={TrendingUp} value={engagement} label="engagement" />}
        </div>
      </div>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex items-start gap-3.5">
          <div className="-mt-10 h-16 w-16 shrink-0 overflow-hidden rounded-full border-[3px] border-[#191b17] bg-[#2b3026] shadow-lg transition-colors group-hover:border-[#1e211b]">
            {creator.avatar_url ? (
              <img src={creator.avatar_url} alt={creator.display_name} loading="lazy" className="h-full w-full object-cover" />
            ) : (
              <span className="flex h-full w-full items-center justify-center text-lg font-bold text-[#d4ff72]">
                {creator.display_name.charAt(0).toUpperCase()}
              </span>
            )}
          </div>
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex items-center gap-1.5">
              <h2 className="truncate text-lg font-semibold tracking-[-0.035em] text-[#f7f5ee]">{creator.display_name}</h2>
              {creator.reach_verified && <BadgeCheck className="h-4 w-4 shrink-0 fill-[#d4ff72]/15 text-[#d4ff72]" />}
            </div>
            <p className="truncate text-xs text-[#85897c]">@{creator.handle}</p>
          </div>
        </div>

        {creator.bio ? (
          <p className="mt-4 line-clamp-2 min-h-11 text-sm leading-[1.4rem] text-[#b8baaf]">{creator.bio}</p>
        ) : (
          <p className="mt-4 min-h-11 text-sm leading-[1.4rem] text-[#74786d]">Creator profile and media kit.</p>
        )}

        <div className="mt-4 flex min-h-7 flex-wrap gap-1.5">
          {creator.niches.slice(0, 3).map((niche) => (
            <span key={niche} className="rounded-full border border-white/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#c5c7bc]">
              {niche}
            </span>
          ))}
        </div>

        <div className="mt-5 flex items-end justify-between gap-3 border-t border-white/10 pt-4">
          <div>
            <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-[#70756a]">Rate card</p>
            <p className="mt-1 text-sm font-semibold text-[#f1f0e9]">
              {creator.min_rate_cents != null ? `From ${fmtCents(creator.min_rate_cents)}` : 'Available on request'}
            </p>
          </div>
          <div className="flex items-center gap-2 text-right">
            {creator.platforms.length > 0 && (
              <span className="hidden text-[10px] font-semibold uppercase tracking-[0.08em] text-[#7f8378] sm:block">
                {creator.platforms.slice(0, 2).map(titleCase).join(' · ')}
              </span>
            )}
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#d4ff72] text-[#182015] transition-transform group-hover:translate-x-0.5">
              <ArrowRight className="h-4 w-4" />
            </span>
          </div>
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

  useEffect(() => {
    const timer = setTimeout(() => { setQ(qInput.trim()); setPage(0) }, 300)
    return () => clearTimeout(timer)
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
  const activeFilterCount = [niche, platform, minFollowers, maxRateCents, location, verifiedOnly].filter(Boolean).length

  function clearFilters() {
    setNiche('')
    setPlatform('')
    setMinFollowers('')
    setMaxRateCents('')
    setLocation('')
    setVerifiedOnly(false)
    setQInput('')
    setQ('')
    setPage(0)
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[#10110f] text-[#f7f5ee] selection:bg-[#d4ff72] selection:text-[#11140d]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[34rem] bg-[radial-gradient(circle_at_78%_5%,rgba(212,255,114,0.15),transparent_24rem),radial-gradient(circle_at_12%_22%,rgba(192,145,255,0.11),transparent_22rem)]" />

      <header className="relative z-10 border-b border-white/10 px-5 py-5 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <Link to="/gummfit/creators" className="flex items-center gap-2.5" aria-label="Gummfit Creators home">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#d4ff72] text-sm font-black tracking-tighter text-[#14170f] shadow-[0_0_28px_rgba(212,255,114,0.22)]">G</span>
            <span className="text-sm font-semibold tracking-[-0.02em]">Gummfit <em className="font-normal text-[#d4ff72]">Creators</em></span>
          </Link>
          <nav className="flex items-center gap-3 sm:gap-5">
            <Link to="/gummfit/creators" className="hidden text-sm font-medium text-[#b8baaf] transition hover:text-white sm:block">For creators</Link>
            {account?.account_type === 'business' ? (
              <Link to={creatorPaths.brandHome} className="rounded-full bg-[#d4ff72] px-4 py-2 text-sm font-semibold text-[#14170f] transition hover:-translate-y-0.5 hover:bg-[#e1ff9a] sm:px-5">Brand workspace</Link>
            ) : (
              <>
                <Link to={creatorPaths.brandLogin} className="text-sm font-medium text-[#deded5] transition hover:text-white">Brand sign in</Link>
                <Link to={creatorPaths.brandSignup} className="rounded-full bg-[#d4ff72] px-4 py-2 text-sm font-semibold text-[#14170f] transition hover:-translate-y-0.5 hover:bg-[#e1ff9a] sm:px-5">Find talent</Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <section className="relative z-10 mx-auto max-w-7xl px-5 pb-12 pt-16 sm:px-8 sm:pb-16 sm:pt-20 lg:px-12">
        <div className="max-w-4xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#d4ff72]/25 bg-[#d4ff72]/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-[#dcff91]">
            <Sparkles className="h-3.5 w-3.5" /> The Gummfit creator network
          </div>
          <h1 className="mt-6 text-[3.15rem] font-semibold leading-[0.93] tracking-[-0.065em] text-[#fbfaf5] sm:text-6xl lg:text-7xl">
            Meet creators with<br className="hidden sm:block" /> a <span className="text-[#d4ff72]">point of view.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-[#b8baaf] sm:text-xl">
            Discover distinct voices, verified audiences, and transparent starting rates. Your next great collaboration starts here.
          </p>
        </div>

        <div className="mt-10 max-w-3xl rounded-2xl border border-white/10 bg-[#1a1d17]/90 p-2 shadow-2xl shadow-black/20 backdrop-blur-xl sm:flex sm:items-center">
          <div className="flex min-w-0 flex-1 items-center gap-3 px-3 py-2">
            <Search className="h-5 w-5 shrink-0 text-[#d4ff72]" />
            <input
              value={qInput}
              onChange={(event) => setQInput(event.target.value)}
              placeholder="Search by name, niche, or creative style"
              className="w-full bg-transparent text-sm text-white outline-none placeholder:text-[#73776c] sm:text-base"
            />
          </div>
          <button type="button" onClick={() => { setQ(qInput.trim()); setPage(0) }} className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#d4ff72] px-5 py-3 text-sm font-bold text-[#182015] sm:mt-0 sm:w-auto">
            Explore creators <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </section>

      <section className="relative border-y border-white/10 bg-[#151713]/90 px-5 py-5 backdrop-blur-sm sm:px-8 lg:px-12">
        <div className="mx-auto max-w-7xl">
          <div className="mb-3 flex items-center justify-between">
            <span className="inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.15em] text-[#85897d]"><SlidersHorizontal className="h-3.5 w-3.5" /> Refine your search</span>
            {(activeFilterCount > 0 || qInput) && <button onClick={clearFilters} className="inline-flex items-center gap-1 text-xs font-semibold text-[#cbd0c1] transition hover:text-[#d4ff72]"><X className="h-3.5 w-3.5" /> Clear all</button>}
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
            <select value={niche} onChange={(event) => setNiche(event.target.value)} className="rounded-xl border border-white/10 bg-[#20231d] px-3 py-2.5 text-sm text-[#e5e5dc] outline-none focus:border-[#d4ff72]/50">
              <option value="">All niches</option>
              {CREATOR_NICHES.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
            </select>
            <select value={platform} onChange={(event) => setPlatform(event.target.value)} className="rounded-xl border border-white/10 bg-[#20231d] px-3 py-2.5 text-sm text-[#e5e5dc] outline-none focus:border-[#d4ff72]/50">
              <option value="">All platforms</option>
              {PLATFORM_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <select value={minFollowers} onChange={(event) => setMinFollowers(event.target.value)} className="rounded-xl border border-white/10 bg-[#20231d] px-3 py-2.5 text-sm text-[#e5e5dc] outline-none focus:border-[#d4ff72]/50">
              {MIN_FOLLOWERS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <select value={maxRateCents} onChange={(event) => setMaxRateCents(event.target.value)} className="rounded-xl border border-white/10 bg-[#20231d] px-3 py-2.5 text-sm text-[#e5e5dc] outline-none focus:border-[#d4ff72]/50">
              {MAX_RATE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <div className="relative">
              <MapPin className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#74786d]" />
              <input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Location" className="w-full rounded-xl border border-white/10 bg-[#20231d] py-2.5 pl-8 pr-3 text-sm text-[#e5e5dc] outline-none placeholder:text-[#74786d] focus:border-[#d4ff72]/50" />
            </div>
            <label className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-white/10 bg-[#20231d] px-3 py-2.5 text-sm text-[#c7c9bf]">
              <input type="checkbox" checked={verifiedOnly} onChange={(event) => setVerifiedOnly(event.target.checked)} className="accent-[#d4ff72]" />
              Verified reach
            </label>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-12 sm:px-8 sm:py-16 lg:px-12">
        <div className="mb-7 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.17em] text-[#d4ff72]">Available for partnerships</p>
            <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f7f5ee] sm:text-3xl">Explore the network</h2>
          </div>
          {!loading && !error && <p className="text-sm text-[#85897d]">{total} creator{total === 1 ? '' : 's'}</p>}
        </div>

        {loading ? (
          <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-[#85897d]"><Loader2 className="h-4 w-4 animate-spin text-[#d4ff72]" /> Curating creators…</div>
        ) : error ? (
          <div className="rounded-2xl border border-white/10 bg-[#191b17] px-6 py-20 text-center"><p className="text-sm text-[#aeb0a4]">{error}</p></div>
        ) : creators.length === 0 ? (
          <div className="rounded-2xl border border-white/10 bg-[#191b17] px-6 py-20 text-center">
            <Search className="mx-auto h-6 w-6 text-[#d4ff72]" />
            <h3 className="mt-4 text-xl font-semibold tracking-tight">No exact matches yet</h3>
            <p className="mt-2 text-sm text-[#8f9387]">Try broadening your filters to discover more creators.</p>
            <button onClick={clearFilters} className="mt-5 rounded-full border border-white/15 px-4 py-2 text-sm font-semibold transition hover:border-[#d4ff72]/40 hover:text-[#d4ff72]">Clear filters</button>
          </div>
        ) : (
          <>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {creators.map((creator) => <CreatorCard key={creator.handle} creator={creator} />)}
            </div>
            {totalPages > 1 && (
              <div className="mt-12 flex items-center justify-center gap-4">
                <button disabled={page === 0} onClick={() => setPage((current) => current - 1)} className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 text-[#e5e5dc] transition hover:border-[#d4ff72]/50 hover:text-[#d4ff72] disabled:cursor-not-allowed disabled:opacity-30"><ArrowLeft className="h-4 w-4" /></button>
                <span className="text-xs font-semibold uppercase tracking-[0.12em] text-[#85897d]">{page + 1} / {totalPages}</span>
                <button disabled={page + 1 >= totalPages} onClick={() => setPage((current) => current + 1)} className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/15 text-[#e5e5dc] transition hover:border-[#d4ff72]/50 hover:text-[#d4ff72] disabled:cursor-not-allowed disabled:opacity-30"><ArrowRight className="h-4 w-4" /></button>
              </div>
            )}
          </>
        )}
      </section>

      <section className="border-t border-white/10 bg-[#171a15] px-5 py-16 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-7 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2 text-[#d4ff72]"><CircleDollarSign className="h-5 w-5" /><span className="text-xs font-bold uppercase tracking-[0.15em]">Built for better partnerships</span></div>
            <h2 className="mt-3 max-w-2xl text-3xl font-semibold leading-tight tracking-[-0.045em]">Ready to put your work in front of the right brands?</h2>
          </div>
          <Link to={creatorPaths.signup} className="inline-flex shrink-0 items-center gap-2 rounded-full bg-[#d4ff72] px-6 py-3.5 text-sm font-bold text-[#14170f] transition hover:-translate-y-0.5 hover:bg-[#e1ff9a]">Join the network <ArrowRight className="h-4 w-4" /></Link>
        </div>
      </section>

      <footer className="border-t border-white/10 px-5 py-7 text-xs text-[#85897d] sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-7xl flex-col justify-between gap-3 sm:flex-row"><span>© {new Date().getFullYear()} Gummfit Creators</span><div className="flex gap-5"><Link to="/gummfit/creators" className="hover:text-white">For creators</Link><Link to={creatorPaths.brandLogin} className="hover:text-white">For brands</Link></div></div>
      </footer>
    </main>
  )
}
