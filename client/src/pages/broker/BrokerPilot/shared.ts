import type { LucideIcon } from 'lucide-react'
import {
  Accessibility, AlertTriangle, Bell, BookOpenCheck, Building2, ClipboardCheck,
  FileSignature, FileText, Gauge, Gavel, GraduationCap, Handshake, HardHat, Hash, MapPin,
  Scale, ShieldCheck, Siren, TrendingUp, Users, Warehouse,
} from 'lucide-react'
import type {
  ContextPreview, CorpusRecord, DocRequirement, DocStatus, DocType, PilotSession,
} from '../../../api/brokerPilot'

/** Label voice — docket micro-caption, shared with the platform primitives. */
export { LABEL } from '../../../components/ui'

export const DOC_TYPE_LABEL: Record<DocType, string> = {
  loss_run: 'Loss run',
  dec_page: 'Dec page',
  quote: 'Quote',
  carrier_letter: 'Carrier letter',
  bordereau: 'Bordereau',
  policy_form: 'Policy form',
  financials: 'Financials',
  contract: 'Contract',
  other: 'Document',
}

export const DOC_STATUS_LABEL: Record<DocStatus, string> = {
  processing: 'Processing…',
  ready: 'Analyzed',
  text_only: 'Text only',
  failed: 'Failed',
}

export const DOC_STATUS_CLASS: Record<DocStatus, string> = {
  processing: 'bg-white/[0.04] text-zinc-400 border-white/[0.08]',
  ready: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  text_only: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  failed: 'bg-red-500/10 text-red-400 border-red-500/20',
}

/** The evidence subsystems Broker Pilot grounds on, in strip order.
 *
 *  Analytics systems come from the flat `platform` source — every platform
 *  record's cid carries a subsystem prefix (`platform:wc`,
 *  `platform:lossdev.wc.PY2024`, `platform:epl.harassment`) that we split on.
 *
 *  Native systems (incidents … accommodations) arrive as their own corpus
 *  sources — the operational records Matcha generates for ON-platform clients.
 *  They stay dark for off-platform clients: that's the visual incentive to
 *  bring the client onto the platform. */
export const SOURCE_META: { key: string; label: string; icon: LucideIcon }[] = [
  { key: 'profile', label: 'Profile', icon: Building2 },
  { key: 'wc', label: "Workers' Comp", icon: HardHat },
  { key: 'lossdev', label: 'Loss dev', icon: TrendingUp },
  { key: 'epl', label: 'EPL', icon: ShieldCheck },
  { key: 'property', label: 'Property', icon: Warehouse },
  { key: 'venue', label: 'Venue', icon: MapPin },
  { key: 'limits', label: 'Limits', icon: Scale },
  { key: 'clauses', label: 'Contract clauses', icon: Handshake },
  { key: 'controls', label: 'Controls', icon: ClipboardCheck },
  { key: 'exclusions', label: 'Exclusions', icon: AlertTriangle },
  { key: 'readiness', label: 'Readiness', icon: Gauge },
  { key: 'incidents', label: 'IR / OSHA', icon: Siren },
  { key: 'er_cases', label: 'ER cases', icon: Users },
  { key: 'compliance', label: 'Compliance', icon: BookOpenCheck },
  { key: 'compliance_alerts', label: 'Alerts', icon: Bell },
  { key: 'discipline', label: 'Discipline', icon: Gavel },
  { key: 'training', label: 'Training', icon: GraduationCap },
  { key: 'policy_ack', label: 'Policy acks', icon: FileSignature },
  { key: 'accommodations', label: 'Accommodations', icon: Accessibility },
  { key: 'documents', label: 'Documents', icon: FileText },
  { key: 'doc_figures', label: 'Doc figures', icon: Hash },
]

/** Systems generated natively by the platform — only on-platform clients have
 *  them; the strip advertises them ("on Matcha") when dark. */
export const NATIVE_KEYS = new Set([
  'incidents', 'er_cases', 'compliance', 'compliance_alerts',
  'discipline', 'training', 'policy_ack', 'accommodations',
])

/** Fuller labels for the evidence-panel accordion rows. */
export const SYSTEM_LABEL: Record<string, string> = {
  profile: 'Client profile',
  wc: "Workers' Comp (TRIR / EMR)",
  lossdev: 'Loss development',
  epl: 'EPL readiness',
  property: 'Property / SOV',
  venue: 'Venue exposure',
  limits: 'Limit adequacy',
  clauses: 'Contract indemnity clauses',
  controls: 'Controls evidence',
  exclusions: 'Emerging exclusions',
  readiness: 'Submission readiness',
  incidents: 'Safety incidents (IR / OSHA)',
  er_cases: 'Employee-relations cases',
  compliance: 'Compliance requirements tracked',
  compliance_alerts: 'Compliance monitoring alerts',
  discipline: 'Progressive discipline',
  training: 'Training completions',
  policy_ack: 'Policy / handbook acknowledgments',
  accommodations: 'Accommodation cases',
  documents: 'Uploaded documents',
  doc_figures: 'Extracted document figures',
}

/** Split the flat corpus into per-subsystem record buckets keyed by SOURCE_META
 *  key. Platform records split on their cid subsystem prefix; documents and
 *  doc_figures pass through whole. */
export function deriveSystems(context: ContextPreview | null): Record<string, CorpusRecord[]> {
  const out: Record<string, CorpusRecord[]> = {}
  if (!context) return out
  for (const [srcKey, source] of Object.entries(context.sources)) {
    if (srcKey === 'platform') {
      for (const r of source.records) {
        const sub = (r.cid.split(':')[1] ?? '').split('.')[0] || 'profile'
        ;(out[sub] ??= []).push(r)
      }
    } else if (source.records.length) {
      out[srcKey] = [...source.records]
    }
  }
  return out
}

/** How a requirement row reads once satisfied — the distinction matters:
 *  "Platform data" means the client's own records already cover it and no upload
 *  is being asked for, which is why a moded session on a well-populated client
 *  never gets prompted at all. */
export function requirementStatus(req: DocRequirement): string {
  if (!req.satisfied) return req.required ? 'Needed' : 'Optional'
  switch (req.satisfied_by) {
    case 'platform': return 'Platform data'
    case 'unclassified': return 'Uploaded (unclassified)'
    default: return 'Uploaded'
  }
}

export function requirementClass(req: DocRequirement): string {
  if (req.satisfied) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
  if (req.required) return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
  return 'bg-white/[0.04] text-zinc-400 border-white/[0.08]'
}

/** The rows that block the chat gate — the frontend mirror of the server's
 *  `missing_required`. The server re-runs it on every turn; this is only for
 *  rendering (what to nag about, whether to auto-prompt). */
export function missingRequired(reqs: DocRequirement[] | undefined | null): DocRequirement[] {
  return (reqs ?? []).filter((r) => r.required && !r.satisfied)
}

export function fmtSize(bytes: number | null | undefined): string | null {
  if (!bytes) return null
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}

/** Default starters for an open-ended session (no mode) + the fallback when a
 *  moded session's template metadata hasn't loaded yet. */
export const STARTERS = [
  'Give me an underwriting read on the WC reserve development and biggest EPL and catastrophe exposures.',
  'Summarize what the uploaded documents show and how it squares with the platform data on file.',
  'Compare the quoted premium against the loss history — is the pricing supported?',
  'Which contract indemnity clauses put this client at risk, and do their limits meet what the contracts require?',
  'Where is the data thin or low-confidence, and what will an underwriter ask for next?',
]

/** Mode-tailored starters for a session, falling back to the defaults. Mirrors
 *  Legal Pilot's `startersFor(matter_type)`. */
export function startersFor(session: PilotSession | null): string[] {
  const s = session?.template?.starters
  return s && s.length ? s : STARTERS
}

export const DISCLAIMER =
  'Analysis is grounded only in the uploaded documents and platform records on file. Verify all figures against actual policy forms before relying on them.'
