// Provenance chip for the Coverage stat card — engine = scope-registry grounded,
// engine_partial = grounded but on a partially-classified index (a floor, not the
// whole scope), bank = compliance-catalog fallback. Same chip idiom as
// ScopeStudio's badge maps.
export const COVERAGE_SOURCE_BADGE: Record<'engine' | 'engine_partial' | 'bank', string> = {
  engine: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300',
  engine_partial: 'border-amber-500/30 bg-amber-500/15 text-amber-300',
  bank: 'border-zinc-500/30 bg-zinc-500/15 text-zinc-400',
}

export const COVERAGE_SOURCE_LABEL: Record<'engine' | 'engine_partial' | 'bank', string> = {
  engine: 'grounded (engine)',
  engine_partial: 'grounded (partial)',
  bank: 'catalog (bank)',
}

export const COVERAGE_SOURCE_TITLE: Record<'engine' | 'engine_partial' | 'bank', string> = {
  engine: 'Grounded in the scope-registry engine (registry classifies every coordinate)',
  engine_partial:
    'Grounded in the scope-registry engine, but at least one covering authority index is not fully classified — these obligations really are in scope, but unclassified items may add more.',
  bank: 'From the compliance catalog (registry not yet definitive for this company)',
}
