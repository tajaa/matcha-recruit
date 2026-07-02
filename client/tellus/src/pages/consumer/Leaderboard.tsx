import { useEffect, useState } from 'react'
import { Crown } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { useAccount } from '../../hooks/useAccount'
import { Card, Empty, Spinner } from '../../components/ui'
import type { LeaderboardEntry } from '../../api/types'

export default function Leaderboard() {
  const { account } = useAccount()
  const [rows, setRows] = useState<LeaderboardEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    tellusApi.get<LeaderboardEntry[]>('/leaderboard').then(setRows).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-bold">Leaderboard</h1>
        <p className="text-sm text-tu-faint">{account?.city ? `Top in ${account.city}` : 'Top contributors'}</p>
      </div>
      {rows.length === 0 ? (
        <Empty>No ranked contributors yet — be the first!</Empty>
      ) : (
        <Card className="p-0">
          <ul className="divide-y divide-tu-border">
            {rows.map((r) => (
              <li key={r.account_id} className={`flex items-center gap-3 px-5 py-3 ${r.is_you ? 'bg-tu-accent/5' : ''}`}>
                <span className={`w-6 text-center text-sm font-bold ${r.rank <= 3 ? 'text-tu-accent' : 'text-tu-faint'}`}>
                  {r.rank === 1 ? <Crown className="mx-auto h-4 w-4" /> : r.rank}
                </span>
                <span className="flex-1 text-sm font-medium">{r.display_name}{r.is_you && <span className="ml-2 text-xs text-tu-accent">you</span>}</span>
                <span className="text-xs text-tu-faint">Lv {r.level}</span>
                <span className="w-20 text-right text-sm font-semibold">{r.lifetime_points.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
