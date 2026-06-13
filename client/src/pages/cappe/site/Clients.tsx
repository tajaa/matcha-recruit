import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Loader2, Users, MessageSquare, Receipt, Calendar, Mail } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell, { centsToMoney } from '../../../components/cappe/SurfaceShell'
import type { CappeClient } from '../../../types/cappe'

export default function Clients() {
  const { siteId } = useParams<{ siteId: string }>()
  const navigate = useNavigate()
  const [clients, setClients] = useState<CappeClient[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    cappeApi.get<CappeClient[]>(`/sites/${siteId}/clients`)
      .then(setClients)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load clients'))
  }, [siteId])

  function message(c: CappeClient) {
    const qs = new URLSearchParams({ to: c.email, ...(c.name ? { name: c.name } : {}) })
    navigate(`/cappe/sites/${siteId}/messages?${qs.toString()}`)
  }

  const filtered = (clients || []).filter((c) =>
    !q || c.email.toLowerCase().includes(q.toLowerCase()) || (c.name || '').toLowerCase().includes(q.toLowerCase()),
  )

  return (
    <SurfaceShell title="Clients" subtitle="Everyone who's ordered, booked, subscribed, or messaged you.">
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {clients === null ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : clients.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <Users className="mx-auto mb-2 h-7 w-7 text-zinc-300" /> No clients yet.
        </div>
      ) : (
        <>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search clients…"
            className="mb-4 w-full max-w-xs rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-lime-500"
          />
          <div className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
            {filtered.map((c) => (
              <div key={c.email} className="flex items-center gap-4 px-5 py-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-sm font-semibold uppercase text-zinc-300">
                  {(c.name || c.email).slice(0, 1)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-zinc-100">{c.name || c.email}</div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-zinc-500">
                    {c.name && <span className="truncate">{c.email}</span>}
                    {c.orders_count > 0 && <span className="inline-flex items-center gap-1"><Receipt className="h-3 w-3" />{c.orders_count}</span>}
                    {c.bookings_count > 0 && <span className="inline-flex items-center gap-1"><Calendar className="h-3 w-3" />{c.bookings_count}</span>}
                    {c.is_subscriber && <span className="inline-flex items-center gap-1 text-lime-400"><Mail className="h-3 w-3" />subscribed</span>}
                    {c.total_spent_cents > 0 && <span className="text-zinc-300">{centsToMoney(c.total_spent_cents)} spent</span>}
                  </div>
                </div>
                <button onClick={() => message(c)} className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:bg-zinc-800">
                  <MessageSquare className="h-3.5 w-3.5" /> Message
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </SurfaceShell>
  )
}
