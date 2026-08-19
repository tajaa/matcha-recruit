import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { loyaltyApi } from '../../api/loyalty'
import { Spinner } from '../../components/ui'
import type { LoyaltyMemberQr } from '../../api/types'

export default function MemberCard() {
  const { brandId = '' } = useParams()
  const [qr, setQr] = useState<LoyaltyMemberQr | null>(null)
  const [expiresAt, setExpiresAt] = useState<number | null>(null)
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const scheduleRef = useRef<number | undefined>(undefined)
  const refresh = useCallback(async () => {
    try {
      const next = await loyaltyApi.mintMemberQr(brandId)
      setQr(next)
      const expiry = Date.parse(next.expires_at)
      setExpiresAt(expiry)
      const remainingMs = Math.max(0, expiry - Date.now())
      scheduleRef.current = window.setTimeout(() => { void refresh() }, Math.max(0, remainingMs - 10_000))
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not load member card.') }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [brandId])
  useEffect(() => {
    void refresh()
    return () => window.clearTimeout(scheduleRef.current)
  }, [refresh])
  useEffect(() => {
    if (expiresAt === null) return
    const id = window.setInterval(() => {
      setSeconds(Math.max(0, Math.floor((expiresAt - Date.now()) / 1000)))
    }, 1000)
    return () => window.clearInterval(id)
  }, [expiresAt])
  if (error) return <div className="flex min-h-screen items-center justify-center p-6 text-center text-sm text-tu-bad">{error}</div>
  if (!qr) return <div className="min-h-screen bg-tu-bg"><Spinner /></div>
  return <div className="flex min-h-screen flex-col items-center justify-center bg-tu-bg p-6 text-center"><p className="text-xs font-bold uppercase tracking-[0.2em] text-tu-accent">Tell-Us member card</p><div className="mt-5 rounded-3xl bg-white p-6 shadow-2xl"><QRCodeSVG value={qr.qr_payload} size={260} includeMargin /></div><p className="mt-5 text-sm text-tu-dim">Show this code to staff</p><p className="mt-1 font-mono text-xs text-tu-faint">Refreshes in {seconds}s</p></div>
}
