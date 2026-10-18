import { AdminButton as Button, AdminButton } from '../AdminUI'
import type { JurisdictionDetail } from './types'

type Props = {
  city: string
  state: string
  detail: JurisdictionDetail | null
  loading: boolean
  scanning: boolean
  specialtyRunning: boolean
  medicalRunning: boolean
  lifeSciRunning: boolean
  fedSourcesRunning: boolean
  onViewCoverage?: () => void
  startCheck: () => void
  startSpecialtyCheck: () => void
  startMedicalCheck: () => void
  startLifeSciCheck: () => void
  startFedSourcesCheck: () => void
}

export default function Toolbar({
  city, state, detail, loading,
  scanning, specialtyRunning, medicalRunning, lifeSciRunning, fedSourcesRunning,
  onViewCoverage, startCheck, startSpecialtyCheck, startMedicalCheck, startLifeSciCheck, startFedSourcesCheck,
}: Props) {
  const anyRunning = scanning || specialtyRunning || medicalRunning || lifeSciRunning || fedSourcesRunning || loading
  return (
    <div className="flex items-center justify-between mb-3">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-base font-medium text-zinc-100">{city}, {state}</h2>
          {onViewCoverage && (
            <button type="button" onClick={onViewCoverage}
              className="text-[11px] text-emerald-400/80 hover:text-emerald-300 transition-colors">
              View coverage →
            </button>
          )}
        </div>
        {detail && (
          <p className="text-[11px] text-zinc-500 mt-0.5">
            {detail.requirements.length} requirements · {detail.legislation.length} legislation · {detail.locations.length} locations
            {detail.county && ` · ${detail.county} County`}
          </p>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <Button variant="secondary" size="sm" disabled={anyRunning} onClick={startCheck}>
          {scanning ? 'Scanning...' : 'Run Check'}
        </Button>
        <AdminButton onClick={startSpecialtyCheck} disabled={anyRunning}
          className="text-purple-400 disabled:opacity-30"
          title="Research healthcare + oncology specialty policies" variant="ghost">
          {specialtyRunning ? 'Running...' : 'Specialty'}
        </AdminButton>
        <AdminButton onClick={startMedicalCheck} disabled={anyRunning}
          className="text-teal-400 disabled:opacity-30"
          title="Research health specs (17 categories)" variant="ghost">
          {medicalRunning ? 'Running...' : 'Health Specs'}
        </AdminButton>
        <AdminButton onClick={startLifeSciCheck} disabled={anyRunning}
          className="text-blue-400 disabled:opacity-30"
          title="Research life sciences / biotech (6 categories)" variant="ghost">
          {lifeSciRunning ? 'Running...' : 'Life Sci'}
        </AdminButton>
        <AdminButton onClick={startFedSourcesCheck} disabled={anyRunning}
          className="text-amber-400 disabled:opacity-30"
          title="Fetch from Federal Register, CMS, Congress.gov" variant="ghost">
          {fedSourcesRunning ? 'Fetching...' : 'Fed Sources'}
        </AdminButton>
      </div>
    </div>
  )
}
