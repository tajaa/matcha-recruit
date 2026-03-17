import { Input, Toggle } from '../ui'
import type { CompanyHandbookProfileInput } from '../../types/handbook'

const BOOL_FLAGS: { key: keyof CompanyHandbookProfileInput; label: string }[] = [
  { key: 'remote_workers', label: 'Remote workers' },
  { key: 'minors', label: 'Employs minors' },
  { key: 'tipped_employees', label: 'Tipped employees' },
  { key: 'union_employees', label: 'Union employees' },
  { key: 'federal_contracts', label: 'Federal contracts' },
  { key: 'group_health_insurance', label: 'Group health insurance' },
  { key: 'background_checks', label: 'Background checks' },
  { key: 'hourly_employees', label: 'Hourly employees' },
  { key: 'salaried_employees', label: 'Salaried employees' },
  { key: 'commissioned_employees', label: 'Commissioned employees' },
  { key: 'tip_pooling', label: 'Tip pooling' },
]

type Props = {
  profile: CompanyHandbookProfileInput
  onChange: (profile: CompanyHandbookProfileInput) => void
}

export function HandbookProfileForm({ profile, onChange }: Props) {
  function set<K extends keyof CompanyHandbookProfileInput>(key: K, value: CompanyHandbookProfileInput[K]) {
    onChange({ ...profile, [key]: value })
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Input
          id="hb-legal-name"
          label="Legal Name"
          required
          value={profile.legal_name}
          onChange={(e) => set('legal_name', e.target.value)}
          placeholder="Company legal name"
        />
        <Input
          id="hb-dba"
          label="DBA (optional)"
          value={profile.dba ?? ''}
          onChange={(e) => set('dba', e.target.value || null)}
          placeholder="Doing business as"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Input
          id="hb-ceo"
          label="CEO / President"
          required
          value={profile.ceo_or_president}
          onChange={(e) => set('ceo_or_president', e.target.value)}
          placeholder="Name"
        />
        <Input
          id="hb-headcount"
          label="Headcount (optional)"
          type="number"
          value={profile.headcount ?? ''}
          onChange={(e) => set('headcount', e.target.value ? parseInt(e.target.value) : null)}
          placeholder="Number of employees"
        />
      </div>
      <div>
        <p className="text-sm font-medium text-zinc-300 mb-3">Workforce Profile</p>
        <div className="grid grid-cols-2 gap-y-2.5 gap-x-6">
          {BOOL_FLAGS.map(({ key, label }) => (
            <label key={key} className="flex items-center justify-between gap-2">
              <span className="text-sm text-zinc-400">{label}</span>
              <Toggle
                checked={profile[key] as boolean}
                onChange={(v) => set(key, v as never)}
              />
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
