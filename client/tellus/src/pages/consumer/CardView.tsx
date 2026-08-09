import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { QRCodeCanvas } from 'qrcode.react'
import { ArrowLeft, BadgeCheck, Ban, Clock } from 'lucide-react'
import { promoApi } from '../../api/promo'
import { Chip, ErrorText, Spinner } from '../../components/ui'
import type { EffectiveCardStatus, PromoCard } from '../../api/types'

const STATUS_TONE: Record<EffectiveCardStatus, string> = {
  issued: 'positive', redeemed: 'neutral', expired: 'negative', cancelled: 'negative',
}

const STATUS_LABEL: Record<EffectiveCardStatus, string> = {
  issued: 'Ready to scan', redeemed: 'Redeemed', expired: 'Expired', cancelled: 'Cancelled',
}

// Chromium-only; typed locally so the guarded call doesn't depend on the
// installed lib.dom shipping WakeLock, and never throws on Safari/Firefox.
type WakeLockSentinelLike = { release: () => Promise<void> }
type WakeLockNavigator = Navigator & {
  wakeLock?: { request: (type: 'screen') => Promise<WakeLockSentinelLike> }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString()
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export default function CardView() {
  const { cardToken = '' } = useParams()
  const navigate = useNavigate()
  const [card, setCard] = useState<PromoCard | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    promoApi.myCard(cardToken)
      .then((c) => { if (!cancelled) setCard(c) })
      .catch(() => { if (!cancelled) setError('Reward card not found') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [cardToken])

  // Keep the screen awake only while the QR is actually on display — a card
  // held up at a counter shouldn't dim mid-scan. Best-effort: the request can
  // reject (backgrounded tab, low battery) and the API may not exist at all.
  const showingQr = card?.status === 'issued'
  useEffect(() => {
    if (!showingQr) return
    let sentinel: WakeLockSentinelLike | null = null
    let released = false
    const wakeLock = (navigator as WakeLockNavigator).wakeLock
    wakeLock?.request('screen').then((s) => {
      if (released) { void s.release().catch(() => {}) } else { sentinel = s }
    }).catch(() => {})
    return () => {
      released = true
      void sentinel?.release().catch(() => {})
    }
  }, [showingQr])

  if (loading) {
    return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  }

  if (error || !card) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-tu-bg p-6 text-center">
        <Ban className="h-10 w-10 text-tu-faint" />
        <div className="space-y-1">
          <p className="font-semibold">Reward card not found</p>
          <ErrorText>This card may have been removed, or the link is wrong.</ErrorText>
        </div>
        <button onClick={() => navigate(-1)} className="text-sm text-tu-accent hover:underline">Go back</button>
      </div>
    )
  }

  const inactive = card.status === 'expired' || card.status === 'cancelled'

  return (
    <div className="min-h-screen bg-tu-bg px-5 pb-12 pt-5">
      <div className={`mx-auto flex w-full max-w-sm flex-col items-center ${inactive ? 'opacity-60' : ''}`}>
        <button
          onClick={() => navigate(-1)}
          className="mb-6 flex items-center gap-1 self-start text-sm text-tu-dim hover:text-tu-text"
        >
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        <div className="flex flex-col items-center gap-3 text-center">
          {card.brand_logo_url && (
            <img
              src={card.brand_logo_url}
              alt={card.brand_name}
              className="h-14 w-14 rounded-full border border-tu-border object-cover"
            />
          )}
          <div className="space-y-1">
            <p className="text-xs uppercase tracking-widest text-tu-faint">{card.brand_name}</p>
            <h1 className="text-xl font-bold">{card.campaign_title}</h1>
            <p className="text-sm text-tu-dim">{card.reward_text}</p>
          </div>
          <Chip tone={STATUS_TONE[card.status]}>{STATUS_LABEL[card.status]}</Chip>
        </div>

        {card.status === 'issued' && (
          <div className="mt-8 flex w-full flex-col items-center gap-4">
            {/* QR needs a light quiet zone to scan reliably, regardless of app theme. */}
            <div className="rounded-2xl bg-white p-5">
              <QRCodeCanvas value={window.location.origin + card.card_url} size={280} />
            </div>
            <div className="text-center">
              <p className="text-xs text-tu-faint">Can’t scan? Give staff this code</p>
              <p className="mt-1 font-mono text-sm tracking-widest text-tu-accent">{card.card_token}</p>
            </div>
            <p className="text-xs text-tu-faint">Expires {formatDate(card.expires_at)}</p>
          </div>
        )}

        {card.status === 'redeemed' && (
          <div className="mt-10 flex flex-col items-center gap-4 text-center">
            <div className="flex h-32 w-32 items-center justify-center rounded-full border-4 border-tu-good/40">
              <BadgeCheck className="h-16 w-16 text-tu-good" />
            </div>
            <p className="text-lg font-bold uppercase tracking-[0.2em] text-tu-good">Redeemed</p>
            <div className="space-y-0.5 text-xs text-tu-faint">
              {card.redeemed_at && <p>{formatDateTime(card.redeemed_at)}</p>}
              {card.redeemed_store_name && <p>{card.redeemed_store_name}</p>}
            </div>
            <p className="mt-1 font-mono text-sm tracking-widest text-tu-faint">{card.card_token}</p>
          </div>
        )}

        {inactive && (
          <div className="mt-10 flex flex-col items-center gap-4 text-center">
            <div className="flex h-32 w-32 items-center justify-center rounded-full border-4 border-tu-border">
              {card.status === 'expired'
                ? <Clock className="h-16 w-16 text-tu-faint" />
                : <Ban className="h-16 w-16 text-tu-faint" />}
            </div>
            <p className="text-lg font-bold uppercase tracking-[0.2em] text-tu-faint">
              {STATUS_LABEL[card.status]}
            </p>
            <p className="text-xs text-tu-faint">
              {card.status === 'expired'
                ? `Expired ${formatDate(card.expires_at)}`
                : 'This card was cancelled by the brand and can no longer be used.'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
