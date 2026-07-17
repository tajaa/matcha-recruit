import { useState, useEffect } from 'react'
import { api } from '../../api/client'

type Notice = {
  requirement_id: string
  authority: string
  category: string
  title: string
  statute_citation?: string | null
  source_url?: string | null
}
type Packet = {
  employee_id: string
  state: string | null
  notices: { federal: Notice[]; state: Notice[]; local: Notice[] }
  count: number
}

const GROUP_LABEL: Record<string, string> = { federal: 'Federal', state: 'State', local: 'Local' }

function NoticeChip({ n }: { n: Notice }) {
  const label = `${n.title}${n.statute_citation ? ` · ${n.statute_citation}` : ''}`
  const inner = (
    <span
      className="inline-flex items-center rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-[11px] text-emerald-200"
      title={`${n.category}${n.authority ? ` — ${n.authority}` : ''}`}
    >
      {label}
    </span>
  )
  return n.source_url
    ? <a href={n.source_url} target="_blank" rel="noopener noreferrer" className="hover:opacity-80">{inner}</a>
    : inner
}

/** New-hire compliance notices owed for an employee's work state (+ federal),
 *  derived from the codified compliance catalog. Renders nothing when empty. */
export function NewHirePacket({ employeeId }: { employeeId: string }) {
  const [packet, setPacket] = useState<Packet | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    api.get<Packet>(`/onboarding/jurisdiction-packet/${employeeId}`)
      .then((p) => { if (live) setPacket(p) })
      .catch(() => { if (live) setPacket(null) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [employeeId])

  if (loading || !packet || packet.count === 0) return null

  return (
    <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] uppercase tracking-wide text-emerald-400/80">New-hire compliance packet</h3>
        {packet.state && <span className="text-[10px] text-zinc-500">{packet.state}</span>}
      </div>
      {(['federal', 'state', 'local'] as const).map((g) =>
        packet.notices[g].length > 0 ? (
          <div key={g} className="space-y-1.5">
            <p className="text-[10px] uppercase tracking-wide text-zinc-500">{GROUP_LABEL[g]}</p>
            <div className="flex flex-wrap gap-1.5">
              {packet.notices[g].map((n) => <NoticeChip key={n.requirement_id} n={n} />)}
            </div>
          </div>
        ) : null,
      )}
      <p className="text-[10px] text-zinc-600">Obligations to complete at hire — verify against counsel; not legal advice.</p>
    </div>
  )
}
