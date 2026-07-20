import type { BadgeVariant } from './Badge'

/**
 * Shared string → BadgeVariant maps.
 *
 * Nine files declared their own copies of these (seven of them in
 * components/er/ alone — ERGuidancePanel.tsx defined three by itself), so the
 * same word rendered in different colors depending on which panel you were
 * looking at.
 *
 * Only genuinely generic vocabularies live here. Domain-specific status maps
 * (ER case status, document processing state, training completion, IR
 * relevance) stay with their domain — they share a shape, not a meaning, and
 * merging them would be a false economy.
 */

/** low / medium / high / critical — the ordered-risk vocabulary. */
export const severityVariant: Record<string, BadgeVariant> = {
  critical: 'critical',
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

/** high / medium / low urgency. Same shape as severity, different subject. */
export const priorityVariant: Record<string, BadgeVariant> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

/**
 * AI/analyst confidence. Note the inversion versus severity: HIGH confidence is
 * good news (green), high severity is bad news (red). They are not
 * interchangeable despite sharing keys.
 *
 * Deliberately NOT adopted by components/er/ERTimelinePanel.tsx, which maps
 * low → 'danger' rather than 'neutral'. That looks like drift but may be
 * intentional — a low-confidence event on a legal timeline arguably warrants a
 * warning rather than a shrug — so it keeps its own map with a note instead of
 * being silently flattened into this one.
 */
export const confidenceVariant: Record<string, BadgeVariant> = {
  high: 'success',
  medium: 'warning',
  low: 'neutral',
}

/** ER investigation outcome. */
export const determinationVariant: Record<string, BadgeVariant> = {
  substantiated: 'danger',
  unsubstantiated: 'success',
  inconclusive: 'warning',
}
