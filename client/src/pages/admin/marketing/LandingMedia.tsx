import { AdminPageHeader } from '../../../components/admin/AdminPageHeader'
import { SchedulingCommercialSettings } from '../../../components/admin/SchedulingCommercialSettings'

export default function LandingMediaAdmin() {
  return (
    <div className="space-y-6">
      <AdminPageHeader
        title="Landing Page Media"
        description="Manage the scheduling page’s commercial. Visitors can watch with sound, use the player controls, or skip to the schedule."
      />
      <SchedulingCommercialSettings />
      <p className="text-xs leading-relaxed text-zinc-500">After you enable and save the commercial, it replaces the scheduling page’s hero animation. Visitors can skip the film to see the schedule demo.</p>
    </div>
  )
}
