import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Loader2, MapPin, Search, X } from 'lucide-react'
import { fetchCappeDirectory, fetchCappeDirectoryCategories } from '../api'
import DirectoryCard from '../components/DirectoryCard'
import type {
  CappeAccountType,
  CappeDirectoryCategory,
  CappeDirectoryEntry,
} from '../types'

// Landing palette — Discover is a public marketing surface, not part of the
// authed app, so it matches CappeLanding rather than the zinc/emerald builder.
const BG = '#0A0A09'
const INK = '#F4F1E8'
const MUTED = '#8E8B81'
const LINE = 'rgba(244,241,232,0.10)'
const ACCENT = '#C6F16B'
const DISPLAY = 'var(--font-display)'
const WRAP = 'max-w-[1400px] mx-auto px-6 sm:px-10'

const PAGE_SIZE = 12
const TYPES: { value: CappeAccountType | 'all'; label: string }[] = [
  { value: 'all', label: 'Everyone' },
  { value: 'business', label: 'Businesses' },
  { value: 'personal', label: 'People' },
]

type Coords = { lat: number; lng: number }

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="shrink-0 rounded-full border px-3.5 py-1.5 text-[13px] transition-colors"
      style={{
        borderColor: active ? ACCENT : LINE,
        background: active ? 'rgba(198,241,107,0.12)' : 'transparent',
        color: active ? ACCENT : MUTED,
      }}
    >
      {children}
    </button>
  )
}

export default function CappeDiscover() {
  const [params, setParams] = useSearchParams()

  // The URL is the source of truth for the query so a search is shareable and
  // the back button works; `input` is the uncommitted text in the box.
  const q = params.get('q') ?? ''
  const category = params.get('category') ?? ''
  const type = (params.get('type') as CappeAccountType | 'all') || 'all'

  const [input, setInput] = useState(q)
  const [categories, setCategories] = useState<CappeDirectoryCategory[]>([])
  const [entries, setEntries] = useState<CappeDirectoryEntry[]>([])
  const [total, setTotal] = useState(0)
  const [nextOffset, setNextOffset] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [coords, setCoords] = useState<Coords | null>(null)
  const [geoState, setGeoState] = useState<'idle' | 'asking' | 'denied'>('idle')

  useEffect(() => { setInput(q) }, [q])

  useEffect(() => {
    fetchCappeDirectoryCategories()
      .then((res) => setCategories(res.categories.filter((c) => c.count > 0)))
      .catch(() => setCategories([]))
  }, [])

  // A stale in-flight response must never overwrite a newer one — the user can
  // type faster than the network answers.
  const requestSeq = useRef(0)

  useEffect(() => {
    const seq = ++requestSeq.current
    setLoading(true)
    setError(null)
    fetchCappeDirectory({
      q: q || undefined,
      category: category || undefined,
      type: type !== 'all' ? type : undefined,
      ...(coords ? { lat: coords.lat, lng: coords.lng, radius_km: 40 } : {}),
      sort: coords && !q ? 'distance' : 'relevance',
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((page) => {
        if (seq !== requestSeq.current) return
        setEntries(page.entries)
        setTotal(page.total)
        setNextOffset(page.next_offset)
      })
      .catch((err: Error) => {
        if (seq !== requestSeq.current) return
        setError(err.message || 'Could not load the directory.')
        setEntries([])
        setTotal(0)
        setNextOffset(null)
      })
      .finally(() => { if (seq === requestSeq.current) setLoading(false) })
  }, [q, category, type, coords])

  const loadMore = useCallback(() => {
    if (nextOffset === null || loadingMore) return
    setLoadingMore(true)
    const seq = requestSeq.current
    fetchCappeDirectory({
      q: q || undefined,
      category: category || undefined,
      type: type !== 'all' ? type : undefined,
      ...(coords ? { lat: coords.lat, lng: coords.lng, radius_km: 40 } : {}),
      sort: coords && !q ? 'distance' : 'relevance',
      limit: PAGE_SIZE,
      offset: nextOffset,
    })
      .then((page) => {
        if (seq !== requestSeq.current) return
        setEntries((prev) => [...prev, ...page.entries])
        setNextOffset(page.next_offset)
      })
      .catch(() => { /* keep what's on screen; the button stays available */ })
      .finally(() => setLoadingMore(false))
  }, [nextOffset, loadingMore, q, category, type, coords])

  function patchParams(next: Record<string, string | null>) {
    const merged = new URLSearchParams(params)
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value)
      else merged.delete(key)
    }
    setParams(merged, { replace: true })
  }

  function submitSearch(e: React.FormEvent) {
    e.preventDefault()
    patchParams({ q: input.trim() || null })
  }

  function requestLocation() {
    if (coords) { setCoords(null); return }         // toggle off
    if (!navigator.geolocation) { setGeoState('denied'); return }
    setGeoState('asking')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude })
        setGeoState('idle')
      },
      // Denial is a normal outcome, not an error state to shout about — the
      // directory simply stays unfiltered by distance.
      () => setGeoState('denied'),
      { timeout: 8000, maximumAge: 300_000 },
    )
  }

  const hasFilters = Boolean(q || category || type !== 'all' || coords)

  return (
    <div className="min-h-screen" style={{ background: BG, color: INK }}>
      <header className="border-b" style={{ borderColor: LINE }}>
        <div className={`${WRAP} flex items-center justify-between py-6`}>
          <Link to="/cappe" style={{ fontFamily: DISPLAY, fontSize: '1.4rem' }}>
            Gummfit
          </Link>
          <Link
            to="/cappe/website-setup"
            className="rounded-full px-4 py-2 text-[13px] font-medium"
            style={{ background: ACCENT, color: BG }}
          >
            Add your business
          </Link>
        </div>
      </header>

      <section className={`${WRAP} pt-14 sm:pt-20`}>
        <h1
          className="max-w-[16ch] tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.2rem,5.5vw,4rem)', lineHeight: 1.0 }}
        >
          Find someone <span className="italic" style={{ color: ACCENT }}>good.</span>
        </h1>
        <p className="mt-5 max-w-lg text-lg leading-relaxed" style={{ color: MUTED }}>
          Every business building on Gummfit, in one place — shops, studios, and the
          people you can hire directly.
        </p>

        <form onSubmit={submitSearch} className="mt-9 flex max-w-2xl items-center gap-2">
          <div className="relative flex-1">
            <Search
              size={17}
              strokeWidth={1.8}
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2"
              style={{ color: MUTED }}
            />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Coffee, wedding photographer, dog grooming…"
              aria-label="Search businesses"
              className="w-full rounded-full border bg-transparent py-3.5 pl-11 pr-10 text-[15px] outline-none placeholder:opacity-60"
              style={{ borderColor: LINE, color: INK }}
            />
            {input && (
              <button
                type="button"
                onClick={() => { setInput(''); patchParams({ q: null }) }}
                aria-label="Clear search"
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1"
                style={{ color: MUTED }}
              >
                <X size={15} strokeWidth={2} />
              </button>
            )}
          </div>
          <button
            type="submit"
            className="rounded-full px-6 py-3.5 text-[14px] font-medium"
            style={{ background: ACCENT, color: BG }}
          >
            Search
          </button>
        </form>

        <div className="mt-6 flex flex-wrap items-center gap-2">
          {TYPES.map((t) => (
            <Chip
              key={t.value}
              active={type === t.value}
              onClick={() => patchParams({ type: t.value === 'all' ? null : t.value })}
            >
              {t.label}
            </Chip>
          ))}
          <span className="mx-1 h-5 w-px" style={{ background: LINE }} />
          <button
            type="button"
            onClick={requestLocation}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[13px]"
            style={{
              borderColor: coords ? ACCENT : LINE,
              background: coords ? 'rgba(198,241,107,0.12)' : 'transparent',
              color: coords ? ACCENT : MUTED,
            }}
          >
            {geoState === 'asking'
              ? <Loader2 size={12} className="animate-spin" />
              : <MapPin size={12} strokeWidth={1.8} />}
            {coords ? 'Near me · on' : 'Near me'}
          </button>
          {geoState === 'denied' && (
            <span className="text-[12px]" style={{ color: MUTED }}>
              Location unavailable — showing everywhere.
            </span>
          )}
        </div>

        {categories.length > 0 && (
          <div className="mt-4 flex gap-2 overflow-x-auto pb-2">
            <Chip active={!category} onClick={() => patchParams({ category: null })}>
              All
            </Chip>
            {categories.map((c) => (
              <Chip
                key={c.slug}
                active={category === c.slug}
                onClick={() => patchParams({ category: category === c.slug ? null : c.slug })}
              >
                {c.label} <span style={{ opacity: 0.55 }}>{c.count}</span>
              </Chip>
            ))}
          </div>
        )}
      </section>

      <section className={`${WRAP} pb-28 pt-10`}>
        {loading ? (
          <div className="flex items-center gap-2 py-20 text-sm" style={{ color: MUTED }}>
            <Loader2 size={15} className="animate-spin" /> Loading…
          </div>
        ) : error ? (
          <p className="py-20 text-sm" style={{ color: MUTED }}>{error}</p>
        ) : entries.length === 0 ? (
          <div className="py-20">
            <p className="text-lg" style={{ fontFamily: DISPLAY }}>Nothing here yet.</p>
            <p className="mt-2 max-w-md text-[15px] leading-relaxed" style={{ color: MUTED }}>
              {hasFilters
                ? 'No businesses match that. Try a broader search or clear the filters.'
                : 'The directory is still filling up. Check back soon.'}
            </p>
            {hasFilters && (
              <button
                type="button"
                onClick={() => { setCoords(null); setParams(new URLSearchParams(), { replace: true }) }}
                className="mt-5 rounded-full border px-4 py-2 text-[13px]"
                style={{ borderColor: LINE, color: INK }}
              >
                Clear filters
              </button>
            )}
          </div>
        ) : (
          <>
            <p className="mb-6 text-[13px]" style={{ color: MUTED }}>
              {total} {total === 1 ? 'business' : 'businesses'}
            </p>
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {entries.map((entry) => (
                <DirectoryCard key={entry.slug} entry={entry} />
              ))}
            </div>
            {nextOffset !== null && (
              <div className="mt-12 flex justify-center">
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="inline-flex items-center gap-2 rounded-full border px-6 py-3 text-[14px] disabled:opacity-60"
                  style={{ borderColor: LINE, color: INK }}
                >
                  {loadingMore && <Loader2 size={14} className="animate-spin" />}
                  Show more
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}
