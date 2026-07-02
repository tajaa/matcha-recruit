import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, MapPin, Sparkles } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import {
  markTenantUpdatesSeen,
  updatesForSource,
  type TenantUpdate,
  type TenantUpdateAvailability,
} from '../../data/tenantUpdates'

const CHIP_STYLES: Record<TenantUpdateAvailability, string> = {
  included: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
  addon: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  upgrade: 'bg-sky-500/15 text-sky-400 border-sky-500/20',
}

const CHIP_LABELS: Record<TenantUpdateAvailability, string> = {
  included: 'Included in your plan',
  addon: 'Add-on',
  upgrade: 'Upgrade',
}

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function UpdateCard({ update }: { update: TenantUpdate }) {
  return (
    <article className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span
          className={`text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border leading-none ${CHIP_STYLES[update.availability]}`}
        >
          {CHIP_LABELS[update.availability]}
        </span>
        <span className="text-xs text-zinc-500">{formatDate(update.date)}</span>
      </div>
      <h2 className="mt-2.5 text-base font-medium text-zinc-100">{update.title}</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{update.summary}</p>

      <div className="mt-4">
        <p className="text-[10px] font-medium uppercase tracking-[0.14em] text-zinc-600">
          Where to find it
        </p>
        <ul className="mt-1.5 space-y-1">
          {update.whereToFind.map((loc) => (
            <li key={loc.label} className="flex items-center gap-2 text-sm">
              <MapPin className="h-3.5 w-3.5 flex-shrink-0 text-zinc-600" strokeWidth={1.6} />
              {loc.to ? (
                <Link
                  to={loc.to}
                  className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300 transition-colors"
                >
                  {loc.label}
                  <ArrowRight className="h-3 w-3" strokeWidth={1.8} />
                </Link>
              ) : (
                <span className="text-zinc-400">{loc.label}</span>
              )}
            </li>
          ))}
        </ul>
      </div>

      <p className="mt-4 text-sm leading-relaxed text-zinc-500">
        <span className="font-medium text-zinc-400">Why it matters: </span>
        {update.whyItMatters}
      </p>
    </article>
  )
}

export default function WhatsNew() {
  const { me } = useMe()
  const userId = me?.user?.id
  const source = me?.profile?.signup_source
  const updates = updatesForSource(source)

  // Visiting the page marks everything for this tier as seen. The sidebar
  // entry's onSeen fires too when it becomes active — both writes are
  // idempotent on the same localStorage id set.
  useEffect(() => {
    if (userId) markTenantUpdatesSeen(userId, source)
  }, [userId, source])

  return (
    <div className="max-w-6xl">
      <div className="flex items-center gap-2.5">
        <Sparkles className="h-5 w-5 text-emerald-400" strokeWidth={1.6} />
        <h1 className="text-2xl font-semibold text-zinc-100">What&rsquo;s New</h1>
      </div>
      <p className="mt-2 text-sm text-zinc-500">
        New features and improvements for your plan — what shipped, where to find it, and
        whether it&rsquo;s included, an add-on, or part of an upgrade.
      </p>

      {updates.length === 0 ? (
        <div className="mt-8 max-w-2xl rounded-xl border border-zinc-800 bg-zinc-900/40 p-8 text-center">
          <p className="text-sm text-zinc-400">You&rsquo;re all caught up.</p>
          <p className="mt-1 text-xs text-zinc-600">
            New features for your plan will show up here when they ship.
          </p>
        </div>
      ) : (
        <div className="mt-8 grid gap-4 lg:grid-cols-2 items-start">
          {updates.map((u) => <UpdateCard key={u.id} update={u} />)}
        </div>
      )}
    </div>
  )
}
