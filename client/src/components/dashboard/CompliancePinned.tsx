import { useNavigate } from 'react-router-dom'
import { Card, Badge } from '../ui'
import type { PinnedRequirement } from '../../types/compliance'

interface CompliancePinnedProps {
  items: PinnedRequirement[]
  loading: boolean
  onUnpin?: (id: string) => void
}

export function CompliancePinned({ items, loading, onUnpin }: CompliancePinnedProps) {
  const navigate = useNavigate()

  if (loading) {
    return (
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-2">Pinned Requirements</h3>
        <p className="text-xs text-zinc-500 animate-pulse">Loading...</p>
      </Card>
    )
  }

  if (items.length === 0) return null

  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 mb-3">Pinned Requirements</h3>
      <div className="space-y-3">
        {items.map((r) => (
          <div key={r.id} className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm text-zinc-200 truncate">{r.title}</p>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="neutral">{r.jurisdiction_name}</Badge>
                <Badge variant="neutral">{r.category}</Badge>
                {r.location_name && (
                  <span className="text-[10px] text-zinc-600">{r.location_name}</span>
                )}
              </div>
              {r.current_value && (
                <p className="text-xs text-zinc-500 mt-1">{r.current_value}</p>
              )}
            </div>
            {onUnpin && (
              <button
                type="button"
                onClick={() => onUnpin(r.id)}
                className="text-[10px] text-zinc-600 hover:text-zinc-400 shrink-0"
              >
                Unpin
              </button>
            )}
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => navigate('/app/compliance')}
        className="mt-4 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        View all compliance &rarr;
      </button>
    </Card>
  )
}
