import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import type { AdminUpdate } from '../../types/adminUpdates'

const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })

function UpdateRow({ u }: { u: AdminUpdate }) {
  return (
    <article className="border-b border-zinc-800 py-4">
      <div className="flex flex-wrap items-baseline gap-2 text-xs text-zinc-500">
        <span>{fmtDate(u.date)}</span>
        <span>·</span>
        <span>{u.category}</span>
        {u.tag === 'action-needed' && <span className="text-amber-400">Setup needed</span>}
      </div>

      <h2 className="mt-1 text-base font-semibold text-zinc-50">{u.title}</h2>
      <p className="mt-1 text-sm leading-relaxed text-zinc-400">{u.summary}</p>

      <div className="mt-3 grid gap-6 lg:grid-cols-3">
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">What's new</div>
          <ul className="space-y-1 text-sm text-zinc-300">
            {u.whatsNew.map((w, i) => (
              <li key={i}>· {w}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">How to use it</div>
          <ol className="space-y-1 text-sm text-zinc-300">
            {u.howToUse.map((h, i) => (
              <li key={i}>{i + 1}. {h}</li>
            ))}
          </ol>
        </div>
        <div>
          {u.notes && u.notes.length > 0 && (
            <>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Context</div>
              <ul className="space-y-1 text-sm text-zinc-400">
                {u.notes.map((n, i) => (
                  <li key={i}>· {n}</li>
                ))}
              </ul>
            </>
          )}
          {u.setup && u.setup.length > 0 && (
            <>
              <div className={`mb-1 text-[11px] font-semibold uppercase tracking-wide text-amber-400 ${u.notes?.length ? 'mt-3' : ''}`}>
                Setup before it works
              </div>
              <ul className="space-y-1 text-sm text-amber-100/80">
                {u.setup.map((s, i) => (
                  <li key={i}>· {s}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </article>
  )
}

/** Master-admin changelog — what shipped + how to use it, so nothing built
 *  ever gets lost. Content is authored in the admin_updates DB table. */
export default function Updates() {
  const [updates, setUpdates] = useState<AdminUpdate[] | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api.get<AdminUpdate[]>('/admin/updates')
      .then(setUpdates)
      .catch(() => setError(true))
  }, [])

  return (
    <div className="max-w-6xl">
      <h1 className="text-xl font-semibold text-zinc-100">Updates</h1>
      <p className="mt-0.5 text-sm text-zinc-500">New features and how to use them — newest first.</p>

      <div className="mt-4">
        {error && <p className="text-sm text-red-400">Couldn't load updates.</p>}
        {!error && !updates && <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />}
        {updates?.map((u) => (
          <UpdateRow key={u.id} u={u} />
        ))}
      </div>
    </div>
  )
}
