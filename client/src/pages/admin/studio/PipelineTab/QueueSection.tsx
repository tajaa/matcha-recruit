import type { RefObject } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'
import { Button } from '../../../../components/ui'
import { LABEL } from '../../../../components/ui/typography'
import type { PendingItem } from '../types'

// ── §1 Queued coverage requests ──
export function QueueSection({
  queueRef, pending, loadingRequests, openIds, selected, runningId, runMessages,
  fetchRequests, toggleOpen, toggleSelectCategory, runResearch, dismissRequest,
}: {
  queueRef: RefObject<HTMLDivElement>
  pending: PendingItem[]
  loadingRequests: boolean
  openIds: Set<string>
  selected: Record<string, Set<string>>
  runningId: string | null
  runMessages: string[]
  fetchRequests: () => void
  toggleOpen: (id: string) => void
  toggleSelectCategory: (rowId: string, catId: string) => void
  runResearch: (rowId: string, item: PendingItem, categoryKeys: string[] | null) => void
  dismissRequest: (id: string) => void
}) {
  return (
    <div ref={queueRef}>
      <div className="flex items-center justify-between mb-2">
        <h2 className={LABEL}>Researching for tenants — newest first</h2>
        <Button variant="ghost" size="sm" onClick={fetchRequests}>Refresh</Button>
      </div>

      {runningId !== null && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-3 py-2.5">
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-emerald-400" />
          <p className="text-xs text-emerald-200">
            Researching… drafts appear below in Staged review when done.
            {runMessages.length > 0 && (
              <span className="ml-1.5 text-emerald-300/70">{runMessages[runMessages.length - 1]}</span>
            )}
          </p>
        </div>
      )}

      {loadingRequests ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : pending.length === 0 ? (
        <div className="border border-white/[0.06] rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">Nothing outstanding — every onboarded tenant is fully covered.</p>
        </div>
      ) : (
        <div className="border border-white/[0.06] rounded-lg overflow-hidden">
          {pending.map((item) => {
            const rowId = item.type === 'category' ? `cat-${item.id}` : `vert-${item.company_id}-${item.label}`
            const open = openIds.has(rowId)
            const categoryNames = item.categories.map((c) => c.name).join(', ')
            return (
              <article key={rowId} className="border-b border-white/[0.06] last:border-b-0">
                <button type="button" onClick={() => toggleOpen(rowId)}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.02]">
                  <ChevronDown className={`mt-1 h-4 w-4 shrink-0 text-zinc-600 transition-transform ${open ? 'rotate-0' : '-rotate-90'}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                      {item.created_at && <span className="tabular-nums">{new Date(item.created_at).toLocaleDateString()}</span>}
                      <span>{item.type === 'category' ? 'Category gap' : `Specialty · ${item.label}`}</span>
                    </div>
                    <h3 className="mt-1 truncate text-[15px] font-semibold text-zinc-100">
                      {item.type === 'category'
                        ? <>{item.city}, {item.state}{item.county && <span className="text-zinc-500 font-normal ml-1.5">({item.county} County)</span>}</>
                        : item.company_name}
                    </h3>
                    <p className="mt-0.5 truncate text-sm text-zinc-500">
                      {item.type === 'category' ? `${item.company_name} · ` : `${item.jurisdictions.join(', ')} · `}
                      {categoryNames}
                    </p>
                  </div>
                </button>
                {open && (
                  <div className="px-4 pb-4 pl-11">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-amber-400 text-[11px]">
                        {item.categories.length} to research
                      </span>
                      <span className="text-[10px] text-zinc-500">
                        · {item.type === 'category'
                          ? `${item.city}, ${item.state}`
                          : item.jurisdictions.join(', ')}
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      {item.categories.map((c, i) => {
                        const catId = c.key ?? c.name
                        const checked = selected[rowId]?.has(catId) ?? false
                        return (
                          <label key={c.key ?? `${c.name}-${i}`}
                            className="flex cursor-pointer gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                            <input type="checkbox" checked={checked} disabled={runningId !== null}
                              onChange={() => toggleSelectCategory(rowId, catId)}
                              className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-500" />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-medium text-zinc-200">{c.name}</span>
                                <span className="rounded border px-1.5 py-0.5 text-[10px] border-amber-500/30 bg-amber-500/10 text-amber-300 shrink-0">
                                  Needs research
                                </span>
                              </div>
                              {c.description && (
                                <p className="mt-1 text-[11px] text-zinc-400 leading-relaxed">{c.description}</p>
                              )}
                            </div>
                          </label>
                        )
                      })}
                    </div>

                    {runningId === rowId && runMessages.length > 0 && (
                      <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mt-3 max-h-28 overflow-y-auto">
                        {runMessages.map((msg, i) => (
                          <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
                        ))}
                      </div>
                    )}

                    {(() => {
                      const selCount = selected[rowId]?.size ?? 0
                      const selKeys = [...(selected[rowId] ?? [])]
                      if (runningId === rowId) {
                        return (
                          <p className="mt-3 text-xs text-zinc-500">Researching… (staged for review)</p>
                        )
                      }
                      return (
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <Button variant="secondary" size="sm"
                            disabled={selCount === 0 || runningId !== null}
                            onClick={() => runResearch(rowId, item, selKeys)}>
                            Research selected ({selCount})
                          </Button>
                          <Button variant="ghost" size="sm"
                            disabled={runningId !== null}
                            onClick={() => runResearch(rowId, item, null)}>
                            Research all
                          </Button>
                          {item.type === 'category' && (
                            <button type="button" onClick={() => dismissRequest(item.id)}
                              className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">Dismiss</button>
                          )}
                        </div>
                      )
                    })()}

                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
