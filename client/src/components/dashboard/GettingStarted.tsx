import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card } from '../ui'
import {
  Building2, Shield, Users, FileText, Plug, Check, X,
} from 'lucide-react'

interface GettingStartedProps {
  userId: string
  onboardingNeeded: Record<string, boolean>
  enabledFeatures: Record<string, boolean>
}

const ALL_ITEMS = [
  { key: 'company_profile', label: 'Complete company profile', icon: Building2, href: '/app/company', feature: null },
  { key: 'compliance', label: 'Add business locations', icon: Shield, href: '/app/compliance', feature: 'compliance' },
  { key: 'employees', label: 'Import employees', icon: Users, href: '/app/employees', feature: 'employees' },
  { key: 'policies', label: 'Create your first policy', icon: FileText, href: '/app/handbooks', feature: 'policies' },
  { key: 'integrations', label: 'Connect integrations', icon: Plug, href: '/app/company', feature: 'onboarding' },
] as const

export function GettingStarted({ userId, onboardingNeeded, enabledFeatures }: GettingStartedProps) {
  const dismissKey = `getting_started_dismissed_${userId}`
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(dismissKey) === '1'
  )
  const navigate = useNavigate()

  const items = ALL_ITEMS.filter(
    (i) => i.feature === null || enabledFeatures[i.feature]
  )

  const doneCount = items.filter((i) => !onboardingNeeded[i.key]).length
  const progress = items.length > 0 ? Math.round((doneCount / items.length) * 100) : 100

  if (dismissed || doneCount === items.length) return null

  return (
    <Card className="p-5 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">Getting Started</h3>
        <button
          type="button"
          onClick={() => { localStorage.setItem(dismissKey, '1'); setDismissed(true) }}
          className="text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-1">
          <span>{doneCount} of {items.length} complete</span>
          <span>{progress}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-zinc-800">
          <div
            className="h-1.5 rounded-full bg-emerald-500 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="space-y-2">
        {items.map((item) => {
          const done = !onboardingNeeded[item.key]
          return (
            <button
              key={item.key}
              type="button"
              onClick={!done ? () => navigate(item.href) : undefined}
              className={`flex items-center gap-3 w-full rounded-lg px-3 py-2 text-left transition-colors ${
                done
                  ? 'opacity-50 cursor-default'
                  : 'hover:bg-zinc-800 cursor-pointer'
              }`}
            >
              {done ? (
                <Check className="h-4 w-4 text-emerald-500 shrink-0" />
              ) : (
                <item.icon className="h-4 w-4 text-zinc-500 shrink-0" />
              )}
              <span className={`text-sm ${done ? 'text-zinc-600 line-through' : 'text-zinc-300'}`}>
                {item.label}
              </span>
            </button>
          )
        })}
      </div>
    </Card>
  )
}
