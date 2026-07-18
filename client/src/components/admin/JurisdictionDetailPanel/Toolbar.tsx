import { Button } from '../../ui'
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
        <button onClick={startSpecialtyCheck} disabled={anyRunning}
          className="px-2.5 py-1.5 text-[11px] font-medium border rounded transition-colors
            text-purple-400 border-purple-500/40 hover:bg-purple-500/10 disabled:opacity-30"
          title="Research healthcare + oncology specialty policies">
          {specialtyRunning ? 'Running...' : 'Specialty'}
        </button>
        <button onClick={startMedicalCheck} disabled={anyRunning}
          className="px-2.5 py-1.5 text-[11px] font-medium border rounded transition-colors
            text-teal-400 border-teal-500/40 hover:bg-teal-500/10 disabled:opacity-30"
          title="Research health specs (17 categories)">
          {medicalRunning ? 'Running...' : 'Health Specs'}
        </button>
        <button onClick={startLifeSciCheck} disabled={anyRunning}
          className="px-2.5 py-1.5 text-[11px] font-medium border rounded transition-colors
            text-blue-400 border-blue-500/40 hover:bg-blue-500/10 disabled:opacity-30"
          title="Research life sciences / biotech (6 categories)">
          {lifeSciRunning ? 'Running...' : 'Life Sci'}
        </button>
        <button onClick={startFedSourcesCheck} disabled={anyRunning}
          className="px-2.5 py-1.5 text-[11px] font-medium border rounded transition-colors
            text-amber-400 border-amber-500/40 hover:bg-amber-500/10 disabled:opacity-30"
          title="Fetch from Federal Register, CMS, Congress.gov">
          {fedSourcesRunning ? 'Fetching...' : 'Fed Sources'}
        </button>
      </div>
    </div>
  )
}
