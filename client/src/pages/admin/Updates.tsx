import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import type { AdminUpdate } from '../../types/adminUpdates'

const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

const monthLabel = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

// Stable color per category, picked from a small fixed palette (keyed by string hash).
const BADGE_COLORS = [
  'bg-emerald-500/10 text-emerald-300 ring-emerald-500/20',
  'bg-sky-500/10 text-sky-300 ring-sky-500/20',
  'bg-violet-500/10 text-violet-300 ring-violet-500/20',
  'bg-rose-500/10 text-rose-300 ring-rose-500/20',
  'bg-amber-500/10 text-amber-300 ring-amber-500/20',
  'bg-cyan-500/10 text-cyan-300 ring-cyan-500/20',
  'bg-fuchsia-500/10 text-fuchsia-300 ring-fuchsia-500/20',
  'bg-lime-500/10 text-lime-300 ring-lime-500/20',
]

function badgeColor(category: string) {
  let h = 0
  for (let i = 0; i < category.length; i++) h = (h * 31 + category.charCodeAt(i)) >>> 0
  return BADGE_COLORS[h % BADGE_COLORS.length]
}

function CategoryBadge({ category }: { category: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${badgeColor(category)}`}>
      {category}
    </span>
  )
}

function UpdateRow({ u, open, onToggle }: { u: AdminUpdate; open: boolean; onToggle: () => void }) {
  return (
    <article className="border-b border-zinc-800 last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 py-3 text-left hover:bg-zinc-900/40"
      >
        <ChevronDown
          className={`mt-1 h-4 w-4 shrink-0 text-zinc-500 transition-transform ${open ? 'rotate-0' : '-rotate-90'}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            <span className="tabular-nums">{fmtDate(u.date)}</span>
            <CategoryBadge category={u.category} />
            {u.tag === 'action-needed' && (
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300 ring-1 ring-inset ring-amber-500/20">
                Setup needed
              </span>
            )}
          </div>
          <h2 className="mt-1 truncate text-[15px] font-semibold text-zinc-50">{u.title}</h2>
          {!open && <p className="mt-0.5 truncate text-sm text-zinc-500">{u.summary}</p>}
        </div>
      </button>

      {open && (
        <div className="pb-5 pl-7">
          <p className="text-sm leading-relaxed text-zinc-400">{u.summary}</p>

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
        </div>
      )}
    </article>
  )
}

/** Master-admin changelog — what shipped + how to use it, so nothing built
 *  ever gets lost. Content is authored in the admin_updates DB table. */
export default function Updates() {
  const [updates, setUpdates] = useState<AdminUpdate[] | null>(null)
  const [error, setError] = useState(false)
  const [openIds, setOpenIds] = useState<Set<string>>(new Set())
  const [category, setCategory] = useState<string | null>(null)

  useEffect(() => {
    api.get<AdminUpdate[]>('/admin/updates')
      .then((data) => {
        setUpdates(data)
        if (data.length > 0) setOpenIds(new Set([data[0].id])) // newest starts expanded
      })
      .catch(() => setError(true))
  }, [])

  const categories = useMemo(
    () => (updates ? Array.from(new Set(updates.map((u) => u.category))).sort() : []),
    [updates]
  )

  const filtered = useMemo(
    () => (updates ? (category ? updates.filter((u) => u.category === category) : updates) : []),
    [updates, category]
  )

  const groups = useMemo(() => {
    const out: { label: string; items: AdminUpdate[] }[] = []
    for (const u of filtered) {
      const label = monthLabel(u.date)
      const last = out[out.length - 1]
      if (last && last.label === label) last.items.push(u)
      else out.push({ label, items: [u] })
    }
    return out
  }, [filtered])

  const toggle = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allOpen = updates ? updates.every((u) => openIds.has(u.id)) : false
  const setAll = (open: boolean) => setOpenIds(new Set(open && updates ? updates.map((u) => u.id) : []))

  return (
    <div className="max-w-6xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Updates</h1>
          <p className="mt-0.5 text-sm text-zinc-500">New features and how to use them — newest first.</p>
        </div>
        {updates && updates.length > 0 && (
          <button
            type="button"
            onClick={() => setAll(!allOpen)}
            className="text-xs font-medium text-zinc-400 hover:text-zinc-200"
          >
            {allOpen ? 'Collapse all' : 'Expand all'}
          </button>
        )}
      </div>

      {categories.length > 1 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setCategory(null)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
              category === null ? 'bg-zinc-100 text-zinc-900 ring-zinc-100' : 'text-zinc-400 ring-zinc-700 hover:text-zinc-200'
            }`}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
                category === c ? 'bg-zinc-100 text-zinc-900 ring-zinc-100' : 'text-zinc-400 ring-zinc-700 hover:text-zinc-200'
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      <div className="mt-5">
        {error && <p className="text-sm text-red-400">Couldn't load updates.</p>}
        {!error && !updates && <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />}
        {groups.map((g) => (
          <div key={g.label} className="mb-6">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-600">{g.label}</div>
            <div>
              {g.items.map((u) => (
                <UpdateRow key={u.id} u={u} open={openIds.has(u.id)} onToggle={() => toggle(u.id)} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
