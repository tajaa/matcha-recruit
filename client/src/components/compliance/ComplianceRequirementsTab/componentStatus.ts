import type { RequirementComponent } from '../../../types/compliance'

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

export const STATUS_GLYPH: Record<RequirementComponent['status'], string> = {
  compliant: '✓',
  non_compliant: '✗',
  in_progress: '◐',
  unknown: '⊘',
}
