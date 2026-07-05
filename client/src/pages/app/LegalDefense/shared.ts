import type { LucideIcon } from 'lucide-react'
import {
  Accessibility, Bell, BookMarked, BookOpenCheck, FileSignature, Gavel, GraduationCap,
  HardHat, Landmark, ScrollText, Users,
} from 'lucide-react'
import type { Matter, MatterType } from '../../../api/legalDefense'

export const MATTER_TYPES: { value: MatterType; label: string }[] = [
  { value: 'class_action', label: 'Class action' },
  { value: 'single_plaintiff', label: 'Single-plaintiff suit' },
  { value: 'eeoc_charge', label: 'EEOC / agency charge' },
  { value: 'subpoena', label: 'Subpoena' },
  { value: 'audit', label: 'Regulator audit' },
  { value: 'other', label: 'Other' },
]
export const typeLabel = (t: MatterType) => MATTER_TYPES.find((m) => m.value === t)?.label ?? t

/** First-turn recap synthesized from the intake form so the user never
 *  re-types what they just entered. Null when there's nothing to seed. */
export function seedRecap(m: Matter): string | null {
  const allegation = m.allegation?.trim()
  const context = m.defense_theory?.trim()
  if (!allegation && !context) return null

  const lines: string[] = []
  if (allegation) lines.push(`What's being claimed: ${allegation}`)
  if (context) lines.push(`Factual context: ${context}`)
  if (m.evidence_start && m.evidence_end) lines.push(`Timeframe: ${m.evidence_start} – ${m.evidence_end}`)
  else if (m.evidence_start) lines.push(`Timeframe: from ${m.evidence_start}`)
  else if (m.evidence_end) lines.push(`Timeframe: through ${m.evidence_end}`)
  lines.push('Map the records to this claim and flag what counsel should look at.')
  return lines.join('\n')
}

export const DISCLAIMER =
  'This organizes your own records to help your attorney — it is an evidence-assembly aid, not legal advice, and renders no legal conclusion. Have counsel review before relying on it.'

/** Starter prompts are the soft-mode surface (LEGAL_PILOT_ROADMAP.md design
 *  decision — no chat modes): shaped by matter type, zero mode state. */
const STARTER_CLOSER = 'What do the records NOT establish that counsel will ask about?'
const STARTERS_BY_TYPE: Record<MatterType, string[]> = {
  class_action: [
    'What do our records show about overtime, breaks, or wage disputes in the window?',
    'Summarize all discipline and ER cases related to timekeeping or pay.',
  ],
  single_plaintiff: [
    'Pull everything involving the claimant — incidents, ER cases, discipline, acknowledgments.',
    'What does the discipline trail show, and was our own process followed?',
  ],
  eeoc_charge: [
    'What documentation exists around the complaints and our responses?',
    'Show training completions and policy acknowledgments relevant to this charge.',
  ],
  subpoena: [
    'Inventory what we hold that matches the subpoena scope and window.',
    'Which records have supporting documents attached, and which are summary-only?',
  ],
  audit: [
    'Summarize our compliance posture and monitoring history for the window.',
    'Show what we tracked, what alerts fired, and how they were resolved.',
  ],
  other: [
    'Organize the records most relevant to this matter and flag anything unusual.',
    'Summarize incidents, ER cases, and discipline in the evidence window.',
  ],
}
export function startersFor(t: MatterType): string[] {
  return [...(STARTERS_BY_TYPE[t] ?? STARTERS_BY_TYPE.other), STARTER_CLOSER]
}

/** Label voice — docket micro-caption. */
export { LABEL } from '../../../components/ui'

export type CidInfo = { ref: string | null; label: string; summary: string; when?: string }

/** Fallback display names for a cid's "<kind>:" prefix, used when a cited
 *  record isn't in the evidence preview (e.g. it fell outside a source cap). */
export const CID_KIND_LABEL: Record<string, string> = {
  incident: 'Incident',
  er_case: 'ER case',
  compliance_req: 'Compliance',
  discipline: 'Discipline',
  training: 'Training',
  policy_ack: 'Policy ack',
  accommodation: 'Accommodation',
  law: 'Governing law',
  bill: 'Pending bill',
  case: 'Case law',
  compliance_alert: 'Compliance alert',
}

/** The evidence subsystems the backend can gather from
 *  (server/app/matcha/services/legal_defense.py:_SOURCES) — strip order. */
export const SOURCE_META: { key: string; label: string; icon: LucideIcon }[] = [
  { key: 'incidents', label: 'IR / OSHA', icon: HardHat },
  { key: 'er_cases', label: 'ER cases', icon: Users },
  { key: 'compliance', label: 'Compliance', icon: BookOpenCheck },
  { key: 'compliance_alerts', label: 'Compliance alerts', icon: Bell },
  { key: 'discipline', label: 'Discipline', icon: Gavel },
  { key: 'training', label: 'Training', icon: GraduationCap },
  { key: 'policy_ack', label: 'Policy acks', icon: FileSignature },
  { key: 'accommodations', label: 'Accommodations', icon: Accessibility },
  { key: 'law', label: 'Governing law', icon: Landmark },
  { key: 'legislation', label: 'Pending legislation', icon: ScrollText },
  { key: 'case_law', label: 'Case law', icon: BookMarked },
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
