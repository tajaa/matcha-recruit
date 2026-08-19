import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, ScanLine, XCircle } from 'lucide-react'
import { loyaltyApi } from '../../api/loyalty'
import { Button, Input, Select, Spinner } from '../../components/ui'
import { useBusinesses } from '../../hooks/useBusinesses'
import { useQrScanner } from '../../hooks/useQrScanner'
import type { LoyaltyEarnResult } from '../../api/types'

function centsFromText(value: string): number | null {
  if (!/^\d{1,5}(\.\d{0,2})?$/.test(value)) return null
  const [whole, fraction = ''] = value.split('.')
  const cents = Number(`${whole}${fraction.padEnd(2, '0')}`)
  return Number.isSafeInteger(cents) && cents > 0 ? cents : null
}

export default function LoyaltyCounter() {
  const { brandId = '' } = useParams()
  const { membershipFor, loading } = useBusinesses()
  const membership = membershipFor(brandId)
  const [storeId, setStoreId] = useState('')
  const [amount, setAmount] = useState('')
  const [manual, setManual] = useState('')
  const [result, setResult] = useState<LoyaltyEarnResult | { reward_title: string; store_name: string } | null>(null)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState('')
  const busy = useRef(false)
  useEffect(() => { if (!storeId && membership?.stores[0]) setStoreId(membership.stores[0].id) }, [membership?.stores, storeId])
  async function handle(raw: string) {
    if (busy.current || !storeId) return
    const value = raw.trim()
    if (!value) return
    busy.current = true; setProcessing(true); setError('')
    try {
      if (value.includes('TU-LR1:')) {
        setResult(await loyaltyApi.redeem(brandId, storeId, value))
      } else {
        const cents = centsFromText(amount)
        if (cents === null) throw new Error('Enter a purchase amount before scanning.')
        setResult(await loyaltyApi.purchase(brandId, storeId, value, cents))
      }
      setManual('')
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not process this code.') }
    finally { busy.current = false; setProcessing(false) }
  }
  const paused = result !== null || processing
  const { videoRef, start, state } = useQrScanner({ onDecode: (value) => void handle(value), paused })
  if (loading || !membership) return <Spinner />
  return <div className="space-y-5"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-tu-accent">{membership.brand_name}</p><h1 className="mt-2 text-2xl font-black">Counter</h1><p className="mt-1 text-sm text-tu-dim">Scan a member card to award purchase points or a loyalty reward to redeem.</p></div><Select label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)} options={membership.stores.map((store) => ({ value: store.id, label: store.name }))} /><Input label="Purchase subtotal (optional for reward redemption)" value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder="12.50" /><div className="relative overflow-hidden rounded-2xl border border-tu-border bg-black"><video ref={videoRef} playsInline muted className={`h-72 w-full object-cover ${paused ? 'hidden' : ''}`} />{state !== 'scanning' && <div className="flex h-72 items-center justify-center"><Button onClick={() => void start()}><ScanLine className="h-4 w-4" /> Start camera</Button></div>}</div><form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); void handle(manual) }}><Input label="Manual code" value={manual} onChange={(e) => setManual(e.target.value)} placeholder="Paste member or reward code" /><Button type="submit" disabled={!manual.trim()}>Accept</Button></form>{error && <p className="rounded-lg bg-tu-bad/10 p-3 text-sm text-tu-bad">{error}</p>}{result && <div className="rounded-2xl border border-tu-good/30 bg-tu-good/10 p-6 text-center"><CheckCircle2 className="mx-auto h-10 w-10 text-tu-good" /><p className="mt-3 text-lg font-bold">{'reward_title' in result ? result.reward_title : result.awarded ? `Awarded ${result.points} points` : 'No points awarded'}</p><p className="mt-1 text-sm text-tu-dim">{'store_name' in result ? result.store_name : `${result.points_balance} points remaining`}</p><Button className="mt-4" onClick={() => setResult(null)}>Scan next</Button></div>}{state === 'error' && <p className="text-sm text-tu-faint"><XCircle className="mr-1 inline h-4 w-4" /> Camera unavailable. Use manual entry.</p>}</div>
}
