import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Gift, Ticket } from 'lucide-react'
import { ApiError, getTellusToken } from '../api/tellusClient'
import { promoApi } from '../api/promo'
import { useAccount } from '../hooks/useAccount'
import { Button, Card, ErrorText, Spinner } from '../components/ui'
import { stashReturnTo } from '../utils/returnTo'
import type { ClaimPreview, ClaimUnavailableReason } from '../api/types'

// Mirrors _CLAIM_UNAVAILABLE_MESSAGES in server/app/tellus/services/promo_service.py.
const UNAVAILABLE_COPY: Record<ClaimUnavailableReason, string> = {
  ok: "This promo isn't available right now.",
  cap_reached: 'This promo has reached its claim limit.',
  cancelled: 'This promo was cancelled.',
  brand_inactive: "This brand's account is no longer active.",
  paused: "This promo isn't currently active.",
  not_started: "This promo hasn't started yet.",
  ended: 'This promo has ended.',
}

export default function Claim() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { account, loading: accountLoading } = useAccount()

  const [preview, setPreview] = useState<ClaimPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const isBrand = account?.account_type === 'brand'
  const wantsAutoClaim = params.get('claim') === '1'
  // Path the login bounce comes back to — ?claim=1 makes the return trip
  // finish the claim instead of dumping the user on the button again.
  const resumePath = `/p/${token}?claim=1`

  useEffect(() => {
    let live = true
    promoApi.claimPreview(token)
      .then((p) => { if (live) setPreview(p) })
      .catch(() => { if (live) setLoadErr("This promo link isn't available.") })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [token])

  const bounceToLogin = useCallback(() => {
    stashReturnTo(resumePath)
    navigate('/login?returnTo=' + encodeURIComponent(resumePath))
  }, [navigate, resumePath])

  const doClaim = useCallback(async () => {
    setErr('')
    setBusy(true)
    try {
      const res = await promoApi.claim(token)
      navigate(`/card/${res.card_token}`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { bounceToLogin(); return }
      if (e instanceof ApiError && e.status === 410) {
        // The preview we rendered from is stale (cap filled / campaign ended
        // between page load and click) — refetch so the reason panel replaces
        // the claim button rather than leaving a button that keeps failing.
        try { setPreview(await promoApi.claimPreview(token)) } catch { /* keep what we have */ }
        setErr(e.message)
        return
      }
      setErr(e instanceof Error ? e.message : 'Could not claim this reward.')
    } finally {
      setBusy(false)
    }
  }, [bounceToLogin, navigate, token])

  function onClaimClick() {
    if (!getTellusToken()) { bounceToLogin(); return }
    void doClaim()
  }

  // Resume after the login bounce. The ref latch (not state) is what makes
  // this fire exactly once — StrictMode double-invokes effects in dev and any
  // re-render before the POST resolves would otherwise submit again.
  const autoFired = useRef(false)
  useEffect(() => {
    if (autoFired.current || !wantsAutoClaim) return
    if (!preview?.available || preview.already_claimed) return
    if (!getTellusToken() || accountLoading || isBrand) return
    autoFired.current = true
    void doClaim()
  }, [wantsAutoClaim, preview, accountLoading, isBrand, doClaim])

  if (loading) return <div className="min-h-screen"><Spinner /></div>

  if (loadErr || !preview) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <h1 className="text-lg font-bold">Promo unavailable</h1>
        <p className="mt-2 text-sm text-tu-dim">{loadErr || "This promo link isn't available."}</p>
      </div>
    )
  }

  const unavailable = !preview.available && !preview.already_claimed

  return (
    <div className="mx-auto max-w-md px-4 py-8">
      <div className="mb-6 text-center">
        {preview.brand_logo_url && (
          <img src={preview.brand_logo_url} alt="" className="mx-auto mb-3 h-12 w-12 rounded-xl object-cover" />
        )}
        <p className="text-sm text-tu-dim">{preview.brand_name}</p>
        <h1 className="text-xl font-bold">{preview.title}</h1>
      </div>

      <Card className={unavailable ? 'opacity-60' : ''}>
        <div className="flex items-start gap-3">
          <Gift className="mt-0.5 h-5 w-5 shrink-0 text-tu-accent" />
          <div>
            <p className="font-semibold text-tu-text">{preview.reward_text}</p>
            {preview.description && <p className="mt-1 text-sm text-tu-dim">{preview.description}</p>}
          </div>
        </div>

        {preview.flyer_image_url && (
          <img src={preview.flyer_image_url} alt="" className="mt-4 w-full rounded-lg border border-tu-border object-cover" />
        )}

        <div className="mt-5 space-y-3">
          <ErrorText>{err}</ErrorText>

          {preview.already_claimed && preview.card_token ? (
            <>
              <p className="flex items-center gap-1.5 text-sm text-tu-good">
                <Ticket className="h-4 w-4" /> You've already claimed this reward.
              </p>
              <Button className="w-full" onClick={() => navigate(`/card/${preview.card_token}`)}>
                View your card
              </Button>
            </>
          ) : unavailable ? (
            <p className="rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2.5 text-sm text-tu-dim">
              {UNAVAILABLE_COPY[preview.reason]}
            </p>
          ) : isBrand ? (
            <p className="rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2.5 text-sm text-tu-dim">
              Reward cards are for customer accounts.
            </p>
          ) : (
            <>
              <Button className="w-full" loading={busy} onClick={onClaimClick}>Claim reward</Button>
              {!getTellusToken() && (
                <p className="text-center text-xs text-tu-faint">
                  You'll sign in first — your card is saved to your account.
                </p>
              )}
            </>
          )}
        </div>
      </Card>
    </div>
  )
}
