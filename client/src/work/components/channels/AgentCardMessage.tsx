import { useEffect, useState } from 'react'
import {
  BadgeCheck, CheckCircle2, Clock, ExternalLink, ImageIcon, Loader2, ShoppingBag, Star, XOctagon,
} from 'lucide-react'
import type {
  AgentChatButton, AgentChatMetadata, AgentChatPick, AgentChatPromptView, AgentChatReceipt, AgentChatResult,
} from '../../types'

/**
 * Espresso's agent-card messages in a project chat, rendered as cards instead
 * of text (server payloads: agent_card/chat_flow.py): the result (top pick
 * with photo, price, rating, reasons, store link; alternatives), a question
 * with quick-reply buttons (each sends its `reply` as a threaded reply, the
 * same as typing it), and the purchase receipt.
 *
 * Photos are server-rehosted https CDN URLs; links are http(s) only and open
 * in a new tab without referrer or opener.
 */

const EXTERNAL = { target: '_blank', rel: 'noopener noreferrer nofollow' } as const

function httpUrl(url?: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function Photo({ url, size, alt }: { url?: string | null; size: number; alt: string }) {
  const [failed, setFailed] = useState(false)
  const src = url && url.startsWith('https://') && !failed ? url : null
  return (
    <div
      className="shrink-0 overflow-hidden rounded-lg border border-w-line bg-white flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      {src ? (
        <img src={src} alt={alt} className="h-full w-full object-cover" onError={() => setFailed(true)} />
      ) : (
        <ImageIcon className="text-w-faint" style={{ width: size / 4, height: size / 4 }} />
      )}
    </div>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="mt-1 max-w-[540px] rounded-2xl border border-w-line bg-w-surface p-3 space-y-2.5">{children}</div>
}

function Rating({ rating }: { rating: NonNullable<AgentChatPick['rating']> }) {
  return (
    <span className="inline-flex items-center gap-0.5 text-xs">
      <Star size={11} className="fill-yellow-400 text-yellow-400" />
      <span className="font-semibold text-w-text">{rating.value.toFixed(1)}</span>
      {rating.count != null && <span className="text-w-dim">({rating.count.toLocaleString()})</span>}
    </span>
  )
}

function ResultCard({ result }: { result: AgentChatResult }) {
  const pick = result.top_pick
  const buy = httpUrl(pick?.buy_url)
  return (
    <Card>
      <p className="text-sm font-semibold text-w-text">{result.headline}</p>
      {result.summary && <p className="text-xs text-w-dim line-clamp-5">{result.summary}</p>}
      {pick && (
        <div className="rounded-xl bg-w-surface2/60 p-2.5 space-y-2">
          <div className="flex gap-3">
            <Photo url={pick.image_url} size={104} alt={pick.name} />
            <div className="min-w-0 space-y-1">
              <p className="text-[10px] font-bold tracking-wider text-w-accent">TOP PICK</p>
              <p className="text-sm font-semibold text-w-text leading-snug">{pick.name}</p>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-w-dim">
                {pick.brand && <span>{pick.brand}</span>}
                {pick.rating && <Rating rating={pick.rating} />}
              </div>
              {pick.price_text && <p className="text-base font-bold text-w-text">{pick.price_text}</p>}
            </div>
          </div>
          {!!pick.why?.length && (
            <ul className="space-y-1">
              {pick.why.map((reason) => (
                <li key={reason} className="flex gap-1.5 text-xs text-w-text">
                  <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-400" />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          )}
          {buy && (
            <a
              href={buy}
              {...EXTERNAL}
              className="inline-flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-xs font-semibold text-w-on-accent hover:opacity-90"
            >
              View at {pick.retailer || host(buy)} <ExternalLink size={12} />
            </a>
          )}
        </div>
      )}
      {result.alternatives.length > 0 && (
        <div className="space-y-1.5 border-t border-w-line pt-2">
          <p className="text-[10px] font-semibold tracking-wider text-w-dim">ALSO COMPARED</p>
          {result.alternatives.map((alt) => {
            const link = httpUrl(alt.buy_url)
            return (
              <div key={alt.name} className="flex items-center gap-2.5">
                <Photo url={alt.image_url} size={40} alt={alt.name} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-w-text">{alt.name}</p>
                  {alt.brand && <p className="truncate text-[10px] text-w-dim">{alt.brand}</p>}
                </div>
                {alt.price_text && <span className="text-xs font-semibold text-w-text">{alt.price_text}</span>}
                {link && (
                  <a href={link} {...EXTERNAL} title={alt.retailer || host(link)} className="text-w-dim hover:text-w-text">
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
            )
          })}
        </div>
      )}
      {!pick && !!result.sections?.length && (
        <p className="text-xs text-w-dim">Covers: {result.sections.join(' · ')}</p>
      )}
      <p className="text-[11px] text-w-faint">
        The full page is on the card{result.source_count ? ` · ${result.source_count} sources` : ''}.
      </p>
    </Card>
  )
}

function closedText(meta: AgentChatMetadata, status: string): string {
  switch (status) {
    case 'answered': return meta.answer_text || 'Answered'
    case 'superseded': return 'Replaced by a newer result'
    case 'expired': return 'This question expired'
    default: return 'Closed'
  }
}

/** True once `expiresAt` has passed, flipping on time while the card is open. */
function useExpired(expiresAt?: string): boolean {
  const deadline = expiresAt ? Date.parse(expiresAt) : Number.NaN
  const [expired, setExpired] = useState(() => !Number.isNaN(deadline) && deadline <= Date.now())
  useEffect(() => {
    if (Number.isNaN(deadline) || expired) return
    // setTimeout caps at 2^31-1 ms (~24 days); questions live 7 days at most.
    const timer = setTimeout(() => setExpired(true), Math.min(Math.max(deadline - Date.now(), 0), 2 ** 31 - 1))
    return () => clearTimeout(timer)
  }, [deadline, expired])
  return expired
}

/** How long a pressed button waits for the server to close the question.
 *  If it stays open (e.g. "Buy it" before any card is saved, where Espresso
 *  says so and keeps asking), the buttons come back. */
const SENDING_MS = 8000

function PromptCard({
  meta, view, heading, userId, onQuickReply,
}: {
  meta: AgentChatMetadata
  view: AgentChatPromptView
  heading: string
  userId?: string
  onQuickReply?: (reply: string) => boolean
}) {
  const [sending, setSending] = useState<string | null>(null)
  const [offline, setOffline] = useState(false)
  const expired = useExpired(meta.expires_at)
  useEffect(() => {
    if (!sending) return
    const timer = setTimeout(() => setSending(null), SENDING_MS)
    return () => clearTimeout(timer)
  }, [sending])
  const status = meta.prompt_status && meta.prompt_status !== 'open' ? meta.prompt_status : expired ? 'expired' : 'open'
  // Buy / card questions answer only to their owner; the server refuses anyone else.
  const forSomeoneElse = !!meta.owner_user_id && meta.owner_user_id !== userId
  const stacked = view.buttons.some((b) => b.detail)
  const offer = view.offer
  const press = (button: AgentChatButton) => {
    const sent = onQuickReply?.(button.reply) ?? false
    setOffline(!sent)
    if (sent) setSending(button.label)
  }
  let footer: React.ReactNode
  if (status !== 'open') {
    footer = (
      <p className="flex items-center gap-1.5 text-[11px] text-w-dim">
        {status === 'answered' ? <CheckCircle2 size={12} /> : <Clock size={12} />}
        {closedText(meta, status)}
      </p>
    )
  } else if (sending) {
    footer = (
      <p className="flex items-center gap-1.5 text-[11px] text-w-dim">
        <Loader2 size={12} className="animate-spin" />
        Sending “{sending}”…
      </p>
    )
  } else if (forSomeoneElse) {
    footer = <p className="text-[11px] text-w-dim">Waiting for the buyer to answer.</p>
  } else {
    footer = (
      <>
        <div className={stacked ? 'flex flex-col items-start gap-1.5' : 'flex flex-wrap gap-2'}>
          {view.buttons.map((button) => (
            <button
              key={button.reply}
              type="button"
              disabled={!onQuickReply}
              onClick={() => press(button)}
              className={`rounded-lg px-3 py-1.5 text-left text-xs font-semibold disabled:opacity-50 ${
                button.style === 'primary'
                  ? 'bg-w-accent text-w-on-accent hover:opacity-90'
                  : 'border border-w-line text-w-text hover:bg-w-surface2'
              }`}
            >
              {button.label}
              {button.detail && <span className="block text-[10px] font-normal opacity-80">{button.detail}</span>}
            </button>
          ))}
        </div>
        {offline && (
          <p className="text-[11px] text-orange-300">Couldn't send: you're offline. Try again once you're reconnected.</p>
        )}
      </>
    )
  }
  return (
    <Card>
      <p className="text-sm font-semibold text-w-text">{heading}</p>
      {offer && (
        <div className="flex items-center gap-2.5 rounded-xl bg-w-surface2/60 p-2">
          <Photo url={offer.image_url} size={56} alt={offer.item_name} />
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-xs font-semibold text-w-text">{offer.item_name}</p>
            {offer.retailer && <p className="text-[11px] text-w-dim">{offer.retailer}</p>}
          </div>
          {offer.price_text
            ? <span className="text-base font-bold text-w-text">{offer.price_text}</span>
            : <span className="text-[11px] text-orange-300">Price not confirmed</span>}
        </div>
      )}
      {footer}
    </Card>
  )
}

const RECEIPT_TITLE: Record<AgentChatReceipt['status'], string> = {
  paid_test: 'Purchase complete',
  approved: 'Approved',
  no_price: 'Approved, no verified price',
  failed: 'Test charge failed',
}
const RECEIPT_NOTE: Record<AgentChatReceipt['status'], string> = {
  paid_test: 'Charged in Stripe test mode. No real money moved.',
  approved: 'Nothing was charged. Finish checkout at the store.',
  no_price: "Nothing was charged because I couldn't verify the price. Finish checkout at the store.",
  failed: 'Nothing was charged. The purchase is saved on the card.',
}

function ReceiptCard({ receipt: r }: { receipt: AgentChatReceipt }) {
  const product = httpUrl(r.product_url)
  const Icon = r.status === 'paid_test' ? BadgeCheck : r.status === 'failed' ? XOctagon : ShoppingBag
  const date = r.date ? new Date(r.date) : null
  const rows: [string, string | null | undefined, boolean?][] = [
    ['Paid with', r.card_text],
    ['Payment', r.payment_intent_id, true],
    ['Order ref', r.order_ref, true],
    ['Date', date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : r.date],
    ['Problem', r.error],
  ]
  return (
    <Card>
      <div className="flex items-center gap-1.5">
        <Icon size={15} className={r.status === 'paid_test' ? 'text-emerald-400' : r.status === 'failed' ? 'text-red-400' : 'text-w-accent'} />
        <p className="text-sm font-semibold text-w-text">{RECEIPT_TITLE[r.status] ?? 'Purchase'}</p>
        <span className="ml-auto rounded-full bg-orange-500/15 px-2 py-0.5 text-[9px] font-bold tracking-wider text-orange-300">TEST MODE</span>
      </div>
      <div className="flex items-start gap-2.5">
        <Photo url={r.image_url} size={56} alt={r.item_name} />
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-xs font-semibold text-w-text">{r.item_name}</p>
          <p className="text-[11px] text-w-dim">{[r.brand, r.retailer].filter(Boolean).join(' · ')}</p>
        </div>
        {r.total_text && <span className="text-lg font-bold text-w-text">{r.total_text}</span>}
      </div>
      <dl className="space-y-1 border-t border-dashed border-w-line pt-2 text-[11px]">
        {rows.filter(([, value]) => value).map(([label, value, mono]) => (
          <div key={label} className="flex gap-2">
            <dt className="w-16 shrink-0 text-w-dim">{label}</dt>
            <dd className={`min-w-0 break-all text-w-text ${mono ? 'font-mono' : ''}`}>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-[11px] text-w-dim">{RECEIPT_NOTE[r.status]}</p>
      {product && (
        <a
          href={product}
          {...EXTERNAL}
          className="inline-flex items-center gap-1.5 rounded-lg border border-w-line px-3 py-1.5 text-xs font-semibold text-w-text hover:bg-w-surface2"
        >
          {r.status === 'paid_test' ? 'View product' : 'Finish checkout'} <ExternalLink size={12} />
        </a>
      )}
    </Card>
  )
}

export default function AgentCardMessage({
  metadata, content, userId, onQuickReply,
}: {
  metadata: AgentChatMetadata
  /** Message text without the ticket marker (a question's heading fallback). */
  content: string
  /** The viewer: a buy / card question shows its buttons only to its owner. */
  userId?: string
  /** Sends the reply; false when it couldn't go out (offline). */
  onQuickReply?: (reply: string) => boolean
}) {
  if (metadata.kind === 'agent_card_result' && metadata.result) return <ResultCard result={metadata.result} />
  if (metadata.kind === 'agent_card_receipt' && metadata.receipt) return <ReceiptCard receipt={metadata.receipt} />
  if (metadata.kind === 'agent_card_prompt' && metadata.view) {
    // The heading is the server's fixed question text; the content holds the
    // user-written card title and is never parsed for it.
    const heading = metadata.view.question || content
    return (
      <PromptCard meta={metadata} view={metadata.view} heading={heading} userId={userId} onQuickReply={onQuickReply} />
    )
  }
  return null
}
