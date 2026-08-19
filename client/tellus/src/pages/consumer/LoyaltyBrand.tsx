import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CreditCard, Gift, QrCode } from 'lucide-react'
import { loyaltyApi } from '../../api/loyalty'
import { Button, Card, Empty, Spinner } from '../../components/ui'
import type { LoyaltyLedgerEntry, LoyaltyProgram } from '../../api/types'

export default function LoyaltyBrand() {
  const { brandId = '' } = useParams()
  const [program, setProgram] = useState<LoyaltyProgram | null>(null)
  const [ledger, setLedger] = useState<LoyaltyLedgerEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [message, setMessage] = useState('')
  const [redeemingId, setRedeemingId] = useState<string | null>(null)
  const requestIdsRef = useRef(new Map<string, string>())
  useEffect(() => {
    setLoadError('')
    Promise.all([loyaltyApi.getProgram(brandId), loyaltyApi.listLedger(brandId, 20)])
      .then(([nextProgram, nextLedger]) => { setProgram(nextProgram); setLedger(nextLedger) })
      .catch((error) => setLoadError(error instanceof Error ? error.message : 'Could not load this loyalty program.'))
      .finally(() => setLoading(false))
  }, [brandId])
  async function redeem(rewardId: string) {
    if (redeemingId) return
    let requestId = requestIdsRef.current.get(rewardId)
    if (!requestId) {
      requestId = crypto.randomUUID()
      requestIdsRef.current.set(rewardId, requestId)
    }
    setMessage('')
    setRedeemingId(rewardId)
    try {
      await loyaltyApi.issueRedemption(brandId, rewardId, requestId)
      requestIdsRef.current.delete(rewardId)
      setMessage('Reward issued. Open your redemptions to show it at the counter.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not issue reward.') }
    finally { setRedeemingId(null) }
  }
  if (loading) return <Spinner />
  if (loadError || !program) return <Empty>{loadError || 'Could not load this loyalty program.'}</Empty>
  const balance = program.balance
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-xs font-bold uppercase tracking-[0.18em] text-tu-accent">{program.brand_name}</p><h1 className="mt-2 text-2xl font-black">{program.name}</h1></div>
        <Link to={`/loyalty/${brandId}/card`}><Button><QrCode className="h-4 w-4" /> Member card</Button></Link>
      </div>
      {message && <p className="rounded-lg bg-tu-accent/10 p-3 text-sm text-tu-accent">{message}</p>}
      <Card className="bg-gradient-to-br from-tu-panel to-tu-accent/10">
        <p className="text-xs uppercase tracking-wide text-tu-faint">Your balance</p>
        <div className="mt-2 flex items-end justify-between"><p className="text-5xl font-black text-tu-accent">{balance?.points_balance.toLocaleString() ?? 0}</p><p className="text-sm text-tu-dim">{balance?.tier_key ?? 'bronze'} tier</p></div>
        <p className="mt-2 text-xs text-tu-faint">{balance?.lifetime_points.toLocaleString() ?? 0} lifetime {program.point_plural}</p>
      </Card>
      <section><h2 className="mb-3 flex items-center gap-2 text-sm font-bold"><Gift className="h-4 w-4 text-tu-accent" /> Rewards</h2>
        {program.rewards.length === 0 ? <Empty>No rewards published yet.</Empty> : <div className="grid gap-3 sm:grid-cols-2">{program.rewards.map((reward) => <Card key={reward.id}><p className="font-semibold">{reward.title}</p><p className="mt-1 text-sm text-tu-dim">{reward.description}</p><div className="mt-4 flex items-center justify-between"><span className="text-sm font-bold text-tu-accent">{reward.points_cost} points</span><Button size="sm" onClick={() => void redeem(reward.id)} disabled={(balance?.points_balance ?? 0) < reward.points_cost || redeemingId !== null}>{redeemingId === reward.id ? 'Redeeming…' : 'Redeem'}</Button></div></Card>)}</div>}
      </section>
      <section><h2 className="mb-3 flex items-center gap-2 text-sm font-bold"><CreditCard className="h-4 w-4 text-tu-accent" /> Activity</h2><Card className="p-0">{ledger.length === 0 ? <p className="p-5 text-sm text-tu-faint">No brand activity yet.</p> : <ul className="divide-y divide-tu-border">{ledger.map((entry) => <li key={entry.id} className="flex justify-between px-5 py-3 text-sm"><span className="text-tu-dim">{entry.description ?? entry.reason}</span><span className={entry.delta > 0 ? 'font-semibold text-tu-good' : 'font-semibold text-tu-bad'}>{entry.delta > 0 ? '+' : ''}{entry.delta}</span></li>)}</ul>}</Card></section>
    </div>
  )
}
