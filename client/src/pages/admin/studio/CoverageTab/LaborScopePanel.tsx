import { BookOpen, Check, Microscope } from 'lucide-react'
import { Button, LABEL } from '../../../../components/ui'
import { HelpHint } from '../../../../components/ui/HelpHint'
import { CitationLink, ScopeChip, SeverityBadge } from './Badges'
import { ResearchProgress } from './ResearchProgress'
import { LEVEL_LABELS } from './constants'
import { penaltyChipText } from './helpers'
import type { GeneralCoverage, LaborScopeResponse, ResearchState } from './types'

export function LaborScopePanel({
  laborRef, laborScope, laborError, research, researchFetchQueue, generalCov, openReader,
}: {
  laborRef: React.RefObject<HTMLDivElement>
  laborScope: LaborScopeResponse | null
  laborError: string | null
  research: ResearchState | null
  researchFetchQueue: () => void
  generalCov: GeneralCoverage | null
  openReader: (itemId: string) => void
}) {
  return (
    <div ref={laborRef} className="rounded-xl border border-white/[0.06] bg-zinc-950 p-4">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={LABEL}>Labor scope — what we must fetch</div>
          <h2 className="mt-0.5 text-base font-semibold tracking-tight text-zinc-100">
            {laborScope?.coordinate.state
              ? `${laborScope.coordinate.state}${laborScope.coordinate.city ? `, ${laborScope.coordinate.city}` : ''}`
              : 'Federal'}
            <span className="ml-2 font-mono text-[10px] font-normal uppercase tracking-[0.15em] text-zinc-600">
              generic employer · federal + state + city
            </span>
          </h2>
        </div>
        {laborScope
          && (['federal', 'state', 'city'] as const).some((l) => laborScope.registry.levels[l].counts.uncodified > 0) && (
          <Button variant="secondary" size="sm" onClick={researchFetchQueue} disabled={research?.running}>
            <Microscope className="h-3.5 w-3.5" />
            Research these · codify
          </Button>
        )}
      </div>
      {research && research.source === 'queue' && <ResearchProgress r={research} />}
      {laborError ? (
        <div className="text-xs text-red-400">{laborError}</div>
      ) : !laborScope ? (
        <div className="text-xs text-zinc-500">Loading…</div>
      ) : laborScope.exhaustiveness.federal.basis === 'none'
          && laborScope.exhaustiveness.state.basis === 'none' ? (
        <div className="text-xs text-amber-400">
          Scope registry is empty — use the <span className="text-zinc-300">Authority tab</span>
          to ingest an authority index, classify it, and confirm the classifications. Until then every
          surface here falls back to the compliance catalog.
        </div>
      ) : (
        <>
          {/* Core spine */}
          <div className="mb-4">
            <div className="mb-1.5 flex items-center gap-2">
              <span className={LABEL}>Core labor checklist</span>
              <span className={`font-mono text-[10px] tabular-nums ${laborScope.core.complete ? 'text-emerald-400' : 'text-amber-400'}`}>
                {laborScope.core.present}/{laborScope.core.total} codified
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {laborScope.core.items.map((it) => (
                <span
                  key={`${it.category}:${it.key}`}
                  className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] ${
                    it.present
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                  }`}
                  title={it.present ? `codified at ${it.level} level` : 'not yet in jurisdiction-data — to fetch'}
                >
                  {it.present ? <Check className="h-3 w-3" /> : null}
                  {it.key}
                  {it.present && it.level ? <span className="text-emerald-500/70">·{it.level}</span> : null}
                </span>
              ))}
            </div>

            {/* Core-labor coverage STATE — the honesty layer. `unchecked` is a
                distinct state from `empty`, so a never-researched category no
                longer reads as a silent green. */}
            {generalCov && (
              <div className="mt-3">
                <div className="mb-1.5 flex items-center gap-2">
                  <span className={LABEL}>Coverage state</span>
                  <span className="font-mono text-[10px] tabular-nums text-zinc-500">
                    <span className="text-emerald-400">{generalCov.summary.covered} covered</span>
                    {' · '}<span className="text-zinc-400">{generalCov.summary.empty} nothing applies</span>
                    {generalCov.summary.unchecked > 0 && (
                      <>{' · '}<span className="text-amber-400">{generalCov.summary.unchecked} not yet checked</span></>
                    )}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {generalCov.categories.map((c) => {
                    const cls = c.status === 'covered'
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                      : c.status === 'empty'
                        ? 'border-zinc-600/40 bg-zinc-500/10 text-zinc-400'
                        : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                    const label = c.status === 'covered' ? 'covered'
                      : c.status === 'empty' ? 'checked — nothing applies' : 'not yet checked'
                    return (
                      <span key={c.slug} className={`rounded border px-2 py-0.5 text-[11px] ${cls}`} title={label}>
                        {c.name}
                      </span>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Federal / State / City */}
          <div className="grid gap-3 md:grid-cols-3">
            {LEVEL_LABELS.map(([lvl, label]) => {
              const data = laborScope.registry.levels[lvl]
              const ex = laborScope.exhaustiveness[lvl]
              if (lvl !== 'federal' && !laborScope.coordinate.state) {
                return (
                  <div key={lvl} className="rounded-lg border border-dashed border-white/[0.08] bg-white/[0.02] p-3">
                    <div className="mb-1.5 text-xs font-medium text-zinc-400">{label}</div>
                    <div className="text-[11px] text-zinc-600">Set a state above to see {label.toLowerCase()} labor scope.</div>
                  </div>
                )
              }
              const badge =
                ex.basis === 'enumerated'
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                  : ex.basis === 'curated'
                    ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                    : 'border-zinc-700 bg-zinc-800/50 text-zinc-500'
              const badgeText =
                ex.basis === 'enumerated' ? 'exhaustive (eCFR-enumerated)'
                  : ex.basis === 'curated' ? 'curated core — not exhaustive'
                    : 'no indexes ingested'
              return (
                <div key={lvl} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-xs font-medium text-zinc-200">{label}</span>
                    <span className="inline-flex items-center gap-1">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] ${badge}`}>
                        {badgeText}
                      </span>
                      {ex.note && <HelpHint text={ex.note} align="right" />}
                    </span>
                  </div>
                  {ex.enumeration && ex.enumeration.enumerated > 0 && (
                    <div className="mb-2 text-[11px] text-zinc-400">
                      {ex.enumeration.enumerated} sections enumerated across {ex.enumeration.indexes} authority {ex.enumeration.indexes === 1 ? 'index' : 'indexes'} ·{' '}
                      <span className="text-emerald-400/90">{ex.enumeration.classified} classified</span>
                      {ex.enumeration.unclassified > 0 && (
                        <>
                          {' · '}
                          <span className="text-amber-400/90">{ex.enumeration.unclassified} still to classify</span>
                        </>
                      )}
                    </div>
                  )}
                  {ex.indexes.length > 0 && (
                    <ul className="mb-2 space-y-1">
                      {ex.indexes.map((ix) => (
                        <li key={ix.slug} className="text-[11px] leading-snug">
                          <div className="text-zinc-300">{ix.name || ix.slug}</div>
                          <div className="text-[10px] text-zinc-500">
                            <span className={ix.source_type === 'ecfr' ? 'text-emerald-400/80' : 'text-zinc-400'}>
                              {ix.source_type === 'ecfr'
                                ? 'eCFR-enumerated (full part, official structure API)'
                                : 'curated from statute'}
                            </span>
                            {' · '}{ix.item_count} sections
                            {ix.unclassified_count > 0 && (
                              <span className="text-amber-500/80"> · {ix.unclassified_count} unclassified</span>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="flex gap-3 text-[11px]">
                    <span className="text-emerald-400">{data.counts.codified} codified</span>
                    <span className="text-amber-400">{data.counts.uncodified} to fetch</span>
                    {data.counts.provisional > 0 && (
                      <span className="text-zinc-500">{data.counts.provisional} awaiting confirm</span>
                    )}
                  </div>
                  {data.codified.length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-[10px] uppercase text-zinc-500">
                        Codified ({data.codified.length})
                      </summary>
                      <ul className="mt-1 space-y-1.5">
                        {data.codified.map((it) => {
                          const r = it.requirement
                          const when = r?.codified_at ?? r?.last_verified_at
                          const penaltyChip = penaltyChipText(r?.penalties)
                          const policyHref = r?.key_definition_id
                            ? `/admin/jurisdiction-data/policy/${r.key_definition_id}`
                            : null
                          return (
                            <li key={it.citation} className="text-[11px] text-zinc-400">
                              <div>
                                <CitationLink it={it} onOpen={openReader} />
                                {r?.title ? ` — ${r.title}` : it.regulation_key ? ` — ${it.regulation_key}` : ''}
                                <SeverityBadge severity={it.severity} />
                                <ScopeChip scope={it.jurisdiction_scope} />
                                {policyHref && (
                                  <a href={policyHref}
                                     className="ml-1.5 text-[10px] text-cyan-400/70 hover:underline"
                                     title="Open the codified value in the Compliance Library">
                                    library ↗
                                  </a>
                                )}
                              </div>
                              {r?.current_value && (
                                <div className="text-emerald-200/70">{r.current_value}</div>
                              )}
                              <div className="flex flex-wrap gap-x-2 text-[10px] text-zinc-500">
                                {r?.source_url ? (
                                  <a href={r.source_url} target="_blank" rel="noreferrer"
                                     className="text-cyan-400/70 hover:underline">
                                    {r.source_name || 'source'}
                                  </a>
                                ) : r?.source_name ? <span>{r.source_name}</span> : null}
                                {r?.jurisdiction_name && <span>{r.jurisdiction_name}</span>}
                                {when && (
                                  <span>{r?.codified_at ? 'codified' : 'verified'} {when.slice(0, 10)}</span>
                                )}
                                {r?.effective_date && (
                                  <span>effective {r.effective_date.slice(0, 10)}</span>
                                )}
                                {penaltyChip && (
                                  <span className="text-amber-400/80"
                                        title={r?.penalties?.summary || undefined}>
                                    penalty {penaltyChip}
                                  </span>
                                )}
                              </div>
                            </li>
                          )
                        })}
                      </ul>
                    </details>
                  )}
                  {data.uncodified.length > 0 && (
                    <div className="mt-2">
                      <div className="text-[10px] uppercase text-zinc-500">Fetch queue</div>
                      <ul className="mt-1 space-y-0.5">
                        {data.uncodified.slice(0, 10).map((it) => (
                          <li key={it.citation} className="text-[11px] text-amber-300/80">
                            {it.has_body && it.item_id ? (
                              <button onClick={() => openReader(it.item_id as string)}
                                      className="inline-flex items-center gap-1 font-mono hover:underline"
                                      title="Read the full regulation text">
                                {it.citation}<BookOpen className="h-3 w-3 opacity-60" />
                              </button>
                            ) : (
                              <span className="font-mono">{it.citation}</span>
                            )}
                            {it.heading ? <span className="text-zinc-500"> — {it.heading}</span> : ''}
                            <SeverityBadge severity={it.severity} />
                            <ScopeChip scope={it.jurisdiction_scope} />
                          </li>
                        ))}
                        {data.uncodified.length > 10 && (
                          <li className="text-[10px] text-zinc-600">+{data.uncodified.length - 10} more</li>
                        )}
                      </ul>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {(laborScope.registry.skipped.category_specific > 0 || laborScope.registry.skipped.conditional > 0) && (
            <div className="mt-2 text-[11px] text-zinc-500">
              {laborScope.registry.skipped.category_specific} category-gated + {laborScope.registry.skipped.conditional} conditional items excluded (generic-employer view)
            </div>
          )}
        </>
      )}
    </div>
  )
}
