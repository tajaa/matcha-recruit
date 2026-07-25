import type {
  RequirementComponent,
  RequirementComponentSummary,
} from '../../../types/compliance'

// Shared between the static checklist and the audit-reveal animation so the
// two can never render different copy/colors for the same status. `unknown`
// reads as "no evidence on file" — never "GAP": absence of a record is not
// proof of a violation (compliance_status.py's blind-never-violating
// invariant). `GAP` is reserved for `non_compliant`, a verdict actually
// derived from the tenant's own records.
export const STATUS_LABEL: Record<RequirementComponent['status'], string> = {
  compliant: 'Compliant',
  non_compliant: 'Gap',
  in_progress: 'In progress',
  unknown: 'No evidence on file',
}

export const STATUS_CLASS: Record<RequirementComponent['status'], string> = {
  compliant: 'bg-emerald-900/20 text-emerald-400 border-emerald-800/40',
  non_compliant: 'bg-red-900/20 text-red-400 border-red-800/40',
  in_progress: 'bg-amber-900/20 text-amber-400 border-amber-800/40',
  unknown: 'bg-white/[0.04] text-zinc-400 border-white/[0.08]',
}

// Mirror of compliance_status.py:rollup — used to recompute the coverage line
// after a successful attestation, so the header can't keep printing the
// server's pre-attest numbers under a row that already flipped to Compliant.
// `known` excludes `unknown` for the same reason it does server-side: the
// number exists to admit how much of the obligation surface is unmeasured.
export function rollupComponents(
  components: RequirementComponent[],
): RequirementComponentSummary {
  const total = components.length
  const count = (s: RequirementComponent['status']) =>
    components.filter((c) => c.status === s).length
  const known = total - count('unknown')
  return {
    total,
    known,
    coverage_pct: total ? Math.round((100 * known) / total) : null,
    derived: components.filter((c) => c.basis === 'derived').length,
    attested: components.filter((c) => c.basis === 'attested').length,
    count_compliant: count('compliant'),
    count_non_compliant: count('non_compliant'),
    count_in_progress: count('in_progress'),
    count_unknown: count('unknown'),
  }
}

export const STATUS_GLYPH: Record<RequirementComponent['status'], string> = {
  compliant: '✓',
  non_compliant: '✗',
  in_progress: '◐',
  unknown: '⊘',
}
