import { Check, Circle, ExternalLink } from 'lucide-react'
import { Button } from '../../../../components/ui'
import { coverageLink, libraryLink } from '../utils'
import type { ApproveResult } from '../types'

// ── §3 Codify chain — outcome panel ──
// The post-approve (or seeded) worklist: which rows are live, which still need
// a statute match, with in-place codify hooks.
export function CodifyOutcomePanel({
  approveResults, openCodify,
}: {
  approveResults: ApproveResult[]
  openCodify: (row: ApproveResult) => void
}) {
  const remaining = approveResults.filter((r) => !r.codified)
  return (
    <div className="mb-4 rounded-lg border border-white/[0.08] bg-white/[0.02] overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2">
        <p className="font-mono text-[10px] uppercase tracking-wide text-zinc-500">
          {remaining.length === 0
            ? `All ${approveResults.length} codified`
            : `Codification outcome — ${approveResults.length - remaining.length}/${approveResults.length} codified`}
        </p>
        {remaining.length > 0 && (
          <Button variant="secondary" size="sm" onClick={() => openCodify(remaining[0])}>
            Codify {remaining.length} →
          </Button>
        )}
      </div>
      <div className="divide-y divide-white/[0.04]">
        {approveResults.map((r) => (
          <div key={r.id} className="flex items-start gap-2.5 px-3 py-2.5">
            {r.codified ? (
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
            ) : (
              <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400/70" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-medium text-zinc-200">{r.title}</p>
                {!r.codified && !!r.blocked_companies && (
                  // Which of these rows a customer is actually waiting on.
                  // Hidden once codified — the wait is over — and absent on
                  // fresh approves, where demand is unknown rather than zero.
                  <span
                    className="shrink-0 rounded-full border border-amber-800/40 bg-amber-900/20 px-1.5 py-0.5 font-mono text-[10px] text-amber-400"
                    title="Live tenants with this requirement projected but withheld from their tab">
                    blocks {r.blocked_companies}
                  </span>
                )}
              </div>
              {r.codified ? (
                <p className="mt-0.5 text-[11px] text-zinc-400">
                  Codified — {r.citation_url
                    ? <a href={r.citation_url} target="_blank" rel="noreferrer"
                        className="text-cyan-400 hover:text-cyan-300">{r.statute_citation || 'view statute'}</a>
                    : <span className="text-zinc-300">{r.statute_citation}</span>}
                  {(r.state || r.city) && <>
                    {' · '}
                    <a href={libraryLink(r.state, r.city)}
                      className="text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-0.5">
                      View in Library <ExternalLink className="h-3 w-3" />
                    </a>
                  </>}
                </p>
              ) : (
                <p className="mt-0.5 text-[11px] text-zinc-500">
                  Live, not yet codified.{' '}
                  <button type="button" onClick={() => openCodify(r)}
                    className="text-emerald-400 hover:text-emerald-300 font-medium">Codify now</button>
                  {' '}or open in{' '}
                  <a href={coverageLink(r.state, r.city)}
                    className="text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-0.5">
                    Coverage <ExternalLink className="h-3 w-3" />
                  </a>.
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
