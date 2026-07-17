/**
 * Rail icons, drawn for this product rather than picked off the shelf.
 *
 * The stock set was generic and, worse, imprecise: a courtroom gavel stood for
 * progressive discipline, a lightning bolt for compliance setup, and the same
 * Sparkles glyph did duty for both Handbook Pilot and What's New. These are
 * built from the vocabulary the product actually deals in — sheets, rules,
 * marks and seals — so a step ladder means progressive discipline and a seal
 * means credentialing.
 *
 * One construction language throughout: a 24 grid, ~18px live area, a single
 * inherited stroke weight, round caps and joins, no fills. Drop-in compatible
 * with the lucide props the rail already passes (className, strokeWidth), so
 * sidebars can mix these with lucide while the set grows.
 */

type IconProps = { className?: string; strokeWidth?: number }

const base = (p: IconProps) => ({
  className: p.className,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: p.strokeWidth ?? 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
})

/** Incidents — the alert triangle stays; it's read instantly and novelty here
 *  would cost comprehension for nothing. Redrawn to this set's proportions. */
export const IconIncident = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 4.4 20.4 19.2H3.6z" />
    <path d="M12 10v3.4" />
    <path d="M12 16.4h.01" />
  </svg>
)

/** Risk Insights — a trend line resolving to a plotted point. */
export const IconTrend = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M3.8 16.6 9 11.2l3.4 3.4L18.6 8" />
    <circle cx="19.4" cy="7.2" r="1.7" />
  </svg>
)

/** OSHA Logs — a ruled ledger sheet: the log itself. */
export const IconLedger = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="4.6" y="3.4" width="14.8" height="17.2" rx="2" />
    <path d="M8.2 8.6h7.6M8.2 12.4h7.6M8.2 16.2h4.4" />
  </svg>
)

/** Handbooks — a bound book, spine out. */
export const IconBook = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6.4 4.6A1.6 1.6 0 0 1 8 3h11.4v18H8a1.6 1.6 0 0 1-1.6-1.6z" />
    <path d="M6.4 16.8h13" />
  </svg>
)

/** Handbook Audit — the sheet, read closely. */
export const IconAudit = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M18.4 10.6V5a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3.4" />
    <path d="M8.4 7.6h6.6M8.4 11.2h3.4" />
    <circle cx="16.2" cy="16.2" r="3.4" />
    <path d="m18.8 18.8 2.2 2.2" />
  </svg>
)

/** Handbook Pilot — the sheet, drafted for you. */
export const IconDraft = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M18.6 11V5a2 2 0 0 0-2-2H7.2a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4.4" />
    <path d="M8.6 7.8h6.6M8.6 11.4h3.6" />
    <path d="m17.8 14 1.2 2.9 2.9 1.2-2.9 1.2-1.2 2.9-1.2-2.9-2.9-1.2 2.9-1.2z" />
  </svg>
)

/** Compliance — a shield. */
export const IconShield = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3.2 19 6v5.6c0 4.3-2.9 7.6-7 8.9-4.1-1.3-7-4.6-7-8.9V6z" />
  </svg>
)

/** Employees — people, on a shared baseline. */
export const IconPeople = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="9.4" cy="8.6" r="3.1" />
    <path d="M3.8 19.4c0-3.1 2.5-5.2 5.6-5.2s5.6 2.1 5.6 5.2" />
    <path d="M16.4 6.2a3.1 3.1 0 0 1 0 5.9" />
    <path d="M17.6 14.6c1.7.7 2.8 2.4 2.8 4.8" />
  </svg>
)

/** Training — a mortarboard. */
export const IconTraining = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 4.6 21.2 9 12 13.4 2.8 9z" />
    <path d="M6.6 11.2v4.6c0 1.7 2.4 3 5.4 3s5.4-1.3 5.4-3v-4.6" />
  </svg>
)

/** Performance Action — the progressive ladder, which is what the workflow
 *  actually is: each step escalates. (Was a courtroom gavel.) */
export const IconSteps = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M3.4 19.6h4.4v-4.4h4.4v-4.4h4.4V6.4h4" />
  </svg>
)

/** Credentialing — a seal with ribbon: a credential in hand. (Was a check
 *  badge, which read as generic "verified".) */
export const IconSeal = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="9.4" r="5.6" />
    <path d="m8.6 14.2-1.4 6.2L12 18l4.8 2.4-1.4-6.2" />
  </svg>
)

/** Company — the building. */
export const IconCompany = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4.6 20.6V5.4a2 2 0 0 1 2-2h10.8a2 2 0 0 1 2 2v15.2" />
    <path d="M3.4 20.6h17.2" />
    <path d="M9 8h1.2M13.8 8H15M9 12h1.2M13.8 12H15" />
    <path d="M10.2 20.6v-3.4h3.6v3.4" />
  </svg>
)

/** Compliance Setup — sliders: the thing being configured. (Was a lightning
 *  bolt, which said "fast" rather than "set this up".) */
export const IconSetup = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 8.4h8.2M16.6 8.4h3.4" />
    <circle cx="14.4" cy="8.4" r="2.2" />
    <path d="M4 15.6h3.4M11.8 15.6h8.2" />
    <circle cx="9.6" cy="15.6" r="2.2" />
  </svg>
)

/** Resources — an open reference. */
export const IconResources = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 7.4C10 5.7 7.6 5 4.2 5v12.6c3.4 0 5.8.7 7.8 2.4 2-1.7 4.4-2.4 7.8-2.4V5c-3.4 0-5.8.7-7.8 2.4z" />
    <path d="M12 7.4V20" />
  </svg>
)

/** What's New — a single spark. Distinct from Handbook Pilot, which pairs its
 *  spark with a sheet; the stock set used one glyph for both. */
export const IconSpark = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m12 3.4 1.9 5.9 5.9 1.9-5.9 1.9L12 19l-1.9-5.9-5.9-1.9 5.9-1.9z" />
  </svg>
)
