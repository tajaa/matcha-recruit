import { useState } from 'react'
import BreakReminderDeliveryLog from './BreakReminderDeliveryLog'
import ScheduleAuditLog from './ScheduleAuditLog'

type AuditView = 'shifts' | 'break-reminders'

const VIEWS: Array<{ value: AuditView; label: string }> = [
  { value: 'shifts', label: 'Published shift changes' },
  { value: 'break-reminders', label: 'Break reminders' },
]

/** The schedule page's Audit log tab: two independent histories, one tab. */
export default function ScheduleAuditTab() {
  const [view, setView] = useState<AuditView>('shifts')
  return (
    <div className="space-y-5">
      <div role="tablist" aria-label="Audit history" className="inline-flex rounded-lg border border-zinc-800 bg-zinc-900/40 p-0.5">
        {VIEWS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={view === option.value}
            onClick={() => setView(option.value)}
            className={`rounded-md px-3 py-1.5 text-sm ${view === option.value ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-200'}`}
          >
            {option.label}
          </button>
        ))}
      </div>
      {view === 'shifts' ? <ScheduleAuditLog /> : <BreakReminderDeliveryLog />}
    </div>
  )
}
