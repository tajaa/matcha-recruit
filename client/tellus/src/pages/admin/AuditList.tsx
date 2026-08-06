import type { AdminAuditEntry } from '../../api/types'

const fmtDateTime = (iso: string) => new Date(iso).toLocaleString()

export function AuditList({
  entries, emptyText = 'No admin actions yet.', showTarget = false,
}: { entries: AdminAuditEntry[]; emptyText?: string; showTarget?: boolean }) {
  if (entries.length === 0) return <p className="text-sm text-tu-faint">{emptyText}</p>
  return (
    <>
      {entries.map((a) => (
        <details key={a.id} className="border-b border-tu-border/50 py-1.5 text-sm last:border-b-0">
          <summary className="cursor-pointer">
            <span className="text-tu-text">{a.action}</span>{' '}
            {showTarget && (
              <span className="text-tu-faint">
                · {a.target_type}{a.target_id ? `:${a.target_id.slice(0, 8)}` : ''}
              </span>
            )}{' '}
            <span className="text-tu-faint">by {a.actor_email} · {fmtDateTime(a.created_at)}</span>
          </summary>
          {a.detail && <pre className="mt-1 overflow-x-auto text-xs text-tu-dim">{JSON.stringify(a.detail, null, 2)}</pre>}
        </details>
      ))}
    </>
  )
}
