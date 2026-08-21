// Shared types + styling for the IR create wizard package. Split out of the
// original flat IRCreateIncidentModal.tsx so index.tsx / WizardStep.tsx /
// ReviewStep.tsx / EntryOptions.tsx / ChatThread.tsx can all reference the
// same field chrome + form shape without duplicating it.

export type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

// Intake stays strictly factual — reporter, when, where, what, who.
// OSHA recordability + Privacy Case are decided afterward in the IR Copilot
// (only recordable incidents reach a log), so no sensitive-case fields here.
export const EMPTY_FORM = {
  reported_by_name: '',
  date_text: '',
  location_id: '',
  description: '',
  involved: [] as string[],
  involved_employee_ids: [] as string[],
}
export type IncidentForm = typeof EMPTY_FORM

export function locationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

export function fmtElapsed(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// Shared field chrome — matches the /app micro-label + control look (see IRDetail
// + the Select primitive) so the modal reads as one cohesive surface.
export const LABEL = 'block text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5'
export const FIELD =
  'w-full rounded-lg border border-white/[0.08] bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none hover:border-white/15 focus:border-white/25 focus:ring-1 focus:ring-white/10 transition-colors'

// A prefill merge shared by both voice dictation and AI chat completion —
// only overwrite a field when the source has a non-empty value, so a partial
// AI result never blanks something the user already typed.
export function applyPrefillToForm(
  form: IncidentForm,
  prefill: {
    reported_by_name?: string | null
    occurred_at_text?: string | null
    location_id?: string | null
    description?: string | null
    witnesses?: { name: string }[]
  },
  validLocationIds: Set<string>,
): IncidentForm {
  const loc = prefill.location_id && validLocationIds.has(prefill.location_id) ? prefill.location_id : null
  return {
    ...form,
    description: prefill.description ?? form.description,
    reported_by_name: prefill.reported_by_name ?? form.reported_by_name,
    date_text: prefill.occurred_at_text ?? form.date_text,
    location_id: loc ?? form.location_id,
    involved: prefill.witnesses?.length
      ? Array.from(new Set([...form.involved, ...prefill.witnesses.map((w) => w.name)]))
      : form.involved,
  }
}
