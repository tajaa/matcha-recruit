import { Button, Select, Badge, Input } from '../ui'
import type {
  HandbookGuidedDraftResponse,
  HandbookGuidedSectionSuggestion,
} from '../../types/handbook'

const INDUSTRIES = [
  { value: 'general', label: 'General' },
  { value: 'tech', label: 'Technology' },
  { value: 'hospitality', label: 'Hospitality' },
  { value: 'retail', label: 'Retail' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'healthcare', label: 'Healthcare' },
]

type Props = {
  industry: string
  onIndustryChange: (v: string) => void
  guidedResult: HandbookGuidedDraftResponse | null
  guidedAnswers: Record<string, string>
  onAnswerChange: (id: string, value: string) => void
  onBuildPolicyPack: () => Promise<void>
  building: boolean
  suggestedSections: HandbookGuidedSectionSuggestion[]
}

export function HandbookPolicyPack({
  industry,
  onIndustryChange,
  guidedResult,
  guidedAnswers,
  onAnswerChange,
  onBuildPolicyPack,
  building,
  suggestedSections,
}: Props) {
  return (
    <div className="space-y-4">
      <Select
        id="hb-industry"
        label="Industry"
        value={industry}
        onChange={(e) => onIndustryChange(e.target.value)}
        options={INDUSTRIES}
      />

      <div className="flex items-center gap-3">
        <Button size="sm" onClick={onBuildPolicyPack} disabled={building}>
          {building ? 'Building...' : guidedResult ? 'Rebuild Policy Pack' : 'Build Policy Pack'}
        </Button>
        {INDUSTRIES.find((i) => i.value === industry) && (
          <Badge variant="neutral">{INDUSTRIES.find((i) => i.value === industry)!.label} playbook</Badge>
        )}
      </div>

      {guidedResult && (
        <div className="space-y-3">
          <p className="text-sm text-zinc-300">{guidedResult.summary}</p>

          {guidedResult.questions.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-zinc-400">Follow-up Questions</p>
              {guidedResult.questions.map((q) => (
                <Input
                  key={q.id}
                  id={`guided-${q.id}`}
                  label={q.question}
                  required={q.required}
                  placeholder={q.placeholder ?? ''}
                  value={guidedAnswers[q.id] ?? ''}
                  onChange={(e) => onAnswerChange(q.id, e.target.value)}
                />
              ))}
            </div>
          )}

          {suggestedSections.length > 0 && (
            <div>
              <p className="text-xs font-medium text-zinc-400 mb-1.5">
                Suggested Sections ({suggestedSections.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {suggestedSections.map((s) => (
                  <Badge key={s.section_key} variant="neutral">{s.title}</Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
