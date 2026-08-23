import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Copy, ExternalLink, Gift, MapPin, Smartphone, Ticket } from 'lucide-react'
import { QRCodeCanvas } from 'qrcode.react'
import { shoutoutApi } from '../api/shoutouts'
import { ApiError, getTellusToken } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Button, Card, ErrorText, Spinner } from '../components/ui'
import { stashReturnTo } from '../utils/returnTo'
import type { ShoutoutOfferPreview } from '../api/types'

export default function ShoutoutOffer() {
  const { token, code } = useParams()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { account, loading: accountLoading } = useAccount()
  const [preview, setPreview] = useState<ShoutoutOfferPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const wantsAutoClaim = params.get('claim') === '1'
  const resumePath = code ? `/o/code/${code}?claim=1` : `/o/${token ?? ''}?claim=1`
  const isBrand = account?.account_type === 'brand'
  const installUrl = (import.meta.env.VITE_TELLUS_IOS_INSTALL_URL as string | undefined)?.trim()
  const isAndroid = /android/i.test(navigator.userAgent)

  useEffect(() => {
    let live = true
    const request = code ? shoutoutApi.previewCode(code) : shoutoutApi.previewOffer(token ?? '')
    request.then((next) => { if (live) setPreview(next) }).catch((e) => {
      if (live) setError(e instanceof Error ? e.message : 'This offer link is not available.')
    }).finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [token, code])

  const bounceToLogin = useCallback(() => {
    stashReturnTo(resumePath)
    navigate('/login?returnTo=' + encodeURIComponent(resumePath))
  }, [navigate, resumePath])

  const doClaim = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const result = code ? await shoutoutApi.claimCode(code) : await shoutoutApi.claimOffer(token ?? '')
      navigate(`/card/${result.card_token}`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { bounceToLogin(); return }
      if (e instanceof ApiError && e.code === 'app_install_required') return
      setError(e instanceof Error ? e.message : 'Could not claim this offer.')
    } finally {
      setBusy(false)
    }
  }, [bounceToLogin, code, navigate, token])

  const autoFired = useRef(false)
  useEffect(() => {
    if (autoFired.current || !wantsAutoClaim || !preview?.available || !preview.web_claim_allowed || accountLoading || isBrand || !getTellusToken()) return
    autoFired.current = true
    void doClaim()
  }, [accountLoading, doClaim, isBrand, preview, wantsAutoClaim])

  if (loading) return <div className="min-h-screen"><Spinner /></div>
  if (!preview) return <div className="mx-auto max-w-md px-4 py-16 text-center"><h1 className="text-lg font-bold">Offer unavailable</h1><p className="mt-2 text-sm text-tu-dim">{error || 'This offer link is not available.'}</p></div>

  const unavailable = !preview.available && !preview.already_claimed
  const needsApp = preview.require_app_install && !preview.web_claim_allowed
  const offerUrl = window.location.href

  return <div className="mx-auto max-w-md px-4 py-10">
    <div className="mb-6 text-center">
      {preview.brand_logo_url && <img src={preview.brand_logo_url} alt="" className="mx-auto mb-3 h-14 w-14 rounded-2xl object-cover" />}
      <p className="text-sm text-tu-dim">{preview.brand_name}</p>
      <h1 className="mt-1 text-2xl font-black">A thank-you for your shoutout</h1>
    </div>
    <Card className={unavailable ? 'opacity-70' : ''}>
      <div className="flex items-start gap-3"><Gift className="mt-0.5 h-5 w-5 shrink-0 text-tu-accent" /><div><p className="font-semibold">{preview.reward_text}</p>{preview.offer_terms && <p className="mt-1 whitespace-pre-wrap text-sm text-tu-dim">{preview.offer_terms}</p>}</div></div>
      {preview.store_name && <p className="mt-4 flex items-center gap-1.5 text-xs text-tu-faint"><MapPin className="h-3.5 w-3.5" /> Redeem at {preview.store_name}</p>}
      <div className="mt-3 flex items-center justify-between rounded-lg border border-dashed border-tu-border bg-tu-panel2 px-3 py-2"><span className="font-mono text-sm tracking-[0.2em]">{preview.short_code}</span><button type="button" className="inline-flex items-center gap-1 text-xs text-tu-accent" onClick={() => void navigator.clipboard.writeText(preview.short_code)}><Copy className="h-3.5 w-3.5" /> Copy</button></div>
      <p className="mt-2 text-xs text-tu-faint">Expires {new Date(preview.claim_expires_at).toLocaleDateString()}</p>
      <div className="mt-5 space-y-3">
        <ErrorText>{error}</ErrorText>
        {preview.already_claimed && preview.card_token ? <>
          <p className="flex items-center gap-1.5 text-sm text-tu-good"><Ticket className="h-4 w-4" /> This offer is already in your account.</p>
          <Button className="w-full" onClick={() => navigate(`/card/${preview.card_token}`)}>View reward card</Button>
        </> : unavailable ? <p className="rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2.5 text-sm text-tu-dim">This offer is expired, revoked, or already claimed.</p>
          : isBrand ? <p className="rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2.5 text-sm text-tu-dim">Sign in with a consumer account to claim this reward.</p>
            : needsApp ? <AppInstallPrompt isAndroid={isAndroid} installUrl={installUrl} offerUrl={offerUrl} onSignIn={bounceToLogin} />
              : !account ? <Button className="w-full" onClick={bounceToLogin}>Sign in to claim</Button>
                : <Button className="w-full" loading={busy} onClick={() => void doClaim()}>Claim reward</Button>}
      </div>
    </Card>
    <div className="mt-6 flex justify-center"><QRCodeCanvas value={offerUrl} size={112} bgColor="transparent" fgColor="#f5f5f4" /></div>
  </div>
}

function AppInstallPrompt({ isAndroid, installUrl, offerUrl, onSignIn }: { isAndroid: boolean; installUrl?: string; offerUrl: string; onSignIn: () => void }) {
  if (isAndroid) return <p className="rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2.5 text-sm text-tu-dim">The Tell-Us app is iPhone-only right now. Save this reward code and try again from an iPhone.</p>
  return <div className="space-y-3 rounded-lg border border-tu-accent/30 bg-tu-accent/5 p-3">
    <div className="flex gap-2"><Smartphone className="h-5 w-5 shrink-0 text-tu-accent" /><p className="text-sm">This thank-you is for new Tell-Us customers. Install the iPhone app, sign up, then enter the reward code above.</p></div>
    {installUrl ? <a className="flex w-full items-center justify-center gap-2 rounded-lg bg-tu-accent px-3 py-2 font-medium text-black" href={installUrl}><ExternalLink className="h-4 w-4" /> Get the iPhone app</a> : <p className="text-xs text-tu-dim">The app install link will be available when the public iPhone release launches.</p>}
    <button type="button" className="block w-full text-center text-xs text-tu-accent hover:underline" onClick={onSignIn}>Already have a Tell-Us account? Sign in to claim on the web.</button>
    <a className="block text-center text-xs text-tu-accent hover:underline" href={offerUrl}>Already have the app? Open this offer there.</a>
  </div>
}
