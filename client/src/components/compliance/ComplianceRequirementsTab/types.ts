import type { ComplianceRequirement, FacilityAttributes } from '../../../types/compliance'
import type { Authority } from '../../../hooks/compliance/useComplianceRequirements'
import type { ComplianceCheckMessage } from '../../../hooks/compliance/useComplianceCheck'

export type Props = {
  requirements: ComplianceRequirement[]
  loading: boolean
  onPin: (requirementId: string, isPinned: boolean) => void
  checkMessages: ComplianceCheckMessage[]
  facilityAttributes?: FacilityAttributes | null
  /** Read-only mode (compliance_lite taste) — hide Pin (the pin endpoint is
   *  Pro-gated and would 403). */
  readOnly?: boolean
  /** Lite preview: show only the first N categories fully; blur the rest behind
   *  an upgrade CTA. When set, the search/filter controls are hidden so the blur
   *  can't be bypassed. */
  previewCategoryLimit?: number
  /** A catalog requirement (jurisdiction_requirement_id + title) to focus —
   *  cited by the regulatory-ask sources. Expands its category, scrolls it into
   *  view, and highlights it. The title is the fallback when the row isn't in
   *  this location's list. */
  targetReq?: { id: string; title?: string | null } | null
  onTargetConsumed?: () => void
}

export type GroupBy = 'topic' | 'jurisdiction'

/** Props shared by every place that renders a category accordion row (topic,
 *  jurisdiction, lite preview). */
export type CategoryRowShared = {
  expanded: Set<string>
  toggle: (cat: string) => void
  missingCoverage: Set<string>
  knownAuthorities: Map<string, Authority>
  highlightId: string | null
  /** Read-only mode — hide Pin. */
  readOnly?: boolean
  onPin: (requirementId: string, isPinned: boolean) => void
}
