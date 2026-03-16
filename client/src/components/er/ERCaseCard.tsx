import { Card, Badge, type BadgeVariant } from '../ui'
import type { ERCase } from '../../types/er'
import { categoryLabel, statusLabel } from '../../types/er'

const statusVariant: Record<string, BadgeVariant> = {
  open: 'warning',
  in_review: 'neutral',
  pending_determination: 'warning',
  closed: 'success',
}

type ERCaseCardProps = {
  case_: ERCase
  onClick: () => void
  selected?: boolean
}

export function ERCaseCard({ case_: c, onClick, selected }: ERCaseCardProps) {
  return (
    <Card
      className={`p-5 cursor-pointer transition-colors hover:border-zinc-700 ${
        selected ? 'border-zinc-600' : ''
      }`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-zinc-500 font-mono">{c.case_number}</span>
            <Badge variant={statusVariant[c.status] ?? 'neutral'}>
              {statusLabel[c.status] ?? c.status}
            </Badge>
            <Badge variant="neutral">
              {categoryLabel[c.category ?? ''] ?? c.category ?? '—'}
            </Badge>
          </div>
          <p className="text-sm font-medium text-zinc-100 truncate">{c.title}</p>
          {c.description && (
            <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{c.description}</p>
          )}
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-zinc-500">
            {new Date(c.created_at).toLocaleDateString()}
          </p>
          {c.document_count > 0 && (
            <p className="text-xs text-zinc-600 mt-1">
              {c.document_count} doc{c.document_count > 1 ? 's' : ''}
            </p>
          )}
        </div>
      </div>
    </Card>
  )
}
