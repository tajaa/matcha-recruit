import {
  CATEGORY_SHORT_LABELS,
  CATEGORY_GROUPS,
  ALL_CATEGORY_KEYS,
} from '../../../generated/complianceCategories'
import type { SpecialtyFilter } from './types'

type Props = {
  value: SpecialtyFilter
  onChange: (value: SpecialtyFilter) => void
  className?: string
}

const OPTGROUP_CONFIGS: { label: string; group: string }[] = [
  { label: 'Healthcare', group: 'healthcare' },
  { label: 'Oncology', group: 'oncology' },
  { label: 'Medical Compliance', group: 'medical_compliance' },
  { label: 'Life Sciences', group: 'life_sciences' },
]

export default function SpecialtyFilterSelect({ value, onChange, className }: Props) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={className ?? 'bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5 focus:border-zinc-500'}
    >
      <option value="all">All Specialties</option>
      <option value="general">General Labor</option>
      <option value="healthcare">Healthcare (all)</option>
      <option value="oncology">Oncology (all)</option>
      <option value="medical">Medical Compliance (all)</option>
      <option value="life_sciences">Life Sciences (all)</option>
      {OPTGROUP_CONFIGS.map(({ label, group }) => (
        <optgroup key={group} label={label}>
          {ALL_CATEGORY_KEYS
            .filter(k => CATEGORY_GROUPS[k] === group)
            .sort((a, b) => (CATEGORY_SHORT_LABELS[a] || a).localeCompare(CATEGORY_SHORT_LABELS[b] || b))
            .map(k => (
              <option key={k} value={k}>{CATEGORY_SHORT_LABELS[k] || k}</option>
            ))}
        </optgroup>
      ))}
    </select>
  )
}
