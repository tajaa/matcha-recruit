import { useEffect, useState } from 'react'
import { Flame, Sparkles, Star, TrendingUp } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Card, Spinner } from '../../components/ui'
import type { BadgeItem, LedgerEntry, PointsBalance } from '../../api/types'

export default function Rewards() {
  const [balance, setBalance] = useState<PointsBalance | null>(null)
  const [badges, setBadges] = useState<BadgeItem[]>([])
  const [ledger, setLedger] = useState<LedgerEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      tellusApi.get<PointsBalance>('/rewards/balance'),
      tellusApi.get<BadgeItem[]>('/badges'),
      tellusApi.get<LedgerEntry[]>('/rewards/ledger?limit=8'),
    ]).then(([b, bd, l]) => { setBalance(b); setBadges(bd); setLedger(l) })
      .finally(() => setLoading(false))
  }, [])

  if (loading || !balance) return <Spinner />

  const span = Math.max(1, balance.level_ceiling - balance.level_floor)
  const into = balance.lifetime_points - balance.level_floor
  const pct = Math.min(100, Math.round((into / span) * 100))

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="sm:col-span-2">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-tu-faint">Points balance</p>
              <p className="mt-1 text-4xl font-black text-tu-accent">{balance.points_balance.toLocaleString()}</p>
              <p className="mt-1 text-xs text-tu-faint">{balance.lifetime_points.toLocaleString()} earned all-time</p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-tu-accent/10 text-tu-accent">
              <Star className="h-6 w-6" />
            </div>
          </div>
          <div className="mt-5">
            <div className="mb-1 flex items-center justify-between text-xs text-tu-dim">
              <span className="font-semibold text-tu-text">Level {balance.level}</span>
              <span>{balance.points_to_next_level} pts to level {balance.level + 1}</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-tu-panel2">
              <div className="h-full rounded-full bg-tu-accent transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex h-full flex-col justify-center gap-4">
            <div className="flex items-center gap-3">
              <Flame className="h-5 w-5 text-tu-accent" />
              <div>
                <p className="text-xl font-bold">{balance.current_streak} day{balance.current_streak === 1 ? '' : 's'}</p>
                <p className="text-xs text-tu-faint">current streak</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <TrendingUp className="h-5 w-5 text-tu-dim" />
              <div>
                <p className="text-xl font-bold">{balance.longest_streak}</p>
                <p className="text-xs text-tu-faint">longest streak</p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-bold"><Sparkles className="h-4 w-4 text-tu-accent" /> Badges</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {badges.map((b) => (
            <div key={b.key} title={b.description ?? ''}
              className={`rounded-xl border p-3 text-center ${b.earned ? 'border-tu-accent/40 bg-tu-accent/5' : 'border-tu-border opacity-40'}`}>
              <div className={`mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-full ${b.earned ? 'bg-tu-accent/20 text-tu-accent' : 'bg-tu-panel2 text-tu-faint'}`}>
                <Star className="h-4 w-4" />
              </div>
              <p className="text-xs font-semibold">{b.name}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-bold">Recent activity</h2>
        <Card className="p-0">
          {ledger.length === 0 ? (
            <p className="p-5 text-sm text-tu-faint">No activity yet — give some feedback to start earning.</p>
          ) : (
            <ul className="divide-y divide-tu-border">
              {ledger.map((l) => (
                <li key={l.id} className="flex items-center justify-between px-5 py-3 text-sm">
                  <span className="text-tu-dim">{l.description || l.reason}</span>
                  <span className={l.delta >= 0 ? 'font-semibold text-tu-good' : 'font-semibold text-tu-bad'}>
                    {l.delta >= 0 ? '+' : ''}{l.delta}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  )
}
