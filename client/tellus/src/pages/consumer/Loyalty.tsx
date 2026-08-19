import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Crown, Sparkles } from 'lucide-react'
import { loyaltyApi } from '../../api/loyalty'
import { Card, Empty, Spinner } from '../../components/ui'
import type { LoyaltyProgramSummary } from '../../api/types'

export default function Loyalty() {
  const [programs, setPrograms] = useState<LoyaltyProgramSummary[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { loyaltyApi.listPrograms().then(setPrograms).finally(() => setLoading(false)) }, [])
  if (loading) return <Spinner />
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-tu-accent">Brand loyalty</p>
        <h1 className="mt-2 text-2xl font-black">Your local memberships</h1>
        <p className="mt-1 text-sm text-tu-dim">Separate rewards and standing at each business you visit.</p>
      </div>
      {programs.length === 0 ? <Empty>No active brand programs yet.</Empty> : (
        <div className="grid gap-4 sm:grid-cols-2">
          {programs.map((program) => (
            <Link key={program.brand_id} to={`/loyalty/${program.brand_id}`}>
              <Card className="h-full transition hover:border-tu-accent/60">
                <div className="flex items-start gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-tu-accent/10 text-tu-accent"><Sparkles className="h-5 w-5" /></div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold">{program.brand_name}</p>
                    <p className="truncate text-xs text-tu-faint">{program.name}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-tu-faint" />
                </div>
                <div className="mt-5 flex items-end justify-between">
                  <div><p className="text-3xl font-black text-tu-accent">{program.points_balance.toLocaleString()}</p><p className="text-xs text-tu-faint">{program.point_plural}</p></div>
                  <div className="flex items-center gap-1 text-xs font-semibold text-tu-dim"><Crown className="h-4 w-4 text-tu-accent" /> {program.tier_key}</div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
