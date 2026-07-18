import type { JurisdictionReq, RowContext } from './types'
import { getCategoryLabel } from './helpers'
import RequirementRow from './RequirementRow'

type Props = {
  map: Record<string, JurisdictionReq[]>
  ctx: RowContext
}

// Render category sub-groups within a section (shared by General + Industry).
export default function CategoryGroups({ map, ctx }: Props) {
  return (
    <>
      {Object.entries(map)
        .sort(([a], [b]) => getCategoryLabel(a).localeCompare(getCategoryLabel(b)))
        .map(([cat, reqs], catIdx) => (
          <div key={cat}>
            {catIdx > 0 && <div className="border-t border-zinc-800/30" />}
            <div className="px-4 pt-2 pb-1">
              <p className="text-xs uppercase tracking-wide text-zinc-400">{getCategoryLabel(cat)}</p>
            </div>
            {reqs.map((req) => <RequirementRow key={req.id} req={req} ctx={ctx} />)}
          </div>
        ))}
    </>
  )
}
