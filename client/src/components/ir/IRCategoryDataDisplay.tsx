import { typeLabel } from '../../types/ir'

type Props = {
  incidentType: string
  categoryData: Record<string, unknown>
}

export function IRCategoryDataDisplay({ incidentType, categoryData }: Props) {
  const fields = Object.entries(categoryData).filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
  if (fields.length === 0) return null

  return (
    <div>
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">
        {typeLabel(incidentType)} Details
      </h3>
      <div className="grid grid-cols-2 gap-3">
        {fields.map(([key, val]) => (
          <div key={key}>
            <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">{typeLabel(key)}</dt>
            <dd className="text-sm text-zinc-200">
              {typeof val === 'boolean' ? (val ? 'Yes' : 'No') : Array.isArray(val) ? val.join(', ') : String(val)}
            </dd>
          </div>
        ))}
      </div>
    </div>
  )
}
