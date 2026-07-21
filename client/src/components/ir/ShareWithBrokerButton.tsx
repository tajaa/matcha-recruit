import { useState, useEffect, useCallback } from 'react'
import { Share2, Check, Loader2 } from 'lucide-react'
import { api } from '../../api/client'

type BrokerShare = { id: string; name: string; shared: boolean; shared_at: string | null }

/** Share this incident's defense file with a linked broker.
 *
 * Brokers see nothing by default — this control is the whole grant. Renders
 * nothing when the company has no linked broker, so the tenants that will never
 * use it never see it.
 *
 * Per broker, not per company: a client with two brokers can share with one and
 * not the other, so with several linked brokers this becomes a list of toggles
 * rather than a single button. */
export function ShareWithBrokerButton({ incidentId }: { incidentId: string }) {
  const [brokers, setBrokers] = useState<BrokerShare[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.get<{ brokers: BrokerShare[] }>(`/ir/incidents/${incidentId}/broker-shares`)
      .then((r) => setBrokers(r.brokers))
      .catch(() => setBrokers([]))
      .finally(() => setLoading(false))
  }, [incidentId])

  useEffect(load, [load])

  async function toggle(b: BrokerShare) {
    setBusyId(b.id)
    setError(null)
    // Optimistic: the round-trip is a single row write and the button is the
    // only thing that changes — a spinner-then-flip reads as lag.
    setBrokers((prev) => prev.map((x) => (x.id === b.id ? { ...x, shared: !x.shared } : x)))
    try {
      if (b.shared) await api.delete(`/ir/incidents/${incidentId}/broker-shares/${b.id}`)
      else await api.put(`/ir/incidents/${incidentId}/broker-shares/${b.id}`, {})
    } catch {
      setBrokers((prev) => prev.map((x) => (x.id === b.id ? { ...x, shared: b.shared } : x)))
      setError(b.shared ? "Couldn't revoke access." : "Couldn't share.")
    } finally {
      setBusyId(null)
    }
  }

  if (loading || brokers.length === 0) return null

  return (
    <div className="space-y-1.5">
      {brokers.map((b) => (
        <button
          key={b.id}
          type="button"
          disabled={busyId === b.id}
          onClick={() => toggle(b)}
          title={b.shared
            ? `${b.name} can download this incident's defense file. Click to revoke.`
            : `Give ${b.name} access to this incident's defense file.`}
          className={`w-full inline-flex items-center justify-center gap-1.5 text-xs px-2 py-1.5 rounded-lg border transition-colors disabled:opacity-60 ${
            b.shared
              ? 'border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-400 hover:border-emerald-500/50'
              : 'border-white/[0.08] text-zinc-400 hover:text-zinc-200 hover:border-white/20'
          }`}
        >
          {busyId === b.id
            ? <Loader2 size={12} className="animate-spin" />
            : b.shared ? <Check size={12} /> : <Share2 size={12} />}
          {b.shared
            ? (brokers.length === 1 ? 'Shared with your broker' : `Shared with ${b.name}`)
            : (brokers.length === 1 ? 'Share with your broker' : `Share with ${b.name}`)}
        </button>
      ))}
      {error && <p className="text-[11px] text-red-400">{error}</p>}
    </div>
  )
}
