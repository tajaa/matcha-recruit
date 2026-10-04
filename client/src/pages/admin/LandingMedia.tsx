import { SchedulingCommercialSettings } from '../../components/admin/SchedulingCommercialSettings'

export default function LandingMediaAdmin() {
  return (
    <div className="max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">Landing Page Media</h1>
        <p className="mt-2 text-sm leading-relaxed text-zinc-400">Manage the home page’s scheduling commercial. Visitors can watch with sound, use the player controls, or skip to the schedule.</p>
      </div>
      <SchedulingCommercialSettings />
      <p className="text-xs leading-relaxed text-zinc-500">After you enable and save the commercial, it replaces the home page’s hero animation. Visitors can skip the film to see the schedule demo.</p>
    </div>
  )
}
