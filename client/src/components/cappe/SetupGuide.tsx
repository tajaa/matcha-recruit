import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Copy, Rocket, Loader2, Sparkles } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import { cappeSiteHost } from '../../utils/cappeHost'
import type { CappeSite } from '../../types/cappe'

interface SetupGuideProps {
  site: CappeSite
  accountType?: string | null
  publishing: boolean
  onPublish: () => void
}

/** Step-by-step path from fresh site to "someone can book/buy from my link".
 *  Driven by real data (offerings exist? published?), not stored progress —
 *  hides itself once the site is live with at least one offering. */
export default function SetupGuide({ site, accountType, publishing, onPublish }: SetupGuideProps) {
  const [offeringCount, setOfferingCount] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      cappeApi.get<unknown[]>(`/sites/${site.id}/products`).catch(() => []),
      cappeApi.get<unknown[]>(`/sites/${site.id}/booking-types`).catch(() => []),
    ]).then(([products, bookingTypes]) => {
      if (!cancelled) setOfferingCount(products.length + bookingTypes.length)
    })
    return () => { cancelled = true }
  }, [site.id])

  const hasOffering = (offeringCount ?? 0) > 0
  const isPublished = site.status === 'published'
  const host = cappeSiteHost(site)
  const url = `https://${host}`

  // All set — get out of the way.
  if (hasOffering && isPublished) return null
  // Don't flash the guide before we know the offering count.
  if (offeringCount === null) return null

  const personal = accountType === 'personal'
  const offeringHint = personal
    ? 'A Pilates class, a styling appointment, a coaching session — whatever people pay you for.'
    : 'A product, a service package, or a bookable appointment your customers pay for.'

  const steps: { done: boolean; title: string; body: React.ReactNode }[] = [
    {
      done: hasOffering,
      title: 'Add something people can book or buy',
      body: (
        <>
          <p className="text-xs leading-relaxed text-zinc-400">{offeringHint}</p>
          <div className="mt-2 flex gap-2">
            <Link to={`/cappe/sites/${site.id}/bookings`}
              className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20">
              Add a bookable session
            </Link>
            <Link to={`/cappe/sites/${site.id}/shop`}
              className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800">
              Add a product or service
            </Link>
          </div>
        </>
      ),
    },
    {
      done: isPublished,
      title: 'Publish your site',
      body: (
        <>
          <p className="text-xs leading-relaxed text-zinc-400">
            Goes live instantly at <span className="text-zinc-200">{host}</span>.
          </p>
          {!isPublished && (
            <button onClick={onPublish} disabled={publishing}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
              {publishing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Rocket className="h-3 w-3" />}
              Publish now
            </button>
          )}
        </>
      ),
    },
    {
      done: false,
      title: 'Share your link',
      body: (
        <div className="flex items-center gap-2">
          <span className="truncate text-xs text-zinc-400">{url}</span>
          <button
            onClick={() => {
              navigator.clipboard.writeText(url).then(() => {
                setCopied(true)
                setTimeout(() => setCopied(false), 1500)
              })
            }}
            className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2 py-0.5 text-[11px] text-zinc-300 hover:bg-zinc-800"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      ),
    },
  ]

  const doneCount = (hasOffering ? 1 : 0) + (isPublished ? 1 : 0)

  return (
    <section className="mb-6 rounded-2xl border border-emerald-500/25 bg-emerald-500/[0.04] p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Sparkles className="h-4 w-4 text-emerald-400" />
          Get your site earning
        </h2>
        <span className="text-xs text-zinc-500">{doneCount} of 2 done</span>
      </div>
      <ol className="space-y-4">
        {steps.map((s, i) => (
          <li key={s.title} className="flex gap-3">
            <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
              s.done ? 'bg-emerald-500 text-zinc-950' : 'border border-zinc-700 text-zinc-400'
            }`}>
              {s.done ? <Check className="h-3 w-3" /> : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <div className={`text-sm font-medium ${s.done ? 'text-zinc-500 line-through' : 'text-zinc-200'}`}>{s.title}</div>
              {!s.done && <div className="mt-1">{s.body}</div>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
