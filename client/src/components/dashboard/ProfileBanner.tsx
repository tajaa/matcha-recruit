import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Button } from '../ui'
import { UserCircle, X } from 'lucide-react'

const DISMISS_KEY = 'company_profile_banner_dismissed'

interface ProfileBannerProps {
  onboardingNeeded: Record<string, boolean>
}

export function ProfileBanner({ onboardingNeeded }: ProfileBannerProps) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === '1'
  )
  const navigate = useNavigate()

  if (dismissed || !onboardingNeeded.company_profile) return null

  return (
    <Card className="flex items-center gap-4 p-4 mb-6 border-emerald-800/40">
      <div className="rounded-lg bg-emerald-900/40 p-2">
        <UserCircle className="h-5 w-5 text-emerald-400" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-zinc-200">Complete your company profile</p>
        <p className="text-xs text-zinc-500 mt-0.5">
          Add your headquarters, benefits, and employment details to unlock full compliance tracking.
        </p>
      </div>
      <Button size="sm" onClick={() => navigate('/app/settings')}>
        Complete Profile
      </Button>
      <button
        type="button"
        onClick={() => { localStorage.setItem(DISMISS_KEY, '1'); setDismissed(true) }}
        className="text-zinc-600 hover:text-zinc-400 transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </Card>
  )
}
