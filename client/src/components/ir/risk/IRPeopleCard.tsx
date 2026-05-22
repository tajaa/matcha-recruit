import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Users } from 'lucide-react'
import { api } from '../../../api/client'
import type { IRPersonSummary } from '../../../types/ir'

// People ranked by incident count — the no-roster answer to "who shows up
// across our incidents?" Each links to the per-person, role-aware history.
export function IRPeopleCard() {
  const [people, setPeople] = useState<IRPersonSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<IRPersonSummary[]>('/ir/incidents/people/search?limit=20')
      .then((rows) => setPeople(rows || []))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load people'))
  }, [])

  return (
    <section>
      <h2 className="flex items-center gap-2 text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">
        <Users className="w-3.5 h-3.5" />
        People by incident count
      </h2>
      {people === null && !error ? (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 flex items-center justify-center text-zinc-500">
          <Loader2 className="w-4 h-4 animate-spin" />
        </div>
      ) : error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : !people || people.length === 0 ? (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 text-sm text-zinc-500 text-center">
          No people tracked yet. Names entered on incident reports appear here automatically.
        </div>
      ) : (
        <div className="border border-zinc-800 rounded-xl divide-y divide-zinc-800/60">
          {people.map((p) => (
            <Link
              key={p.id}
              to={`/app/ir/people/${p.id}`}
              className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-zinc-900/60 transition-colors"
            >
              <span className="text-sm text-zinc-200 truncate">{p.display_name}</span>
              <span className="text-xs text-zinc-500 shrink-0">
                {p.incident_count} {p.incident_count === 1 ? 'incident' : 'incidents'}
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
