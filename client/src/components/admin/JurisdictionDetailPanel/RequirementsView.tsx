import type { SpecialtyFilter } from '../jurisdiction/types'
import type { JurisdictionDetail, JurisdictionReq, RowContext } from './types'
import { industryLabel, sectionAnchor } from './helpers'
import CategoryGroups from './CategoryGroups'

type Sectioned = {
  general: Record<string, JurisdictionReq[]>
  generalCount: number
  industries: Record<string, Record<string, JurisdictionReq[]>>
  industryTags: string[]
}

type Props = {
  detail: JurisdictionDetail
  specialtyFilter: SpecialtyFilter
  categoryFilteredReqs: JurisdictionReq[]
  sectioned: Sectioned
  onNavigate?: (id: string) => void
  ctx: RowContext
}

export default function RequirementsView({ detail, specialtyFilter, categoryFilteredReqs, sectioned, onNavigate, ctx }: Props) {
  if (categoryFilteredReqs.length === 0) {
    return (
      <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center space-y-2">
        <p className="text-sm text-zinc-600">
          No city-level requirements{specialtyFilter !== 'all' ? ' for this specialty' : ''}.
        </p>
        {detail.state && (
          <div className="text-sm">
            <p className="text-zinc-500">
              {detail.parent_id
                ? `This city inherits policies from its state jurisdiction (${detail.state}).`
                : `City-specific data has not been researched yet. State-level ${detail.state} policies may apply.`
              }
            </p>
            {detail.parent_id ? (
              <button
                onClick={() => onNavigate?.(detail.parent_id!)}
                className="mt-1 text-blue-400 hover:text-blue-300 underline underline-offset-2"
              >
                View {detail.state} state policies
              </button>
            ) : (
              <p className="text-xs text-zinc-500 mt-1">
                Run a compliance check or use /research-jurisdiction to populate.
              </p>
            )}
          </div>
        )}
        {!detail.state && (
          <p className="text-xs text-zinc-600">Run a check to populate.</p>
        )}
      </div>
    )
  }

  return (
    <div className="border border-zinc-800 rounded-lg max-h-[55vh] overflow-y-auto divide-y divide-zinc-800/60">
      {/* General employment law — applies to every business here */}
      {sectioned.generalCount > 0 && (
        <div id={sectionAnchor('general')}>
          <div className="px-4 py-2 bg-emerald-500/[0.06]">
            <p className="text-[11px] font-semibold text-emerald-300 uppercase tracking-wide">
              General employment law
              <span className="ml-1.5 text-zinc-500 font-normal normal-case">· {sectioned.generalCount} · every business here answers to these</span>
            </p>
          </div>
          <CategoryGroups map={sectioned.general} ctx={ctx} />
        </div>
      )}
      {/* Industry-specific — grouped by applicable industry tag */}
      {sectioned.industryTags.map((tag) => {
        const cats = sectioned.industries[tag]
        const count = Object.values(cats).reduce((n, a) => n + a.length, 0)
        return (
          <div key={tag} id={sectionAnchor(tag)}>
            <div className="px-4 py-2 bg-blue-500/[0.06]">
              <p className="text-[11px] font-semibold text-blue-300 uppercase tracking-wide">
                {industryLabel(tag)}
                <span className="ml-1.5 text-zinc-500 font-normal normal-case">· {count} · industry-specific</span>
              </p>
            </div>
            <CategoryGroups map={cats} ctx={ctx} />
          </div>
        )
      })}
    </div>
  )
}
