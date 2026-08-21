// Wizard step config — one question per screen, conversational order (what
// happened first, matching the AI chat's opening question) rather than the
// old flat form's name-first layout.

export type WizardFieldKey = 'description' | 'date_text' | 'location_id' | 'reported_by_name' | 'involved'
export type WizardStepKey = WizardFieldKey | 'review'

export type WizardStepConfig = {
  key: WizardFieldKey
  question: string
  required: boolean
}

export const WIZARD_STEPS: WizardStepConfig[] = [
  { key: 'description', question: 'What happened?', required: true },
  { key: 'date_text', question: 'When did this happen?', required: true },
  { key: 'location_id', question: 'Where did this happen?', required: true },
  { key: 'reported_by_name', question: 'Your name', required: true },
  { key: 'involved', question: 'Anyone else involved, or who saw it?', required: false },
]

export function nextStepKey(current: WizardStepKey, steps: WizardStepConfig[]): WizardStepKey {
  const idx = steps.findIndex((s) => s.key === current)
  if (idx === -1 || idx === steps.length - 1) return 'review'
  return steps[idx + 1].key
}

export function prevStepKey(current: WizardStepKey, steps: WizardStepConfig[]): WizardStepKey {
  if (current === 'review') return steps[steps.length - 1].key
  const idx = steps.findIndex((s) => s.key === current)
  return idx <= 0 ? steps[0].key : steps[idx - 1].key
}
