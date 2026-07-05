import { useEffect, useState } from 'react'
import { Rocket, Sparkles, ListChecks, Wrench, AlertCircle, BookOpen, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import type { AdminUpdate } from '../../types/adminUpdates'

const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })

function UpdateCard({ u }: { u: AdminUpdate }) {
  return (
    <article className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
          {u.category}
        </span>
        {u.tag === 'action-needed' && (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-300">
            <AlertCircle className="h-3 w-3" /> Setup needed
          </span>
        )}
        <span className="ml-auto text-xs text-zinc-500">{fmtDate(u.date)}</span>
      </div>

      <h2 className="text-lg font-semibold text-zinc-50">{u.title}</h2>
      <p className="mt-1 text-sm leading-relaxed text-zinc-400">{u.summary}</p>

      {u.notes && u.notes.length > 0 && (
        <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-950/40 p-4">
          <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            <BookOpen className="h-3.5 w-3.5" /> Context
          </div>
          <ul className="space-y-2 text-sm leading-relaxed text-zinc-400">
            {u.notes.map((n, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-zinc-600" />
                {n}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 grid gap-5 sm:grid-cols-2">
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            <Sparkles className="h-3.5 w-3.5" /> What's new
          </div>
          <ul className="space-y-1.5 text-sm text-zinc-300">
            {u.whatsNew.map((w, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-emerald-400" />
                {w}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            <ListChecks className="h-3.5 w-3.5" /> How to use it
          </div>
          <ol className="space-y-1.5 text-sm text-zinc-300">
            {u.howToUse.map((h, i) => (
              <li key={i} className="flex gap-2">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-[10px] font-semibold text-zinc-400">
                  {i + 1}
                </span>
                {h}
              </li>
            ))}
          </ol>
        </div>
      </div>

      {u.setup && u.setup.length > 0 && (
        <details className="mt-4 rounded-xl border border-amber-700/30 bg-amber-500/[0.05] p-3">
          <summary className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-amber-200">
            <Wrench className="h-3.5 w-3.5" /> Setup before it works ({u.setup.length})
          </summary>
          <ul className="mt-2 space-y-1 text-xs text-amber-100/80">
            {u.setup.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                {s}
              </li>
            ))}
          </ul>
        </details>
      )}
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
    <div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15">
          <Rocket className="h-5 w-5 text-emerald-300" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Updates</h1>
          <p className="mt-0.5 text-sm text-zinc-500">New features and how to use them — newest first.</p>
        </div>
      </div>

      <div className="max-w-3xl space-y-4">
        {error && <p className="text-sm text-red-400">Couldn't load updates.</p>}
        {!error && !updates && <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />}
        {updates?.map((u) => (
          <UpdateCard key={u.id} u={u} />
        ))}
      </div>
    </div>
  )
}
