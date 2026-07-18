import { Badge, Card } from '../../../../components/ui'
import { MapPin, HelpCircle } from 'lucide-react'
import type { ComplianceCalendarItem } from '../../../../api/compliance/compliance'
import { STATUS_LABEL, STATUS_HINT, STATUS_VARIANT } from './constants'
import { formatDate, formatDays } from './helpers'

interface ListViewProps {
  grouped: Record<ComplianceCalendarItem['derived_status'], ComplianceCalendarItem[]>
  onView: (item: ComplianceCalendarItem) => void
  onMarkRead: (item: ComplianceCalendarItem) => void
  onDismiss: (item: ComplianceCalendarItem) => void
}

export function ListView({ grouped, onView, onMarkRead, onDismiss }: ListViewProps) {
  const order: ComplianceCalendarItem['derived_status'][] = ['overdue', 'due_soon', 'upcoming', 'future']
  return (
    <div className="space-y-6">
      {order.map((bucket) => {
        const rows = grouped[bucket]
        if (rows.length === 0) return null
        return (
          <section key={bucket}>
            <div className="flex items-center gap-2 mb-2">
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
                {STATUS_LABEL[bucket]}
              </h2>
              <span className="text-xs text-zinc-600">({rows.length})</span>
              <span className="text-xs text-zinc-600" title={STATUS_HINT[bucket]}>
                <HelpCircle size={11} className="inline opacity-60" />
              </span>
            </div>
            <div className="space-y-2">
              {rows.map((item) => (
                <Card
                  key={item.id}
                  className="hover:border-zinc-700 cursor-pointer transition-colors"
                >
                  <div className="flex items-start gap-3" onClick={() => onMarkRead(item)}>
                    <Badge variant={STATUS_VARIANT[bucket]}>
                      {formatDays(item.days_until_due)}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className={`text-sm font-medium ${
                            item.alert_status === 'unread' ? 'text-zinc-100' : 'text-zinc-300'
                          } truncate`}>
                            {item.title}
                          </p>
                          <div className="flex items-center gap-2 mt-1 text-xs text-zinc-500">
                            <span>{formatDate(item.deadline)}</span>
                            {item.location_name && (
                              <>
                                <span>·</span>
                                <span className="flex items-center gap-1">
                                  <MapPin size={10} />
                                  {item.location_name}
                                  {item.location_state ? `, ${item.location_state}` : ''}
                                </span>
                              </>
                            )}
                            {item.category && (
                              <>
                                <span>·</span>
                                <span>{item.category.replace(/_/g, ' ')}</span>
                              </>
                            )}
                          </div>
                          {item.action_required && (
                            <p className="text-xs text-zinc-400 mt-2 line-clamp-2">
                              {item.action_required}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {item.alert_status === 'baseline' ? (
                            <span
                              className="text-[10px] uppercase tracking-wide text-emerald-500/70 px-2 py-1"
                              title="Universal annual deadline — included by default. Run a compliance check to enrich with location-specific rules."
                            >
                              Baseline
                            </span>
                          ) : (
                            <>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onView(item)
                                }}
                                className="text-xs text-zinc-500 hover:text-zinc-200 px-2 py-1 rounded hover:bg-zinc-800"
                              >
                                View
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onDismiss(item)
                                }}
                                className="text-xs text-zinc-500 hover:text-red-400 px-2 py-1 rounded hover:bg-zinc-800"
                              >
                                Dismiss
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
