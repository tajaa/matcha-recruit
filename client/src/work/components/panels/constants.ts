import { Database, Shield, Stethoscope, HeartPulse, Scale, Gauge, GraduationCap, LifeBuoy, Bot } from 'lucide-react'
import type { MWModeKey } from '../../types'

// Grounding-mode registry — mirrors the backend
// (server/app/matcha/services/matcha_work_modes.py THREAD_MODES).
// Consumed by the thread header toggles (MatchaWorkThread) and the
// thread-list badges (MatchaWorkList). Adding a mode: backend registry entry
// + mw_threads column + MWThread type field + one row here.
export const THREAD_MODE_TOGGLES: {
  key: MWModeKey
  label: string
  icon: typeof Database
  desc: string
  badgeClass: string
  tipOn: string
  tipOff: string
  // Paid flag the mode's data lives behind — mirrors ThreadMode.required_feature
  // in the backend registry, which 403s the toggle. Undefined = ungated.
  feature?: string
}[] = [
  { key: 'node', label: 'Node', icon: Database, desc: 'Query employees, policies, handbooks', badgeClass: 'bg-purple-700 text-purple-200', tipOn: 'Node ON — query employees, policies, handbooks', tipOff: 'Node OFF' },
  { key: 'compliance', label: 'Compliance', icon: Shield, desc: 'Jurisdiction requirements injected', badgeClass: 'bg-cyan-700 text-cyan-200', tipOn: 'Compliance ON — jurisdiction requirements injected', tipOff: 'Compliance OFF' },
  { key: 'payer', label: 'Payer', icon: Stethoscope, desc: 'Medicare NCD/LCD search active', badgeClass: 'bg-emerald-700 text-emerald-200', tipOn: 'Payer ON — Medicare NCD/LCD search active', tipOff: 'Payer OFF' },
  { key: 'benefits', label: 'Benefits', icon: HeartPulse, desc: 'Roster, eligibility gaps, renewal risk', badgeClass: 'bg-rose-700 text-rose-200', tipOn: 'Benefits ON — roster, eligibility gaps, renewal risk', tipOff: 'Benefits OFF', feature: 'benefits_admin' },
  { key: 'legal', label: 'Legal', icon: Scale, desc: 'Legal matters register injected', badgeClass: 'bg-amber-700 text-amber-200', tipOn: 'Legal ON — legal matters register injected', tipOff: 'Legal OFF', feature: 'legal_defense' },
  { key: 'risk', label: 'Risk', icon: Gauge, desc: 'Risk index, coverage & contract verdicts', badgeClass: 'bg-indigo-700 text-indigo-200', tipOn: 'Risk ON — risk index, coverage & contract verdicts', tipOff: 'Risk OFF', feature: 'risk_profile' },
  { key: 'training', label: 'Training', icon: GraduationCap, desc: 'Programs, credentials & OSHA currency', badgeClass: 'bg-teal-700 text-teal-200', tipOn: 'Training ON — programs, credentials & OSHA currency', tipOff: 'Training OFF', feature: 'training' },
  { key: 'hr_pilot', label: 'HR Pilot', icon: LifeBuoy, desc: 'Grounded in your handbook & policies; sensitive topics route to corporate HR', badgeClass: 'bg-fuchsia-700 text-fuchsia-200', tipOn: 'HR Pilot ON — grounded in your handbook & policies; sensitive topics route to corporate HR', tipOff: 'HR Pilot OFF', feature: 'hr_pilot' },
  { key: 'huume', label: 'Huume', icon: Bot, desc: 'Agentic assistant: drafts offers, stages hiring plans, runs Legal & Handbook Pilot from chat', badgeClass: 'bg-orange-700 text-orange-200', tipOn: 'Huume ON — agentic assistant: drafts offers, stages hiring plans, and (when enabled) runs Legal Pilot and Handbook Pilot from chat — waits for your approval before it acts. Handles the whole turn itself, so every other mode below is inert while this is on', tipOff: 'Huume OFF', feature: 'huume' },
]

export type ModelOption = {
  id: string
  label: string
}

/** One row of the server's picker (`entitlements.workspace.chat_models`). */
export type ChatModelRow = { id: string; locked: boolean }

export const DEFAULT_MODEL = 'gemini-3.7-flash'

// Labels only. WHICH rows a person gets, which are locked, and where the
// picker starts are the server's call (`matcha_work_ai._models.picker_models`);
// ids must be in its SUPPORTED_MODELS. Flash Lite shipped as
// 'gemini-3.7-flash-lite', which the server never supported — LEGACY_MODEL_IDS
// maps a stored pick of it, and the server aliases it for older builds.
export const MODEL_OPTIONS: readonly ModelOption[] = [
  { id: 'gemini-3.5-flash-lite', label: 'Flash Lite 3.5' },
  { id: DEFAULT_MODEL, label: 'Flash 3.7' },
  { id: 'claude-haiku-5-5', label: 'Claude Haiku 5.5' },
  { id: 'claude-sonnet-5-5', label: 'Claude Sonnet 5.5' },
]

export const LEGACY_MODEL_IDS: Record<string, string> = {
  'gemini-3.7-flash-lite': 'gemini-3.5-flash-lite',
}

// Until entitlements load: the two Gemini rows every plan has. A Claude row
// that appears and then vanishes is worse than one that appears a moment late.
const UNKNOWN_ROWS: readonly ChatModelRow[] = [
  { id: 'gemini-3.5-flash-lite', locked: false },
  { id: DEFAULT_MODEL, locked: false },
]

/** The menu for this person: the server's unlocked rows, in menu order.
 *  Locked rows are left out here; the web picker has no upsell row. */
export function modelOptionsFor(rows: readonly ChatModelRow[] | null): ModelOption[] {
  const offered = new Set((rows ?? UNKNOWN_ROWS).filter((row) => !row.locked).map((row) => row.id))
  return MODEL_OPTIONS.filter((option) => offered.has(option.id))
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}
