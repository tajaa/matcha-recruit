import { useEffect } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import {
  normalizeCategoryKey,
  jurisdictionSectionId,
  requirementAuthority,
} from '../../../hooks/compliance/useComplianceRequirements'
import type { Authority } from '../../../hooks/compliance/useComplianceRequirements'
import type { ComplianceRequirement } from '../../../types/compliance'
import type { CategoryGroup } from '../../../generated/complianceCategories'

type Params = {
  targetReq?: { id: string; title?: string | null } | null
  requirements: ComplianceRequirement[]
  loading: boolean
  knownAuthorities: Map<string, Authority>
  onTargetConsumed?: () => void
  setSearchQuery: (value: string) => void
  setGroupFilter: (value: 'all' | CategoryGroup) => void
  setExpanded: Dispatch<SetStateAction<Set<string>>>
  setHighlightId: (value: string | null) => void
}

// Focus a requirement cited by the "Ask" sources: expand its category, scroll
// to it, highlight it briefly.
export function useTargetReqFocus({
  targetReq,
  requirements,
  loading,
  knownAuthorities,
  onTargetConsumed,
  setSearchQuery,
  setGroupFilter,
  setExpanded,
  setHighlightId,
}: Params) {
  useEffect(() => {
    if (!targetReq) return
    const match = requirements.find((r) => r.jurisdiction_requirement_id === targetReq.id)
    if (!match) {
      // The location's requirements may still be in flight (clicking a source
      // with no location selected picks one, THEN fetches). Consuming the target
      // here would drop it before the data it needs ever arrives.
      if (loading || requirements.length === 0) return
      // A real miss: the "Ask" cites the shared catalog, which can hold a row
      // this location never materialized. Search by title so the click still
      // lands somewhere, instead of doing nothing at all.
      setSearchQuery(targetReq.title ?? '')
      setGroupFilter('all')
      onTargetConsumed?.()
      return
    }
    setSearchQuery('')
    setGroupFilter('all')
    // Expand under BOTH lenses' keys — the row is reachable from either, and
    // this stays correct if the user toggles the view after the jump.
    const cat = normalizeCategoryKey(match.category || 'other')
    const authority = requirementAuthority(match, knownAuthorities)
    const jurKey = `${jurisdictionSectionId(authority.level, authority.name)}::${cat}`
    setExpanded((prev) => new Set(prev).add(cat).add(jurKey))
    setHighlightId(match.id)
    // Deliberately NOT cleaned up. Consuming the target below re-renders with
    // changed deps, which runs this effect's own cleanup — a clearTimeout there
    // killed the 60ms scroll before it ever fired (and left the highlight on
    // forever), which is most of the "chips don't take me to the requirement"
    // this whole path exists to fix. Both timers are one-shot and harmless late:
    // querySelector just misses, and setHighlightId on an unmounted component is
    // a no-op.
    setTimeout(() => {
      document.querySelector(`[data-req-id="${match.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 60)
    setTimeout(() => setHighlightId(null), 4000)
    onTargetConsumed?.()
  }, [targetReq, requirements, loading, knownAuthorities, onTargetConsumed])
}
