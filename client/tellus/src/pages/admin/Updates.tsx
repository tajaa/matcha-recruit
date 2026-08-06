import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Loader2, Sparkles } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import type { TellusAdminUpdate } from '../../api/types'

const LABEL = 'font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-tu-faint'

const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

const monthLabel = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { month: 'long', year: 'numeric' })

function UpdateRow({ u, open, onToggle }: { u: TellusAdminUpdate; open: boolean; onToggle: () => void }) {
  return (
    <article className="border-b border-tu-border/70 last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-tu-panel2/60"
      >
        <ChevronDown
          className={`mt-1 h-4 w-4 shrink-0 text-tu-faint transition-transform ${open ? 'rotate-0' : '-rotate-90'}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-wide text-tu-faint">
            <span className="tabular-nums">{fmtDate(u.date)}</span>
            <span>{u.category}</span>
            {u.tag === 'action-needed' && <span className="text-tu-accent">Setup needed</span>}
          </div>
          <h2 className="mt-1 truncate text-[15px] font-semibold text-tu-text">{u.title}</h2>
          {!open && <p className="mt-0.5 truncate text-sm text-tu-dim">{u.summary}</p>}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-6 pl-11">
          <p className="text-sm leading-relaxed text-tu-dim">{u.summary}</p>

          <div className="mt-3">
            <div className={`mb-1 ${LABEL}`}>What's new</div>
            <ul className="space-y-1 text-sm leading-normal text-tu-text lg:columns-2 lg:gap-8 [&>li]:break-inside-avoid">
              {(u.whatsNew ?? []).map((w, i) => (
                <li key={i}>· {w}</li>
              ))}
            </ul>
          </div>

          {/* Ternary, not `&&`: these are numbers, and `0 || 0 || 0` renders a literal "0". */}
          {(u.howToUse?.length || u.notes?.length || u.setup?.length) ? (
            <div className="mt-4 grid gap-6 border-t border-tu-border/70 pt-4 lg:grid-cols-2">
              <div>
                {u.howToUse && u.howToUse.length > 0 && (
                  <>
                    <div className={`mb-1 ${LABEL}`}>How to use it</div>
                    <ol className="space-y-1 text-sm leading-normal text-tu-text">
                      {u.howToUse.map((h, i) => (
                        <li key={i}>{i + 1}. {h}</li>
                      ))}
                    </ol>
                  </>
                )}
              </div>
              <div>
                {u.notes && u.notes.length > 0 && (
                  <>
                    <div className={`mb-1 ${LABEL}`}>Context</div>
                    <ul className="space-y-1 text-sm leading-normal text-tu-dim">
                      {u.notes.map((n, i) => (
                        <li key={i}>· {n}</li>
                      ))}
                    </ul>
                  </>
                )}
                {u.setup && u.setup.length > 0 && (
                  <>
                    <div className={`mb-1 text-[10px] font-medium uppercase tracking-[0.15em] text-tu-accent ${u.notes?.length ? 'mt-3' : ''}`}>
                      Setup before it works
                    </div>
                    <ul className="space-y-1 text-sm leading-normal text-tu-accent-soft/80">
                      {u.setup.map((s, i) => (
                        <li key={i}>· {s}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </article>
  )
}

/** Internal Tell-Us changelog — what shipped + how to use it. Content is
 *  auto-generated from merged PRs into the tellus_admin_updates DB table
 *  (see AUTO_CHANGELOG_PLAN.md), same shape as matcha's /admin/updates. */
export default function TellusAdminUpdates() {
  const [updates, setUpdates] = useState<TellusAdminUpdate[] | null>(null)
  const [error, setError] = useState(false)
  const [openIds, setOpenIds] = useState<Set<string>>(new Set())
  const [category, setCategory] = useState<string | null>(null)

  useEffect(() => {
    tellusApi.get<TellusAdminUpdate[]>('/admin/updates')
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
    const out: { label: string; items: TellusAdminUpdate[] }[] = []
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
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-tu-border bg-tu-bg">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-tu-border px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-tu-text">
          <Sparkles className="h-4 w-4 text-tu-accent" /> Updates
        </h1>
        <div className="flex items-center gap-4">
          <span className="hidden text-xs text-tu-faint md:block">New features and how to use them — newest first.</span>
          {updates && updates.length > 0 && (
            <button
              type="button"
              onClick={() => setAll(!allOpen)}
              className="rounded-md border border-tu-border px-2.5 py-1 text-xs font-medium text-tu-dim transition-colors hover:bg-tu-panel2 hover:text-tu-text"
            >
              {allOpen ? 'Collapse all' : 'Expand all'}
            </button>
          )}
        </div>
      </div>

      {/* Stat bar */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-tu-border px-4 py-2 font-mono text-[11px] uppercase tracking-wide text-tu-faint">
        <span>Updates <b className="text-tu-text">{updates?.length ?? '—'}</b></span>
        <span>Categories <b className="text-tu-text">{categories.length || '—'}</b></span>
        <span className={setupNeededCount > 0 ? 'text-tu-accent' : ''}>
          Setup needed <b>{setupNeededCount || '—'}</b>
        </span>
      </div>

      {/* Category tabs */}
      {categories.length > 1 && (
        <div className="flex flex-wrap items-center gap-1 border-b border-tu-border px-2 py-1.5">
          <button
            type="button"
            onClick={() => setCategory(null)}
            className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors ${
              category === null ? 'bg-tu-panel2 text-tu-text' : 'text-tu-faint hover:text-tu-dim'
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
                category === c ? 'bg-tu-panel2 text-tu-text' : 'text-tu-faint hover:text-tu-dim'
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {/* Scrolling body */}
      <div className="flex-1 overflow-y-auto">
        {error && <p className="px-4 py-4 text-sm text-tu-bad">Couldn't load updates.</p>}
        {!error && !updates && <Loader2 className="m-4 h-5 w-5 animate-spin text-tu-faint" />}
        {groups.map((g) => (
          <div key={g.label}>
            <div className={`sticky top-0 z-10 border-b border-tu-border bg-tu-bg px-4 py-1.5 ${LABEL}`}>{g.label}</div>
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
