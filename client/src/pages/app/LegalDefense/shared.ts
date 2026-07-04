import type { LucideIcon } from 'lucide-react'
import {
  Accessibility, BookOpenCheck, FileSignature, Gavel, GraduationCap, HardHat, Users,
} from 'lucide-react'
import type { MatterType } from '../../../api/legalDefense'

export const MATTER_TYPES: { value: MatterType; label: string }[] = [
  { value: 'class_action', label: 'Class action' },
  { value: 'single_plaintiff', label: 'Single-plaintiff suit' },
  { value: 'eeoc_charge', label: 'EEOC / agency charge' },
  { value: 'subpoena', label: 'Subpoena' },
  { value: 'audit', label: 'Regulator audit' },
  { value: 'other', label: 'Other' },
]
export const typeLabel = (t: MatterType) => MATTER_TYPES.find((m) => m.value === t)?.label ?? t

export const DISCLAIMER =
  'This organizes your own records to help your attorney — it is an evidence-assembly aid, not legal advice, and renders no legal conclusion. Have counsel review before relying on it.'

export const STARTERS = [
  'We were served a class action alleging employees worked off the clock in 2025.',
  'What do our records show about overtime or wage disputes?',
  'Summarize all discipline and ER cases related to timekeeping.',
]

/** Label voice — docket micro-caption. */
export { LABEL } from '../../../components/ui'

export type CidInfo = { ref: string | null; label: string; summary: string }

/** The 7 evidence subsystems the backend can gather from
 *  (server/app/matcha/services/legal_defense.py:_SOURCES) — strip order. */
export const SOURCE_META: { key: string; label: string; icon: LucideIcon }[] = [
  { key: 'incidents', label: 'IR / OSHA', icon: HardHat },
  { key: 'er_cases', label: 'ER cases', icon: Users },
  { key: 'compliance', label: 'Compliance', icon: BookOpenCheck },
  { key: 'discipline', label: 'Discipline', icon: Gavel },
  { key: 'training', label: 'Training', icon: GraduationCap },
  { key: 'policy_ack', label: 'Policy acks', icon: FileSignature },
  { key: 'accommodations', label: 'Accommodations', icon: Accessibility },
]

export function fmtWhen(iso: string): string {
  const d = new Date(iso)
  const t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return d.toDateString() === new Date().toDateString()
    ? t
    : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${t}`
}

/** Humanize a raw db enum/snake_case value for display — 'in_review' ->
 *  'In Review'. Mirrors legal_defense.py's `_hum()`. */
export function hum(s: string | null | undefined): string {
  if (!s) return ''
  return String(s).replace(/_/g, ' ').replace(/-/g, ' ').trim()
    .replace(/\w\S*/g, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase())
}

export function fmtSize(n: number | null | undefined): string | null {
  if (!n) return null
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}
