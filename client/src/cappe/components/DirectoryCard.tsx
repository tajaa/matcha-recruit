import { MapPin, Star, User } from 'lucide-react'
import type { CappeDirectoryEntry } from '../types'

// Palette shared with CappeLanding — Discover lives on the landing's dark
// surface, not inside the zinc/emerald authed app, so it uses the landing
// tokens rather than the app's.
const INK = '#F4F1E8'
const MUTED = '#8E8B81'
const LINE = 'rgba(244,241,232,0.10)'
const ACCENT = '#C6F16B'
const DISPLAY = 'var(--font-display)'

/** Monogram stand-in for a site with no logo — a directory of grey boxes reads
 *  as broken, and most sites won't have uploaded one. */
function Monogram({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
  return (
    <div
      className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border"
      style={{ borderColor: LINE, background: 'rgba(198,241,107,0.08)', color: ACCENT, fontFamily: DISPLAY, fontSize: '1.05rem' }}
    >
      {initials || '·'}
    </div>
  )
}

function locationLine(entry: CappeDirectoryEntry): string | null {
  const place = [entry.city, entry.region].filter(Boolean).join(', ')
  if (entry.distance_km !== null && entry.distance_km !== undefined) {
    const dist = entry.distance_km < 1 ? '<1 km' : `${Math.round(entry.distance_km)} km`
    return place ? `${place} · ${dist}` : dist
  }
  return place || null
}

export default function DirectoryCard({ entry }: { entry: CappeDirectoryEntry }) {
  const place = locationLine(entry)
  return (
    <a
      href={entry.url}
      target="_blank"
      rel="noopener noreferrer"
      className="gf-card flex h-full flex-col rounded-2xl border p-6 transition-colors"
      style={{ borderColor: LINE, background: 'rgba(244,241,232,0.02)' }}
    >
      <div className="flex items-start gap-4">
        {entry.logo_url ? (
          <img
            src={entry.logo_url}
            alt=""
            loading="lazy"
            className="h-12 w-12 shrink-0 rounded-xl border object-cover"
            style={{ borderColor: LINE }}
          />
        ) : (
          <Monogram name={entry.name} />
        )}
        <div className="min-w-0 flex-1">
          <h3
            className="truncate tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.25rem', color: INK }}
          >
            {entry.name}
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]" style={{ color: MUTED }}>
            {entry.category_label && <span>{entry.category_label}</span>}
            {/* A solo professional and a venue are different things to a
                visitor deciding whether they can hire this person. */}
            {entry.account_type === 'personal' && (
              <span className="inline-flex items-center gap-1" style={{ color: ACCENT }}>
                <User size={11} strokeWidth={2} />
                Individual
              </span>
            )}
          </div>
        </div>
      </div>

      {entry.blurb && (
        <p className="mt-4 line-clamp-3 text-[14px] leading-relaxed" style={{ color: MUTED }}>
          {entry.blurb}
        </p>
      )}

      <div className="mt-auto pt-5">
        {entry.tags.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {entry.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="rounded-full border px-2.5 py-0.5 text-[11px]"
                style={{ borderColor: LINE, color: MUTED }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
        <div className="flex items-center justify-between text-[12px]" style={{ color: MUTED }}>
          {place ? (
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <MapPin size={12} strokeWidth={1.8} />
              <span className="truncate">{place}</span>
            </span>
          ) : (
            <span />
          )}
          {/* Shown, never sorted on — see routes/public/directory.py. */}
          {entry.rating !== null && entry.review_count > 0 && (
            <span className="inline-flex shrink-0 items-center gap-1">
              <Star size={12} strokeWidth={1.8} style={{ color: ACCENT }} />
              {entry.rating.toFixed(1)}
              <span style={{ color: 'rgba(142,139,129,0.7)' }}>({entry.review_count})</span>
            </span>
          )}
        </div>
      </div>
    </a>
  )
}
