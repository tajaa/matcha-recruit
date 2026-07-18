import type { RefObject } from 'react'
import { Check, ExternalLink, Sparkles } from 'lucide-react'
import { Button } from '../../../../components/ui'
import { LABEL } from '../../../../components/ui/typography'
import { coverageLink } from '../utils'
import type { ReviewGroup, ApproveResult } from '../types'
import { CodifyOutcomePanel } from './CodifyOutcomePanel'

// ── §2 Staged review + §3 Codify chain ──
export function ReviewSection({
  reviewRef, justStaged, reviewResult, approveResults, loadingReview, reviewGroups,
  fetchReview, openCodify, approveReview, rejectReview,
}: {
  reviewRef: RefObject<HTMLDivElement | null>
  justStaged: boolean
  reviewResult: string | null
  approveResults: ApproveResult[]
  loadingReview: boolean
  reviewGroups: ReviewGroup[]
  fetchReview: () => void
  openCodify: (row: ApproveResult) => void
  approveReview: (ids: string[], group: ReviewGroup) => void
  rejectReview: (ids: string[], group: ReviewGroup) => void
}) {
  return (
    <div ref={reviewRef}>
      <div className="flex items-center justify-between mb-2">
        <h2 className={LABEL}>Staged research — approve to publish</h2>
        <Button variant="ghost" size="sm" onClick={fetchReview}>Refresh</Button>
      </div>

      {justStaged && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2.5">
          <Sparkles className="h-3.5 w-3.5 shrink-0 text-amber-400" />
          <p className="text-xs text-amber-200">
            Research complete — staged below, not yet live. Review, then
            <span className="font-medium"> Approve</span> to publish to the tenant and codify.
          </p>
        </div>
      )}

      {reviewResult && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-3 py-2.5">
          <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
          <p className="text-xs text-emerald-200">{reviewResult}</p>
        </div>
      )}

      {approveResults.length > 0 && (
        <CodifyOutcomePanel approveResults={approveResults} openCodify={openCodify} />
      )}

      {loadingReview ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : reviewGroups.length === 0 ? (
        <div className="border border-white/[0.06] rounded-lg px-4 py-8 text-center">
          <p className="text-sm text-zinc-600">Nothing staged for review.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {reviewGroups.map((group) => {
            const allIds = group.rows.map((r) => r.id)
            return (
              <div key={group.jurisdiction_id} className="border border-white/[0.06] rounded-lg overflow-hidden">
                <div className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-4 py-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-[15px] font-semibold text-zinc-100">{group.label}</h3>
                    <p className="mt-0.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                      <span>{group.state} · {group.rows.length} staged</span>
                      <a href={coverageLink(group.state, group.city)}
                        className="inline-flex items-center gap-0.5 text-cyan-400/70 hover:text-cyan-300 normal-case tracking-normal">
                        Coverage <ExternalLink className="h-2.5 w-2.5" />
                      </a>
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="secondary" size="sm" onClick={() => approveReview(allIds, group)}>
                      Approve all ({group.rows.length})
                    </Button>
                    <button type="button" onClick={() => rejectReview(allIds, group)}
                      className="text-xs text-zinc-600 hover:text-red-400 px-2 py-1 transition-colors">Reject all</button>
                  </div>
                </div>

                <div className="space-y-1.5 p-3">
                  {group.rows.map((row) => (
                    <div key={row.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-zinc-200">{row.title}</span>
                        <span className={`rounded border px-1.5 py-0.5 text-[10px] shrink-0 ${
                          row.will_codify
                            ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                            : 'border-zinc-600/40 bg-zinc-500/10 text-zinc-400'
                        }`} title={row.will_codify
                          ? 'A confirmed authority citation exists — approving will codify this automatically.'
                          : 'Research-cited, not yet registry-verified — approve, then Codify to confirm the statute citation.'}>
                          {row.will_codify ? 'Will codify' : 'Codify after approve'}
                        </span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-zinc-500">
                        {row.category_name}
                        {row.source_name && (
                          <> · {row.source_url
                            ? <a href={row.source_url} target="_blank" rel="noreferrer" className="text-cyan-400/70 hover:text-cyan-300">{row.source_name}</a>
                            : <span className="text-zinc-400">{row.source_name}</span>}</>
                        )}
                      </p>
                      {row.description && (
                        <p className="mt-1 text-[11px] text-zinc-400 leading-relaxed">{row.description}</p>
                      )}
                      {row.current_value && (
                        <p className="mt-1 text-[11px] text-zinc-300">{row.current_value}</p>
                      )}
                      <div className="mt-2 flex items-center gap-3">
                        <button type="button" onClick={() => approveReview([row.id], group)}
                          className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors">Approve</button>
                        <button type="button" onClick={() => rejectReview([row.id], group)}
                          className="text-xs text-zinc-600 hover:text-red-400 transition-colors">Reject</button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
