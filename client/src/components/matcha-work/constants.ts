import { Database, Shield, Stethoscope, HeartPulse, Scale, Gauge, GraduationCap, LifeBuoy } from 'lucide-react'
import type { MWModeKey } from '../../types/matcha-work'

// Grounding-mode registry — mirrors the backend
// (server/app/matcha/services/matcha_work_modes.py THREAD_MODES).
// Consumed by the thread header toggles (MatchaWorkThread) and the
// thread-list badges (MatchaWorkList). Adding a mode: backend registry entry
// + mw_threads column + MWThread type field + one row here.
export const THREAD_MODE_TOGGLES: {
  key: MWModeKey
  label: string
  icon: typeof Database
  onClass: string
  badgeClass: string
  tipOn: string
  tipOff: string
  // Paid flag the mode's data lives behind — mirrors ThreadMode.required_feature
  // in the backend registry, which 403s the toggle. Undefined = ungated.
  feature?: string
}[] = [
  { key: 'node', label: 'Node', icon: Database, onClass: 'bg-purple-600 text-white hover:bg-purple-500', badgeClass: 'bg-purple-700 text-purple-200', tipOn: 'Node ON — query employees, policies, handbooks', tipOff: 'Node OFF' },
  { key: 'compliance', label: 'Compliance', icon: Shield, onClass: 'bg-cyan-600 text-white hover:bg-cyan-500', badgeClass: 'bg-cyan-700 text-cyan-200', tipOn: 'Compliance ON — jurisdiction requirements injected', tipOff: 'Compliance OFF' },
  { key: 'payer', label: 'Payer', icon: Stethoscope, onClass: 'bg-emerald-600 text-white hover:bg-emerald-500', badgeClass: 'bg-emerald-700 text-emerald-200', tipOn: 'Payer ON — Medicare NCD/LCD search active', tipOff: 'Payer OFF' },
  { key: 'benefits', label: 'Benefits', icon: HeartPulse, onClass: 'bg-rose-600 text-white hover:bg-rose-500', badgeClass: 'bg-rose-700 text-rose-200', tipOn: 'Benefits ON — roster, eligibility gaps, renewal risk', tipOff: 'Benefits OFF', feature: 'benefits_admin' },
  { key: 'legal', label: 'Legal', icon: Scale, onClass: 'bg-amber-600 text-white hover:bg-amber-500', badgeClass: 'bg-amber-700 text-amber-200', tipOn: 'Legal ON — legal matters register injected', tipOff: 'Legal OFF', feature: 'legal_defense' },
  { key: 'risk', label: 'Risk', icon: Gauge, onClass: 'bg-indigo-600 text-white hover:bg-indigo-500', badgeClass: 'bg-indigo-700 text-indigo-200', tipOn: 'Risk ON — risk index, coverage & contract verdicts', tipOff: 'Risk OFF', feature: 'risk_profile' },
  { key: 'training', label: 'Training', icon: GraduationCap, onClass: 'bg-teal-600 text-white hover:bg-teal-500', badgeClass: 'bg-teal-700 text-teal-200', tipOn: 'Training ON — programs, credentials & OSHA currency', tipOff: 'Training OFF', feature: 'training' },
  { key: 'hr_pilot', label: 'HR Pilot', icon: LifeBuoy, onClass: 'bg-fuchsia-600 text-white hover:bg-fuchsia-500', badgeClass: 'bg-fuchsia-700 text-fuchsia-200', tipOn: 'HR Pilot ON — grounded in your handbook & policies; sensitive topics route to corporate HR', tipOff: 'HR Pilot OFF', feature: 'hr_pilot' },
]

export const MODEL_OPTIONS = [
  { id: 'gemini-3.1-flash-lite', label: 'Flash Lite 3.1' },
  { id: 'gemini-3-flash-preview', label: 'Flash 3.0' },
  { id: 'gemini-3.1-pro-preview', label: 'Pro 3.1' },
] as const

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}
