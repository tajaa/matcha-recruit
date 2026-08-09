// Counter-device scanner (public route /scan/:deviceToken, rendered bare with
// no Layout chrome). The device token IS the auth — staff open this on a
// tablet, tap Start once, and redeem customer reward-card QRs all shift.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { AlertTriangle, Camera, CheckCircle2, ScanLine, XCircle } from 'lucide-react'
import { promoApi } from '../api/promo'
import { ApiError } from '../api/tellusClient'
import { Button, Input, Spinner } from '../components/ui'
import { useQrScanner } from '../hooks/useQrScanner'
import type { PromoRedeemResult, PromoScanBootstrap } from '../api/types'

function fmtWhen(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'earlier'
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

type Failure = { tone: 'warn' | 'bad'; title: string; message: string }
type Outcome = { ok: true; data: PromoRedeemResult } | { ok: false } & Failure

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null
}

function toFailure(e: unknown): Failure {
  if (e instanceof ApiError) {
    switch (e.code) {
      case 'already_redeemed': {
        const at = str(e.detail?.redeemed_at)
        const store = str(e.detail?.redeemed_store_name) ?? 'this brand'
        return {
          tone: 'warn',
          title: 'Already used',
          message: `Already used ${at ? fmtWhen(at) : 'earlier'} at ${store}`,
        }
      }
      case 'cancelled':
        return { tone: 'bad', title: 'Cancelled', message: 'This promo was cancelled.' }
      case 'expired':
        return { tone: 'bad', title: 'Expired', message: 'This reward card has expired.' }
      case 'brand_inactive':
        return { tone: 'bad', title: 'Unavailable', message: e.message }
    }
  }
  return { tone: 'bad', title: 'Not valid', message: 'Not a valid reward card.' }
}

export default function Scan() {
  const { deviceToken = '' } = useParams()
  const [boot, setBoot] = useState<PromoScanBootstrap | null>(null)
  const [bootErr, setBootErr] = useState('')
  const [loading, setLoading] = useState(true)

  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [busy, setBusy] = useState(false)
  const [manual, setManual] = useState('')
  // Guards the ~150ms window between a decode firing and `paused` reaching the
  // scan loop through a re-render — without it one card can redeem twice.
  const inFlight = useRef(false)

  useEffect(() => {
    promoApi
      .scanBootstrap(deviceToken)
      .then(setBoot)
      .catch((e: unknown) => {
        const status = e instanceof ApiError ? e.status : 0
        setBootErr(
          status === 410
            ? "This brand's account is no longer active."
            : status === 404
              ? "This scanner link isn't available."
              : e instanceof Error
                ? e.message
                : 'This scanner link is unavailable.',
        )
      })
      .finally(() => setLoading(false))
  }, [deviceToken])

  const redeem = useCallback(
    async (cardToken: string) => {
      const value = cardToken.trim()
      if (!value || inFlight.current) return
      inFlight.current = true
      setBusy(true)
      try {
        // The backend extracts a bare token out of a full card URL itself, so
        // the raw QR payload / typed string goes straight through.
        const data = await promoApi.scanRedeem(deviceToken, value)
        setOutcome({ ok: true, data })
        setManual('')
      } catch (e) {
        setOutcome({ ok: false, ...toFailure(e) })
      } finally {
        setBusy(false)
        inFlight.current = false
      }
    },
    [deviceToken],
  )

  const paused = outcome !== null || busy
  const { videoRef, start, state } = useQrScanner({ onDecode: redeem, paused })

  // Best-effort screen wake lock — Chromium-only, absent on Safari.
  useEffect(() => {
    if (state !== 'scanning') return
    let sentinel: WakeLockSentinel | null = null
    let cancelled = false
    navigator.wakeLock
      ?.request('screen')
      .then((s) => {
        if (cancelled) void s.release().catch(() => {})
        else sentinel = s
      })
      .catch(() => {})
    return () => {
      cancelled = true
      void sentinel?.release().catch(() => {})
    }
  }, [state])

  if (loading) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>

  if (bootErr) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-tu-bg px-6 text-center">
        <XCircle className="mb-4 h-12 w-12 text-tu-bad" />
        <h1 className="text-lg font-bold text-tu-text">Scanner unavailable</h1>
        <p className="mt-2 text-sm text-tu-dim">{bootErr}</p>
      </div>
    )
  }

  const live = state === 'starting' || state === 'scanning'

  return (
    <div className="flex min-h-screen flex-col bg-tu-bg text-tu-text">
      <header className="flex items-center gap-3 border-b border-tu-border px-4 py-3">
        {boot?.brand_logo_url && <img src={boot.brand_logo_url} alt="" className="h-9 w-9 rounded-lg object-cover" />}
        <div className="min-w-0">
          <p className="truncate text-sm font-bold">{boot?.brand_name}</p>
          <p className="truncate text-xs text-tu-dim">{boot?.store_name}</p>
        </div>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-tu-faint">
          <ScanLine className="h-3.5 w-3.5" /> Redeem
        </span>
      </header>

      <div className="relative flex-1 overflow-hidden bg-black">
        {/* Kept mounted across the result overlay so resuming doesn't need a
            second getUserMedia prompt — only the decode loop pauses. */}
        <video
          ref={videoRef}
          playsInline
          muted
          className={`h-full w-full object-cover ${live ? '' : 'hidden'}`}
        />
        {live && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="h-56 w-56 rounded-2xl border-2 border-tu-accent/80 shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]" />
          </div>
        )}
        {state === 'starting' && (
          <p className="absolute inset-x-0 bottom-6 text-center text-sm text-white/80">Starting camera…</p>
        )}
        {state === 'scanning' && (
          <p className="absolute inset-x-0 bottom-6 text-center text-sm text-white/80">
            Point at the customer's reward card
          </p>
        )}

        {!live && (
          <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
            <Button onClick={() => void start()} className="px-6 py-3 text-base">
              <Camera className="h-5 w-5" /> Start camera
            </Button>
            {state === 'denied' && (
              <p className="text-sm text-tu-bad">Camera access denied — use manual entry below.</p>
            )}
            {state === 'unsupported' && (
              <p className="text-sm text-tu-bad">Camera scanning isn't supported on this device — use manual entry below.</p>
            )}
            {state === 'error' && (
              <p className="text-sm text-tu-bad">Couldn't start the camera — try again, or use manual entry below.</p>
            )}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          void redeem(manual)
        }}
        className="flex items-end gap-2 border-t border-tu-border px-4 py-3"
      >
        <div className="flex-1">
          <Input
            label="Or enter a card code"
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            placeholder="Card code or link"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
          />
        </div>
        <Button type="submit" loading={busy} disabled={!manual.trim()}>Redeem</Button>
      </form>

      {outcome && (
        <div
          className={`fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 px-8 text-center ${
            outcome.ok ? 'bg-tu-good/15' : outcome.tone === 'warn' ? 'bg-amber-500/15' : 'bg-tu-bad/15'
          } backdrop-blur-sm`}
        >
          {outcome.ok ? (
            <>
              <CheckCircle2 className="h-20 w-20 text-tu-good" />
              <p className="text-3xl font-bold text-tu-good">{outcome.data.reward_text}</p>
              <p className="text-sm text-tu-dim">{outcome.data.campaign_title}</p>
              <p className="text-xs text-tu-faint">Redeemed {fmtWhen(outcome.data.redeemed_at)}</p>
            </>
          ) : (
            <>
              {outcome.tone === 'warn' ? (
                <AlertTriangle className="h-20 w-20 text-amber-400" />
              ) : (
                <XCircle className="h-20 w-20 text-tu-bad" />
              )}
              <p className={`text-2xl font-bold ${outcome.tone === 'warn' ? 'text-amber-400' : 'text-tu-bad'}`}>
                {outcome.title}
              </p>
              <p className="text-sm text-tu-dim">{outcome.message}</p>
            </>
          )}
          <Button onClick={() => setOutcome(null)} variant="soft" className="mt-6 px-6 py-3 text-base">
            Scan next
          </Button>
        </div>
      )}
    </div>
  )
}
