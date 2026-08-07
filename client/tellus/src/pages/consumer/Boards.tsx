import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Megaphone } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Card, Chip, Empty, ErrorText, Spinner } from '../../components/ui'
import type { BoardMembership } from '../../api/types'

function statusChip(status: BoardMembership['status']) {
  if (status === 'approved') return <Chip tone="positive">Member</Chip>
  if (status === 'pending') return <Chip>Pending approval</Chip>
  if (status === 'declined') return <Chip tone="negative">Declined</Chip>
  if (status === 'left') return <Chip>You left</Chip>
  if (status === 'removed') return <Chip tone="negative">Removed</Chip>
  return <Chip>Cancelled</Chip>
}

export default function Boards() {
  const [items, setItems] = useState<BoardMembership[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    tellusApi.get<BoardMembership[]>('/me/board-memberships')
      .then(setItems)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load boards'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />
  if (err) return <ErrorText>{err}</ErrorText>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-lg font-semibold"><Megaphone className="h-4.5 w-4.5 text-tu-accent" /> Regulars boards</h1>
        <p className="mt-0.5 text-sm text-tu-dim">News, deals, and events from the brands that let you in.</p>
      </div>

      {items.length === 0 ? (
        <Empty>
          You're not on any regulars board yet.{' '}
          <Link to="/places" className="font-semibold text-tu-accent hover:underline">Find a business →</Link>
        </Empty>
      ) : (
        <div className="space-y-3">
          {items.map((m) => {
            const content = (
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {m.logo_url && <img src={m.logo_url} alt="" className="h-9 w-9 rounded-lg object-cover" />}
                  <span className="text-sm font-semibold">{m.brand_name}</span>
                </div>
                {statusChip(m.status)}
              </div>
            )
            return m.status === 'approved' ? (
              <Link key={m.id} to={`/boards/${m.brand_slug}`}>
                <Card className="transition hover:border-tu-accent">{content}</Card>
              </Link>
            ) : (
              <Card key={m.id}>{content}</Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
