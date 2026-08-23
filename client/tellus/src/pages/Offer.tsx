import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Copy, ExternalLink, Gift, MapPin, QrCode, Smartphone, Ticket } from 'lucide-react'
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
    setBusy(true); setError('')
    try {
      const result = code ? await shoutoutApi.claimCode(code) : await shoutoutApi.claimOffer(token ?? '')
      navigate(`/card/${result.card_token}`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { bounceToLogin(); return }
      setError(e instanceof Error ? e.message : 'Could not claim this offer.')
    } finally { setBusy(false) }
  }, [bounceToLogin, code, navigate, token])

  const autoFired = useRef(false)
  useEffect(() => {
    if (autoFired.current || !wantsAutoClaim || !preview?.available || accountLoading || isBrand || !getTellusToken()) return
    autoFired.current = true
    void doClaim()
  }, [accountLoading, doClaim, isBrand, preview, wantsAutoClaim])

  if (loading) return <div className="min-h-screen"><Spinner /></div>
  if (!preview) return <div className="mx-auto max-w-md px-4 py-16 text-center"><h1 className="text-lg font-bold">Offer unavailable</h1><p className="mt-2 text-sm text-tu-dim">{error || 'This offer link is not available.'}</p></div>

  const unavailable = !preview.available && !preview.already_claimed
  return <div className="mx-auto max-w-md px-4 py-10"><div className="mb-6 text-center">{preview.brand_logo_url && <img src={preview.brand_logo_url} alt="" className="mx-auto mb-3 h-14 w-14 rounded-2xl object-cover" />}<p className="text-sm text-tu-dim">{preview.brand_name}</p><h1 className="mt-1 text-2xl font-black">A thank-you for your shoutout</h1></div><Card className={unavailable ? 'opacity-70' : ''}><div className="flex items-start gap-3"><Gift className="mt-0.5 h-5 w-5 shrink-0 text-tu-accent" /><div><p className="font-semibold">{preview.reward_text}</p>{preview.offer_terms && <p className="mt-1 whitespace-pre-wrap text-sm text-tu-dim">{preview.offer_terms}</p>}</div></div>{preview.store_name && <p className="mt-4 flex items-center gap-1.5 text-xs text-tu-faint"><MapPin className="h-3.5 w-3.5" /> Redeem at {preview.store_name}</p>}<div className="mt-3 flex items-center justify-between rounded-lg border border-dashed border-tu-border bg-tu-panel2 px-3 py-2"><span className="font-mono text-sm tracking-[0.2em]">{preview.short_code}</span><button type="button" className="inline-flex items-center gap-1 text-xs text-tu-accent" onClick={() => void navigator.clipboard.writeText(preview.short_code)}><Copy className="h-3.5 w-3.5" /> Copy</button></div><p className="mt-2 text-xs text-tu-faint">Expires {new Date(preview.claim_expires_at).toLocaleDateString()}</p><div className="mt-5 space-y-3"><ErrorText>{error}</ErrorText>{preview.already_claimed && preview.card_token ? <><p className="flex items-center gap-1.5 text-sm text-tu-good"><Ticket className="h-4 w-4" /> This offer is already in your account.</p><Button className="w-full" onClick={() => navigate(`/card/${preview.card_token}`)}>View reward card</Button></> : unavailable ? <p className="rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2.5 text-sm text-tu-dim">This offer is expired, revoked, or already claimed.</p> : isBrand ? <p className="rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2.5 text-sm text-tu-dim">Reward cards are for customer accounts.</p> : installUrl ? <><a href={installUrl} className="flex w-full items-center justify-center gap-2 rounded-lg bg-tu-accent px-4 py-2 text-sm font-medium text-black hover:bg-tu-accent-soft"><Smartphone className="h-4 w-4" /> Get the iPhone app</a><a href={window.location.href} className="flex items-center justify-center gap-1 text-xs text-tu-accent hover:underline"><ExternalLink className="h-3.5 w-3.5" /> Already have the app? Open your offer</a>{isAndroid && <p className="text-center text-xs text-tu-faint">The Tell-Us iPhone app is not available on Android yet.</p>}<div className="flex flex-col items-center gap-2 border-t border-tu-border pt-4"><div className="rounded-lg bg-white p-2"><QRCodeCanvas value={window.location.href} size={128} /></div><p className="flex items-center gap-1 text-xs text-tu-faint"><QrCode className="h-3.5 w-3.5" /> Scan from a desktop</p></div></> : <><Button className="w-full" loading={busy} onClick={() => getTellusToken() ? void doClaim() : bounceToLogin()}>Claim this reward</Button>{!getTellusToken() && <p className="text-center text-xs text-tu-faint">You will sign in first so the reward is saved to your account.</p>}</>}</div></Card></div>
}
