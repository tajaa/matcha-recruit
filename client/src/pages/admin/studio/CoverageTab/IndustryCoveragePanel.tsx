import { Fragment } from 'react'
import { Loader2, Microscope } from 'lucide-react'
import { Button, LABEL } from '../../../../components/ui'
import type { GotoParams, StudioView, VerticalCoverageResponse } from '../types'
import { CitationLink } from './Badges'
import { ResearchProgress } from './ResearchProgress'
import { GRID_STATUS, INDUSTRIES, SOURCE_BADGE } from './constants'
import type { CategoryEntry, MatrixResponse, ResearchState, ResolveResult, Specialty } from './types'

export function IndustryCoveragePanel({
  coverageTab, setCoverageTab,
  available, specialties, toggleSpecialty,
  newSpecialty, setNewSpecialty, discoverSpecialty, discovering,
  specialtyError, researchTarget, researchTargetGap,
  research, state,
  gridIndustry, setGridIndustry, grid, gridLoading, goto,
  matrix, matrixLoading, onlyGaps, setOnlyGaps, grouped,
  resolveResult, resolveError,
  openReader,
}: {
  coverageTab: 'matrix' | 'resolve' | 'industry'
  setCoverageTab: (t: 'matrix' | 'resolve' | 'industry') => void
  available: Specialty[]
  specialties: string[]
  toggleSpecialty: (slug: string) => void
  newSpecialty: string
  setNewSpecialty: (v: string) => void
  discoverSpecialty: () => void
  discovering: boolean
  specialtyError: string | null
  researchTarget: { label: string; industry_tag: string; categories: string[] } | null
  researchTargetGap: () => void
  research: ResearchState | null
  state: string
  gridIndustry: string
  setGridIndustry: (v: string) => void
  grid: VerticalCoverageResponse | null
  gridLoading: boolean
  goto?: (next: StudioView, params?: GotoParams & { section?: string }) => void
  matrix: MatrixResponse | null
  matrixLoading: boolean
  onlyGaps: boolean
  setOnlyGaps: (fn: (v: boolean) => boolean) => void
  grouped: [string, CategoryEntry[]][]
  resolveResult: ResolveResult | null
  resolveError: string | null
  openReader: (itemId: string) => void
}) {
  return (
    <div className="mt-5 rounded-xl border border-white/[0.06] bg-zinc-950 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className={LABEL}>Industry &amp; specialty coverage</div>
          <div className="mt-0.5 text-[11px] text-zinc-500">The specialization layer that rides on top of the core labor scope above.</div>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-white/[0.06] bg-white/[0.02] p-0.5">
          {(['matrix', 'resolve', 'industry'] as const).map((t) => (
            <button key={t} onClick={() => setCoverageTab(t)}
              className={`rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors ${
                coverageTab === t ? 'bg-white/[0.06] text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'
              }`}>
              {t === 'matrix' ? 'Coverage matrix' : t === 'resolve' ? 'Registry resolution' : 'Across jurisdictions'}
            </button>
          ))}
        </div>
      </div>

      {/* Specialties + research the gap (per-coordinate — not the cross-jurisdiction grid) */}
      {coverageTab !== 'industry' && (
      <div className="mb-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
        <div className={`mb-2 ${LABEL}`}>Specialties</div>
        <div className="flex flex-wrap gap-2">
          {available.map((s) => (
            <button
              key={s.slug}
              onClick={() => toggleSpecialty(s.slug)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                specialties.includes(s.slug)
                  ? 'border-purple-500/50 bg-purple-500/15 text-purple-200'
                  : 'border-white/[0.08] text-zinc-400 hover:border-white/20'
              }`}
              title={s.category_count === 0 ? 'No categories behind this specialty yet' : ''}
            >
              {s.label}
              <span className={s.category_count === 0 ? 'ml-1 text-amber-400' : 'ml-1 text-zinc-500'}>
                {s.category_count}
              </span>
            </button>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={newSpecialty}
            onChange={(e) => setNewSpecialty(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && discoverSpecialty()}
            placeholder="Add a specialty (e.g. ophthalmology)…"
            className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-white/20"
          />
          <Button variant="secondary" size="sm" onClick={discoverSpecialty} disabled={discovering || !newSpecialty.trim()}>
            {discovering ? '…' : 'Derive ↵'}
          </Button>
        </div>
        {specialtyError && <div className="mt-2 text-xs text-red-400">{specialtyError}</div>}
        {researchTarget && researchTarget.categories.length > 0 && (
          <div className="mt-3">
            <Button variant="primary" size="sm" onClick={researchTargetGap} disabled={research?.running || !state.trim()}>
              <Microscope className="h-3.5 w-3.5" />
              Research {researchTarget.label} — {researchTarget.categories.length} categories
              {!state.trim() && <span className="text-amber-300"> · set a state</span>}
            </Button>
          </div>
        )}
        {research && research.source === 'gap' && <ResearchProgress r={research} />}
      </div>
      )}

      {coverageTab === 'industry' ? (
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className={LABEL}>Industry</span>
            <select value={gridIndustry} onChange={(e) => setGridIndustry(e.target.value)}
              className="rounded-lg border border-white/[0.08] bg-white/[0.02] px-2 py-1 text-sm text-zinc-100 outline-none focus:border-white/20">
              {(grid?.industries?.length ? grid.industries.map((i) => i.tag) : INDUSTRIES.map((i) => i.value))
                .map((tag) => <option key={tag} value={tag}>{tag}</option>)}
            </select>
            <span className="text-[11px] text-zinc-500">Pipeline status — distinct from the registry coverage above. Click a row → Library.</span>
          </div>

          {gridLoading ? (
            <div className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>
          ) : !grid || grid.jurisdictions.length === 0 ? (
            <div className="rounded-lg border border-white/[0.06] px-4 py-6 text-center text-sm text-zinc-600">
              No ledger cells for this industry yet. Run onboarding or scoping for a coordinate to populate it.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
              <table className="text-[11px]">
                <thead>
                  <tr className="text-zinc-500">
                    <th className="sticky left-0 z-10 bg-zinc-950 px-3 py-2 text-left font-medium">Jurisdiction</th>
                    {grid.categories.map((c) => (
                      <th key={c.slug} className="px-1 py-2 font-medium align-bottom" title={c.name}>
                        <div className="mx-auto w-5 truncate text-zinc-600">{c.name}</div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {grid.jurisdictions.map((row) => (
                    <tr key={row.jurisdiction_id}
                      onClick={() => goto?.('library', { state: row.state || undefined, city: row.city || undefined, industry: grid.industry_tag || undefined })}
                      className="cursor-pointer border-t border-white/[0.04] hover:bg-white/[0.03]">
                      <td className="sticky left-0 z-10 bg-zinc-950 px-3 py-1.5 text-left whitespace-nowrap">
                        <span className="text-zinc-200">{row.display_name || row.city || row.state}</span>
                        <span className="ml-1.5 text-[10px] text-zinc-600 uppercase">{row.level}</span>
                      </td>
                      {grid.categories.map((c) => {
                        const cell = row.cells[c.slug]
                        const status = cell?.status ?? 'absent'
                        return (
                          <td key={c.slug} className="px-1 py-1.5 text-center">
                            <span className={`inline-block h-2.5 w-2.5 rounded-full ${GRID_STATUS[status] ?? GRID_STATUS.absent}`}
                              title={`${c.name}: ${cell?.status ?? 'not in ledger'}${cell?.written ? ` · ${cell.written} rows` : ''}`} />
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-zinc-500">
            {([['covered', 'Covered'], ['empty', 'Nothing applies'], ['in_progress', 'Researching'],
               ['pending', 'Queued'], ['failed', 'Failed'], ['absent', 'Not in ledger']] as const).map(([k, l]) => (
              <span key={k} className="flex items-center gap-1">
                <span className={`inline-block h-2 w-2 rounded-full ${GRID_STATUS[k]}`} /> {l}
              </span>
            ))}
          </div>
        </div>
      ) : coverageTab === 'matrix' ? (
        <>
          {matrix && (
            <div className="mb-3 flex items-center gap-4 text-sm">
              <span className="text-zinc-300">{matrix.summary.total} applicable</span>
              <span className="text-emerald-400">{matrix.summary.with_data} codified</span>
              <button
                onClick={() => setOnlyGaps((v) => !v)}
                className={`rounded px-2 py-0.5 text-xs ${
                  onlyGaps ? 'bg-amber-500/20 text-amber-300' : 'text-amber-400 hover:bg-amber-500/10'
                }`}
              >
                {matrix.summary.missing_data} to fetch
              </button>
              {matrix.scoped_to?.city && matrix.scoped_to.city_found === false && (
                <span className="text-xs text-amber-400">city not found — state ∪ federal</span>
              )}
              {(matrix.summary.engine_cells ?? 0) > 0 && (
                <span className={`rounded border px-2 py-0.5 text-xs ${SOURCE_BADGE.base}`}>
                  {matrix.summary.engine_cells} engine-grounded · {matrix.summary.engine_to_codify ?? 0} to codify
                </span>
              )}
            </div>
          )}
          {matrixLoading ? (
            <div className="py-8 text-center text-sm text-zinc-500">Loading…</div>
          ) : !matrix ? (
            <div className="py-8 text-center text-sm text-zinc-500">No matrix data.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-zinc-500">
                  <tr>
                    <th className="py-2">Category</th>
                    <th className="py-2">Source</th>
                    <th className="py-2">Data</th>
                  </tr>
                </thead>
                <tbody>
                  {grouped.map(([group, cats]) => (
                    <Fragment key={group}>
                      <tr>
                        <td colSpan={3} className="pt-3 text-xs font-semibold uppercase text-zinc-500">
                          {group}
                        </td>
                      </tr>
                      {cats.map((c) => (
                        <tr key={c.slug} className={!c.has_data ? 'bg-amber-950/10' : ''}>
                          <td className="py-1.5 text-zinc-200">{c.name}</td>
                          <td className="py-1.5">
                            <span
                              className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                SOURCE_BADGE[c.source] || SOURCE_BADGE.focused
                              }`}
                            >
                              {c.source}
                            </span>
                          </td>
                          <td className="py-1.5 text-xs">
                            {c.has_data ? (
                              <span className="text-emerald-400">
                                {c.jurisdiction_count} jur · {c.requirement_count} reqs
                              </span>
                            ) : (
                              <span className="text-amber-400">No data</span>
                            )}
                            {c.registry_source === 'engine' && (
                              <span className="ml-2 inline-flex items-center gap-1">
                                <span className={`rounded border px-1.5 py-0.5 text-[10px] ${SOURCE_BADGE.base}`}>
                                  engine
                                </span>
                                <span className="text-zinc-400">
                                  {c.engine_codified ?? 0} codified · {c.engine_to_codify ?? 0} to codify
                                </span>
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
        <>
          {!state.trim() ? (
            <div className="py-6 text-center text-xs text-zinc-500">Set a state to resolve the grounded registry scope.</div>
          ) : resolveError ? (
            <div className="text-xs text-red-400">{resolveError}</div>
          ) : !resolveResult ? (
            <div className="py-6 text-center text-xs text-zinc-500">Resolving…</div>
          ) : (
            <>
              <div className="flex flex-wrap gap-3 text-xs">
                <span className="text-zinc-300">{resolveResult.counts.applicable} applicable</span>
                <span className="text-emerald-400">{resolveResult.counts.codified} codified</span>
                <span className="text-amber-400">{resolveResult.counts.uncodified} to fetch</span>
                {resolveResult.counts.provisional > 0 && (
                  <span className="text-zinc-500">{resolveResult.counts.provisional} provisional (excluded)</span>
                )}
              </div>
              {resolveResult.uncodified.length > 0 && (
                <div className="mt-3">
                  <div className="text-[11px] uppercase text-zinc-500">To fetch</div>
                  <ul className="mt-1 grid gap-1 sm:grid-cols-2">
                    {resolveResult.uncodified.slice(0, 20).map((it) => (
                      <li key={it.citation} className="text-xs text-zinc-400">
                        <CitationLink it={it} onOpen={openReader} />
                        {it.heading ? ` — ${it.heading}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {resolveResult.unmodeled_coordinates.length > 0 && (
                <div className="mt-3 rounded border border-amber-500/30 bg-amber-500/5 p-2 text-[11px] text-amber-300">
                  {resolveResult.unmodeled_coordinates.map((u, i) => (
                    <div key={i}>{u.kind}: {u.note}</div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
