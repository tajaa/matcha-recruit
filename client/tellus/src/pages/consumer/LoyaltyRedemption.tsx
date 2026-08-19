import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { loyaltyApi } from '../../api/loyalty'
import { Spinner } from '../../components/ui'
import type { LoyaltyRedemption } from '../../api/types'

export default function LoyaltyRedemption() {
  const { token = '' } = useParams()
  const [redemption, setRedemption] = useState<LoyaltyRedemption | null>(null)
  useEffect(() => { loyaltyApi.listRedemptions().then((rows) => setRedemption(rows.find((row) => row.token === token) ?? null)) }, [token])
  if (!redemption) return <Spinner />
  return <div className="flex min-h-screen flex-col items-center justify-center bg-tu-bg p-6 text-center"><h1 className="text-xl font-black">{redemption.reward_title}</h1><p className="mt-1 text-sm text-tu-dim">{redemption.brand_name}</p><div className="mt-6 rounded-3xl bg-white p-6"><QRCodeSVG value={redemption.qr_payload} size={260} includeMargin /></div><p className="mt-4 text-sm text-tu-dim">{redemption.effective_status === 'expired' ? 'Expired' : 'Show this code at the counter.'}</p></div>
}
