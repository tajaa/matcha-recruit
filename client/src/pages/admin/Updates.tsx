import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Loader2, Sparkles } from 'lucide-react'
import { api } from '../../api/client'
import { LABEL } from '../../components/ui'
import type { AdminUpdate } from '../../types/adminUpdates'

const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

const monthLabel = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

function UpdateRow({ u, open, onToggle }: { u: AdminUpdate; open: boolean; onToggle: () => void }) {
  return (
    <article className="border-b border-white/[0.06] last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.02]"
      >
        <ChevronDown
          className={`mt-1 h-4 w-4 shrink-0 text-zinc-600 transition-transform ${open ? 'rotate-0' : '-rotate-90'}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
            <span className="tabular-nums">{fmtDate(u.date)}</span>
            <span>{u.category}</span>
            {u.tag === 'action-needed' && <span className="text-amber-400">Setup needed</span>}
          </div>
          <h2 className="mt-1 truncate text-[15px] font-semibold text-zinc-100">{u.title}</h2>
          {!open && <p className="mt-0.5 truncate text-sm text-zinc-500">{u.summary}</p>}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-6 pl-11">
          <p className="text-sm leading-relaxed text-zinc-400">{u.summary}</p>

          <div className="mt-3">
            <div className={`mb-1 ${LABEL}`}>What's new</div>
            <ul className="space-y-1 text-sm leading-normal text-zinc-300 lg:columns-2 lg:gap-8 [&>li]:break-inside-avoid">
              {u.whatsNew.map((w, i) => (
                <li key={i}>· {w}</li>
              ))}
            </ul>
          </div>

          <div className="mt-4 grid gap-6 border-t border-white/[0.06] pt-4 lg:grid-cols-2">
            <div>
              <div className={`mb-1 ${LABEL}`}>How to use it</div>
              <ol className="space-y-1 text-sm leading-normal text-zinc-300">
                {u.howToUse.map((h, i) => (
                  <li key={i}>{i + 1}. {h}</li>
                ))}
              </ol>
            </div>
            <div>
              {u.notes && u.notes.length > 0 && (
                <>
                  <div className={`mb-1 ${LABEL}`}>Context</div>
                  <ul className="space-y-1 text-sm leading-normal text-zinc-400">
                    {u.notes.map((n, i) => (
                      <li key={i}>· {n}</li>
                    ))}
                  </ul>
                </>
              )}
              {u.setup && u.setup.length > 0 && (
                <>
                  <div className={`mb-1 text-[10px] font-medium uppercase tracking-[0.15em] text-amber-400 ${u.notes?.length ? 'mt-3' : ''}`}>
                    Setup before it works
                  </div>
                  <ul className="space-y-1 text-sm leading-normal text-amber-100/80">
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
 *  ever gets lost. Content is authored in the admin_updates DB table. Styled as
 *  its own bordered module (matching Legal Pilot's shell), not a plain page. */
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

  const setupNeededCount = useMemo(
    () => (updates ? updates.filter((u) => u.tag === 'action-needed').length : 0),
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
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-black">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Sparkles className="h-4 w-4 text-emerald-400" /> Updates
        </h1>
        <div className="flex items-center gap-4">
          <span className="hidden text-xs text-zinc-500 md:block">New features and how to use them — newest first.</span>
          {updates && updates.length > 0 && (
            <button
              type="button"
              onClick={() => setAll(!allOpen)}
              className="rounded-md border border-white/[0.08] px-2.5 py-1 text-xs font-medium text-zinc-400 transition-colors hover:bg-white/[0.04] hover:text-zinc-100"
            >
              {allOpen ? 'Collapse all' : 'Expand all'}
            </button>
          )}
        </div>
      </div>

      {/* Stat bar */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-white/[0.06] px-4 py-2 font-mono text-[11px] uppercase tracking-wide text-zinc-500">
        <span>Updates <b className="text-zinc-100">{updates?.length ?? '—'}</b></span>
        <span>Categories <b className="text-zinc-100">{categories.length || '—'}</b></span>
        <span className={setupNeededCount > 0 ? 'text-amber-400' : ''}>
          Setup needed <b>{setupNeededCount || '—'}</b>
        </span>
      </div>

      {/* Category tabs */}
      {categories.length > 1 && (
        <div className="flex flex-wrap items-center gap-1 border-b border-white/[0.06] px-2 py-1.5">
          <button
            type="button"
            onClick={() => setCategory(null)}
            className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors ${
              category === null ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors ${
                category === c ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {/* Scrolling body */}
      <div className="flex-1 overflow-y-auto">
        {error && <p className="px-4 py-4 text-sm text-red-400">Couldn't load updates.</p>}
        {!error && !updates && <Loader2 className="m-4 h-5 w-5 animate-spin text-zinc-500" />}
        {groups.map((g) => (
          <div key={g.label}>
            <div className={`sticky top-0 z-10 border-b border-white/[0.06] bg-black px-4 py-1.5 ${LABEL}`}>{g.label}</div>
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
