import { useState } from 'react'
import {
  BadgeCheck, CheckCircle2, Clock, ExternalLink, ImageIcon, ShoppingBag, Star, XOctagon,
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

function statusText(meta: AgentChatMetadata, sent: string | null): string {
  if (sent) return `You replied “${sent}”`
  switch (meta.prompt_status) {
    case 'answered': return meta.answer ? `Answered: ${meta.answer}` : 'Answered'
    case 'superseded': return 'Replaced by a newer result'
    case 'expired': return 'This question expired'
    default: return 'Closed'
  }
}

function PromptCard({
  meta, view, heading, onQuickReply,
}: {
  meta: AgentChatMetadata
  view: AgentChatPromptView
  heading: string
  onQuickReply?: (reply: string) => void
}) {
  const [sent, setSent] = useState<string | null>(null)
  const open = !sent && (meta.prompt_status ?? 'open') === 'open'
  const stacked = view.buttons.some((b) => b.detail)
  const offer = view.offer
  const press = (button: AgentChatButton) => {
    setSent(button.label)
    onQuickReply?.(button.reply)
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
      {open ? (
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
      ) : (
        <p className="flex items-center gap-1.5 text-[11px] text-w-dim">
          {sent || meta.prompt_status === 'answered' ? <CheckCircle2 size={12} /> : <Clock size={12} />}
          {statusText(meta, sent)}
        </p>
      )}
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
  metadata, content, onQuickReply,
}: {
  metadata: AgentChatMetadata
  /** Message text without the ticket marker (a question's heading fallback). */
  content: string
  onQuickReply?: (reply: string) => void
}) {
  if (metadata.kind === 'agent_card_result' && metadata.result) return <ResultCard result={metadata.result} />
  if (metadata.kind === 'agent_card_receipt' && metadata.receipt) return <ReceiptCard receipt={metadata.receipt} />
  if (metadata.kind === 'agent_card_prompt' && metadata.view) {
    const heading = metadata.prompt_kind === 'show_result'
      ? content.replace(/\s+Reply\b[\s\S]*$/, '').trim()  // drop the typed-reply hint
      : metadata.view.question || content
    return <PromptCard meta={metadata} view={metadata.view} heading={heading} onQuickReply={onQuickReply} />
  }
  return null
}
