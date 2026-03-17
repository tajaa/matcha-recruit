import { Badge, Card } from '../ui'
import type {
  CompanyHandbookProfileInput,
  HandbookMode,
  HandbookSourceType,
  HandbookSectionInput,
  HandbookGuidedSectionSuggestion,
} from '../../types/handbook'

type Props = {
  title: string
  mode: HandbookMode
  sourceType: HandbookSourceType
  industry: string
  states: string[]
  profile: CompanyHandbookProfileInput
  customSections: HandbookSectionInput[]
  suggestedSections: HandbookGuidedSectionSuggestion[]
  fileName?: string | null
}

const BOOL_LABELS: Record<string, string> = {
  remote_workers: 'Remote workers',
  minors: 'Employs minors',
  tipped_employees: 'Tipped employees',
  union_employees: 'Union employees',
  federal_contracts: 'Federal contracts',
  group_health_insurance: 'Group health insurance',
  background_checks: 'Background checks',
  hourly_employees: 'Hourly employees',
  salaried_employees: 'Salaried employees',
  commissioned_employees: 'Commissioned employees',
  tip_pooling: 'Tip pooling',
}

export function HandbookReviewStep({
  title,
  mode,
  sourceType,
  industry,
  states,
  profile,
  customSections,
  suggestedSections,
  fileName,
}: Props) {
  const activeBools = Object.entries(BOOL_LABELS).filter(
    ([key]) => profile[key as keyof CompanyHandbookProfileInput] === true,
  )

  return (
    <div className="space-y-4">
      <Card>
        <h4 className="text-sm font-semibold text-zinc-300 mb-2">Handbook Details</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-zinc-500">Title:</span>{' '}
            <span className="text-zinc-200">{title || '(untitled)'}</span>
          </div>
          <div>
            <span className="text-zinc-500">Mode:</span>{' '}
            <span className="text-zinc-200">{mode === 'single_state' ? 'Single State' : 'Multi-State'}</span>
          </div>
          <div>
            <span className="text-zinc-500">Source:</span>{' '}
            <span className="text-zinc-200">{sourceType === 'template' ? 'Template' : 'Upload'}</span>
          </div>
          <div>
            <span className="text-zinc-500">Industry:</span>{' '}
            <span className="text-zinc-200">{industry || 'general'}</span>
          </div>
        </div>
      </Card>

      <Card>
        <h4 className="text-sm font-semibold text-zinc-300 mb-2">States ({states.length})</h4>
        <div className="flex flex-wrap gap-1.5">
          {states.map((st) => (
            <Badge key={st} variant="neutral">{st}</Badge>
          ))}
          {states.length === 0 && <p className="text-xs text-zinc-600">No states selected</p>}
        </div>
      </Card>

      <Card>
        <h4 className="text-sm font-semibold text-zinc-300 mb-2">Company Profile</h4>
        <div className="text-sm space-y-1">
          <p className="text-zinc-400">
            {profile.legal_name}{profile.dba ? ` (DBA: ${profile.dba})` : ''}
          </p>
          <p className="text-zinc-400">CEO: {profile.ceo_or_president}</p>
          {profile.headcount && <p className="text-zinc-400">Headcount: {profile.headcount}</p>}
        </div>
        {activeBools.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {activeBools.map(([, label]) => (
              <Badge key={label} variant="success">{label}</Badge>
            ))}
          </div>
        )}
      </Card>

      {sourceType === 'upload' && fileName && (
        <Card>
          <h4 className="text-sm font-semibold text-zinc-300 mb-2">Uploaded File</h4>
          <p className="text-sm text-zinc-400">{fileName}</p>
        </Card>
      )}

      {sourceType === 'template' && (suggestedSections.length > 0 || customSections.length > 0) && (
        <Card>
          <h4 className="text-sm font-semibold text-zinc-300 mb-2">
            Sections ({suggestedSections.length + customSections.length})
          </h4>
          <div className="space-y-1">
            {suggestedSections.map((s) => (
              <div key={s.section_key} className="flex items-center gap-2 text-xs">
                <Badge variant="neutral">{s.section_type}</Badge>
                <span className="text-zinc-300">{s.title}</span>
              </div>
            ))}
            {customSections.map((s) => (
              <div key={s.section_key} className="flex items-center gap-2 text-xs">
                <Badge variant="success">custom</Badge>
                <span className="text-zinc-300">{s.title || '(untitled)'}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
