import {
  Users, MapPin, CalendarCheck, Search, FileSearch, Scale,
  CheckCircle2, AlertTriangle, XCircle, Sparkles,
} from 'lucide-react'
import type { ResolvedScopeMissing } from '../../../api/admin/adminOnboarding'
import type { ResearchGapItem } from '../../../hooks/admin/useResearchGaps'
import type { EnrichEvent } from '../../../hooks/admin/useEnrichStream'

export function missingId(m: ResolvedScopeMissing): string {
  return [m.category_slug, m.scope_level, m.state || '-', m.county || '-', m.city || '-'].join('::')
}

export function toResearchItem(m: ResolvedScopeMissing): ResearchGapItem {
  return { category_slug: m.category_slug, scope_level: m.scope_level, state: m.state, county: m.county, city: m.city }
}

export function eventStyle(type: string): { icon: React.ElementType; color: string; spin?: boolean } {
  switch (type) {
    case 'roster_scanned':
    case 'roles_detected': return { icon: Users, color: 'text-blue-400' }
    case 'jurisdiction_new': return { icon: MapPin, color: 'text-amber-400' }
    case 'jurisdiction_tracking': return { icon: CalendarCheck, color: 'text-emerald-400' }
    case 'researching':
    case 'repository_refresh':
    case 'retrying': return { icon: Search, color: 'text-violet-400', spin: true }
    case 'repository_refreshed':
    case 'started':
    case 'facility_inference': return { icon: FileSearch, color: 'text-violet-300' }
    case 'scoping': return { icon: Scale, color: 'text-blue-400' }
    case 'scoped':
    case 'complete': return { icon: CheckCircle2, color: 'text-emerald-400' }
    case 'warning':
    case 'repository_only': return { icon: AlertTriangle, color: 'text-amber-400' }
    case 'error': return { icon: XCircle, color: 'text-red-400' }
    default: return { icon: Sparkles, color: 'text-zinc-400' }
  }
}

export function eventText(ev: EnrichEvent): string {
  if (ev.message) return ev.message
  if (ev.type === 'complete') return 'Analysis complete.'
  return ev.type.replace(/_/g, ' ')
}
