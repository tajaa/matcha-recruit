import { useCallback, useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ExternalLink, Loader2, RotateCcw, ShoppingCart, Sparkles, Star } from 'lucide-react'
import type { MWProjectTask } from '../../../types'
import {
  agentErrorMessage, listAgentRuns, rerunAgent,
  type AgentPick, type AgentPurchase, type AgentResult, type AgentRun,
} from '../../../api/matchaWork'

const POLL_MS = 4000
const EXTERNAL = { target: '_blank', rel: 'noopener noreferrer nofollow' } as const

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function money(amount: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'USD' }).format(amount)
  } catch {
    return `${amount.toFixed(2)} ${currency}`
  }
}

function Rating({ rating }: { rating: NonNullable<AgentPick['rating']> }) {
  return (
    <a {...EXTERNAL} href={rating.source_url} className="inline-flex items-center gap-1 text-xs text-amber-300 hover:underline">
      <Star className="h-3.5 w-3.5 fill-current" />
      {rating.value.toFixed(1)}/{rating.scale}
      {rating.count != null && <span className="text-w-dim">({rating.count.toLocaleString()} ratings)</span>}
    </a>
  )
}

function PickCard({ pick, hero }: { pick: AgentPick; hero?: boolean }) {
  const [imageIndex, setImageIndex] = useState(0)
  const image = pick.images[imageIndex]
  return (
    <div className={`rounded-lg border border-w-line bg-w-surface/60 p-3 ${hero ? '' : 'text-sm'}`}>
      {hero && <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-emerald-300">Top pick</p>}
      <div className={hero ? 'flex flex-col gap-3 sm:flex-row' : 'flex gap-3'}>
        {image && (
          <div className="shrink-0">
            <a {...EXTERNAL} href={image.page_url}>
              <img
                src={image.url}
                alt={image.alt}
                loading="lazy"
                referrerPolicy="no-referrer"
                className={`${hero ? 'h-40 w-40' : 'h-20 w-20'} rounded-md bg-white object-contain`}
              />
            </a>
            {pick.images.length > 1 && (
              <div className="mt-1 flex justify-center gap-1">
                {pick.images.map((img, i) => (
                  <button
                    key={img.url}
                    aria-label={`Photo ${i + 1}`}
                    onClick={() => setImageIndex(i)}
                    className={`h-1.5 w-1.5 rounded-full ${i === imageIndex ? 'bg-w-text' : 'bg-w-line'}`}
                  />
                ))}
              </div>
            )}
          </div>
        )}
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className={`${hero ? 'text-base' : 'text-sm'} font-semibold text-w-text`}>{pick.name}</p>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
              {pick.brand && <span className="text-xs text-w-dim">{pick.brand}</span>}
              {pick.price && (
                <a {...EXTERNAL} href={pick.price.source_url} className="text-xs font-medium text-w-text hover:underline">
                  {money(pick.price.amount, pick.price.currency)}
                </a>
              )}
              {pick.rating && <Rating rating={pick.rating} />}
            </div>
          </div>
          {pick.why.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-w-text">
              {pick.why.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          {hero && pick.reviews.length > 0 && (
            <div className="space-y-1.5">
              {pick.reviews.map((r) => (
                <blockquote key={r.url + r.quote} className="border-l-2 border-w-line pl-2 text-xs text-w-dim">
                  “{r.quote}”{' '}
                  <a {...EXTERNAL} href={r.url} className="whitespace-nowrap text-w-faint hover:underline">
                    — {r.source_name || host(r.url)}
                  </a>
                </blockquote>
              ))}
            </div>
          )}
          {pick.buy_links.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {pick.buy_links.map((link) => (
                <a
                  key={link.url}
                  {...EXTERNAL}
                  href={link.url}
                  className="inline-flex items-center gap-1 rounded-md bg-w-accent px-2 py-1 text-xs font-medium text-white hover:bg-w-accent-hi"
                >
                  <ShoppingCart className="h-3 w-3" />
                  {link.retailer || host(link.url)}
                  {link.price != null && ` · ${money(link.price, pick.price?.currency ?? 'USD')}`}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function AgentResultBody({ result }: { result: AgentResult }) {
  return (
    <div className="space-y-3">
      {result.changes_from_previous && (
        <div className="rounded-md border border-sky-500/35 bg-sky-500/10 px-2.5 py-1.5 text-xs text-sky-300">
          <span className="font-semibold">What changed: </span>
          {result.changes_from_previous}
        </div>
      )}
      <div>
        <p className="text-base font-semibold text-w-text">{result.headline}</p>
        <p className="mt-1 text-sm text-w-dim">{result.summary}</p>
      </div>
      {result.top_pick && <PickCard pick={result.top_pick} hero />}
      {result.criteria.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-w-dim">What mattered</p>
          <ul className="space-y-0.5 text-xs text-w-text">
            {result.criteria.map((c) => (
              <li key={c.name}><span className="font-medium">{c.name}</span>{c.why ? ` — ${c.why}` : ''}</li>
            ))}
          </ul>
        </div>
      )}
      {result.alternatives.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-w-dim">Alternatives</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {result.alternatives.map((pick) => <PickCard key={pick.name} pick={pick} />)}
          </div>
        </div>
      )}
      {result.sections.map((s) => (
        <div key={s.heading + s.body_md.slice(0, 20)} className="prose prose-sm prose-invert max-w-none text-sm">
          {s.heading && <p className="text-sm font-semibold text-w-text">{s.heading}</p>}
          {/* The server strips unverified links and images from body_md; this
              is the second lock: only http(s) links render, and never an image. */}
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) =>
                href && /^https?:\/\//i.test(href)
                  ? <a {...EXTERNAL} href={href}>{children}</a>
                  : <>{children}</>,
              img: () => null,
            }}
          >
            {s.body_md}
          </Markdown>
        </div>
      ))}
      {result.caveats.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-xs text-w-dim">
          {result.caveats.map((c) => <li key={c}>{c}</li>)}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-w-faint">
        <span>Confidence: {result.confidence}</span>
        {result.sources.map((s) => (
          <a key={s.url} {...EXTERNAL} href={s.url} className="inline-flex items-center gap-0.5 hover:text-w-text">
            {s.title || host(s.url)}
            <ExternalLink className="h-2.5 w-2.5" />
          </a>
        ))}
      </div>
    </div>
  )
}

/**
 * The agent card's result page inside the task panel: the newest round's
 * structured result, a round switcher, live status while a run is working,
 * and "Run again" after a failure.
 */
/** Purchases approved in the project chat. v1 records a handoff and charges
 *  nothing; the person finishes checkout at the link. */
function Purchases({ purchases }: { purchases: AgentPurchase[] }) {
  return (
    <div className="space-y-1.5 rounded-lg border border-w-line p-2.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-w-dim">
        <ShoppingCart className="h-3.5 w-3.5" /> Purchases
      </div>
      {purchases.map((p) => (
        <div key={p.id} className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="text-w-text">
            {p.item_name}
            {p.retailer ? ` at ${p.retailer}` : ''}
            {p.amount != null ? ` · ${money(p.amount, p.currency ?? 'USD')}` : ''}
            <span className="text-w-faint"> · card ending {p.card_last4}</span>
          </span>
          {/^https?:\/\//i.test(p.checkout_url) && (
            <a
              href={p.checkout_url}
              {...EXTERNAL}
              className="inline-flex items-center gap-1 rounded border border-w-line px-2 py-0.5 text-w-text hover:bg-w-surface2"
            >
              Checkout <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      ))}
      <p className="text-[11px] text-w-faint">Approved in chat. Nothing was charged: finish checkout at the link.</p>
    </div>
  )
}

export default function AgentResultView({
  projectId,
  task,
  canEdit,
}: {
  projectId: string
  task: MWProjectTask
  canEdit: boolean
}) {
  const [runs, setRuns] = useState<AgentRun[] | null>(null)
  const [purchases, setPurchases] = useState<AgentPurchase[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await listAgentRuns(projectId, task.id)
      setRuns(res.runs)
      setPurchases(res.purchases ?? [])
    } catch (e) {
      setError(agentErrorMessage(e))
    }
  }, [projectId, task.id])

  // Reload whenever the card itself changes (a WS task.updated moves it or
  // updates its status line), and poll while a run is live.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch; state is set after it resolves
    void load()
  }, [load, task.board_column, task.progress_note])

  const live = runs?.some((r) => r.status === 'queued' || r.status === 'running') ?? false
  useEffect(() => {
    if (!live) return
    const id = window.setInterval(() => void load(), POLL_MS)
    return () => window.clearInterval(id)
  }, [live, load])

  const done = (runs ?? []).filter((r) => r.status === 'done' && r.result)
  const shown = done.find((r) => r.id === selected) ?? done[0]
  const latest = runs?.[0]
  // Any open column with nothing working on it: a failed run, a card moved back
  // by hand, or a redirect whose run the queue refused (the note is saved).
  const canRerun = canEdit && !live && ['todo', 'in_progress', 'changes_requested'].includes(task.board_column)
  const waitingOnRedirect = !live && task.board_column === 'changes_requested' && latest?.status !== 'failed'

  async function rerun() {
    setBusy(true)
    setError(null)
    try {
      await rerunAgent(projectId, task.id)
      await load()
    } catch (e) {
      setError(agentErrorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (runs === null && !error) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-w-line bg-w-surface/60 p-3 text-xs text-w-dim">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading the agent's result…
      </div>
    )
  }

  return (
    <div className="space-y-3 rounded-lg border border-w-line bg-w-surface/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-w-dim">
          <Sparkles className="h-3.5 w-3.5 text-emerald-300" /> Espresso agent
        </div>
        {done.length > 1 && (
          <div className="flex gap-1">
            {done.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelected(r.id)}
                className={`rounded px-1.5 py-0.5 text-[11px] ${r.id === shown?.id ? 'bg-w-surface2 text-w-text' : 'text-w-dim hover:text-w-text'}`}
              >
                Round {r.round}
              </button>
            ))}
          </div>
        )}
      </div>

      {live && (
        <div className="flex items-center gap-2 text-xs text-w-dim">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {task.progress_note || 'Working on it…'}
          {latest?.steps.length ? <span className="text-w-faint">· {latest.steps.length} steps</span> : null}
        </div>
      )}
      {!live && latest?.status === 'failed' && (
        <p className="text-xs text-orange-300">{task.progress_note || 'The last run stopped before finishing.'}</p>
      )}
      {!live && !runs?.length && <p className="text-xs text-w-dim">The agent hasn't run on this card yet.</p>}
      {waitingOnRedirect && (
        <p className="text-xs text-w-dim">Your note is saved, but the agent isn't working on it yet. Run again to start.</p>
      )}

      {shown?.result && <AgentResultBody result={shown.result} />}
      {purchases.length > 0 && <Purchases purchases={purchases} />}

      {error && <p className="text-xs text-orange-300">{error}</p>}
      {canRerun && (
        <button
          onClick={rerun}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-2.5 py-1.5 text-xs font-medium text-w-text hover:bg-w-surface2 disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
          Run again
        </button>
      )}
    </div>
  )
}
