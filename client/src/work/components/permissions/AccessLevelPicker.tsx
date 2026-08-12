import { Check, Shield, Eye, Play, UserRound } from 'lucide-react'
import type { WorkAccessLevel } from '../../api/workPermissions'
import { ACCESS_LEVEL_COPY, ACCESS_LEVELS, type GrantableWorkAccessLevel } from '../../utils/workAccess'

interface Props {
  value: Exclude<WorkAccessLevel, 'guest'>
  onChange: (level: Exclude<WorkAccessLevel, 'guest'>) => void
  disabled?: boolean
}

const icons = { member: UserRound, reviewer: Eye, operator: Play, admin: Shield }

export default function AccessLevelPicker({ value, onChange, disabled = false }: Props) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {ACCESS_LEVELS.map((level: GrantableWorkAccessLevel) => {
        const copy = ACCESS_LEVEL_COPY[level]
        const Icon = icons[level]
        const selected = value === level
        return (
          <button
            key={level}
            type="button"
            disabled={disabled}
            onClick={() => onChange(level)}
            className={`text-left rounded-xl border p-3 transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
              selected
                ? 'border-w-accent bg-w-accent/10 ring-1 ring-w-accent/40'
                : 'border-w-line bg-w-surface2/40 hover:border-w-accent/50'
            }`}
          >
            <div className="flex items-start gap-2">
              <Icon size={16} className={selected ? 'text-w-accent' : 'text-w-dim'} />
              <span className="flex-1 min-w-0">
                <span className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-w-text">{copy.label}</span>
                  {selected && <Check size={15} className="text-w-accent" />}
                </span>
                <span className="block text-xs text-w-dim mt-0.5">{copy.short}</span>
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}
