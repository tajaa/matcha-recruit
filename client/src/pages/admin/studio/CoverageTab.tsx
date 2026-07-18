import { Input, LABEL, Select } from '../../../components/ui'
import { Telescope } from 'lucide-react'
import SpecialtyReviewModal from './SpecialtyReviewModal'
import type { GotoParams, StudioView } from './types'
import { HEADCOUNTS, INDUSTRIES, MODEL_LABELS } from './CoverageTab/constants'
import { Stat } from './CoverageTab/Stat'
import { LaborScopePanel } from './CoverageTab/LaborScopePanel'
import { IndustryCoveragePanel } from './CoverageTab/IndustryCoveragePanel'
import { StatuteReaderDrawer } from './CoverageTab/StatuteReaderDrawer'
import { useCoverage } from './CoverageTab/useCoverage'

// ── The tab ───────────────────────────────────────────────────────────────────

export default function CoverageTab({
  initialIndustry, initialState, initialCity, initialHeadcount, onMutate, goto,
}: {
  initialIndustry?: string | null
  initialState?: string | null
  initialCity?: string | null
  initialHeadcount?: string | null
  // Bumped after any registry-mutating action here (research/reconcile) so the
  // shell/other tabs can refresh their worklist counts.
  onMutate?: () => void
  // Cross-link into the Library shelf for a coordinate.
  goto?: (next: StudioView, params?: GotoParams & { section?: string }) => void
}) {
  const {
    industry, setIndustry, state, setState, city, setCity, headcount, setHeadcount,
    specialties, available,
    matrix, matrixLoading, onlyGaps, setOnlyGaps,
    resolveResult, resolveError,
    laborScope, laborError,
    newSpecialty, setNewSpecialty, discovering, proposal, setProposal,
    specialtyError, researchTarget,
    research,
    laborRef, coverageTab, setCoverageTab,
    grid, gridLoading, gridIndustry, setGridIndustry,
    generalCov,
    reader, setReader, openReader,
    modelMode,
    grouped, kpis,
    toggleSpecialty, discoverSpecialty, onSpecialtyConfirmed,
    researchTargetGap, researchFetchQueue,
  } = useCoverage({ initialIndustry, initialState, initialCity, initialHeadcount, onMutate })

  return (
    <div className="text-zinc-200">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className={LABEL}>Exhaustiveness deep-dive</div>
          <h2 className="mt-0.5 flex items-center gap-2 text-lg font-semibold tracking-tight text-zinc-100">
            <Telescope className="h-4 w-4 text-emerald-400" /> Coverage
          </h2>
          <p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-zinc-500">
            One coordinate → the labor scope we must fetch, its grounded registry resolution, and
            derive → confirm → research the gap.
          </p>
        </div>
        {(() => {
          const info = MODEL_LABELS[modelMode] || MODEL_LABELS.light
          const dot = modelMode === 'heavy' ? 'bg-purple-400' : 'bg-blue-400'
          return (
            <div className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5"
                 title={`Research model: ${info.model}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-300">{info.label}</span>
              <span className="hidden font-mono text-[10px] tracking-wide text-zinc-600 sm:inline">{info.model}</span>
            </div>
          )
        })()}
      </div>

      {/* Coordinate bar */}
      <div className="mb-4 grid grid-cols-2 gap-4 rounded-xl border border-white/[0.06] bg-zinc-950 p-4 sm:grid-cols-4">
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">Industry</label>
          <Select options={INDUSTRIES} value={industry} onChange={(e) => setIndustry(e.target.value)} />
        </div>
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">State</label>
          <Input value={state} onChange={(e) => setState(e.target.value)} placeholder="CA" maxLength={2} className="uppercase" />
        </div>
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">City (optional)</label>
          <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Los Angeles" />
        </div>
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">Headcount</label>
          <Select options={HEADCOUNTS.map((h) => ({ value: h, label: h || 'Any' }))} value={headcount}
                  onChange={(e) => setHeadcount(e.target.value)} />
        </div>
      </div>

      {/* KPI headline strip */}
      <div className="mb-5 flex items-stretch divide-x divide-white/[0.06] overflow-x-auto rounded-xl border border-white/[0.06] bg-zinc-950">
        <Stat label="Core labor" value={kpis ? kpis.core : '—'} delay={0}
              tone={kpis ? (kpis.coreComplete ? 'text-emerald-400' : 'text-amber-400') : 'text-zinc-600'} />
        <Stat label="Codified" value={kpis ? String(kpis.codified) : '—'} delay={40}
              tone={kpis ? 'text-emerald-400' : 'text-zinc-600'} />
        <Stat label="To fetch" value={kpis ? String(kpis.toFetch) : '—'} delay={80}
              tone={kpis ? (kpis.toFetch > 0 ? 'text-amber-400' : 'text-emerald-400') : 'text-zinc-600'}
              hint={kpis && kpis.toFetch > 0 ? 'Jump to the labor worklist' : undefined}
              onClick={kpis && kpis.toFetch > 0
                ? () => laborRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                : undefined} />
        <Stat label="To classify" value={kpis ? String(kpis.toClassify) : '—'} delay={120}
              tone={kpis && kpis.toClassify > 0 ? 'text-amber-400' : kpis ? 'text-zinc-300' : 'text-zinc-600'} />
      </div>

      {/* Labor scope — PRIMARY */}
      <LaborScopePanel
        laborRef={laborRef}
        laborScope={laborScope}
        laborError={laborError}
        research={research}
        researchFetchQueue={researchFetchQueue}
        generalCov={generalCov}
        openReader={openReader}
      />

      {/* Industry & specialty coverage — SECONDARY */}
      <IndustryCoveragePanel
        coverageTab={coverageTab}
        setCoverageTab={setCoverageTab}
        available={available}
        specialties={specialties}
        toggleSpecialty={toggleSpecialty}
        newSpecialty={newSpecialty}
        setNewSpecialty={setNewSpecialty}
        discoverSpecialty={discoverSpecialty}
        discovering={discovering}
        specialtyError={specialtyError}
        researchTarget={researchTarget}
        researchTargetGap={researchTargetGap}
        research={research}
        state={state}
        gridIndustry={gridIndustry}
        setGridIndustry={setGridIndustry}
        grid={grid}
        gridLoading={gridLoading}
        goto={goto}
        matrix={matrix}
        matrixLoading={matrixLoading}
        onlyGaps={onlyGaps}
        setOnlyGaps={setOnlyGaps}
        grouped={grouped}
        resolveResult={resolveResult}
        resolveError={resolveError}
        openReader={openReader}
      />

      {proposal && (
        <SpecialtyReviewModal
          proposal={proposal}
          industry={industry}
          onCancel={() => setProposal(null)}
          onConfirmed={onSpecialtyConfirmed}
        />
      )}

      {/* Statute reader — the full regulation text, in-app */}
      <StatuteReaderDrawer reader={reader} setReader={setReader} />
    </div>
  )
}
