import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle, Building2, ClipboardCheck, FileText, Gauge, HardHat, Hash,
  MapPin, Scale, ShieldCheck, TrendingUp, Warehouse,
} from 'lucide-react'
import type { ContextPreview, CorpusRecord, DocStatus, DocType } from '../../../api/brokerPilot'

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

/** The evidence subsystems Broker Pilot grounds on. The backend corpus is three
 *  flat sources (`platform` / `documents` / `doc_figures`), but every platform
 *  record's cid carries a subsystem prefix — `platform:wc`,
 *  `platform:lossdev.wc.PY2024`, `platform:epl.harassment`, `platform:property`
 *  — so we split those into their own systems for the strip + evidence panel,
 *  mirroring Legal Pilot's per-source view. Order = strip order. */
export const SOURCE_META: { key: string; label: string; icon: LucideIcon }[] = [
  { key: 'profile', label: 'Profile', icon: Building2 },
  { key: 'wc', label: "Workers' Comp", icon: HardHat },
  { key: 'lossdev', label: 'Loss dev', icon: TrendingUp },
  { key: 'epl', label: 'EPL', icon: ShieldCheck },
  { key: 'property', label: 'Property', icon: Warehouse },
  { key: 'venue', label: 'Venue', icon: MapPin },
  { key: 'limits', label: 'Limits', icon: Scale },
  { key: 'controls', label: 'Controls', icon: ClipboardCheck },
  { key: 'exclusions', label: 'Exclusions', icon: AlertTriangle },
  { key: 'readiness', label: 'Readiness', icon: Gauge },
  { key: 'documents', label: 'Documents', icon: FileText },
  { key: 'doc_figures', label: 'Doc figures', icon: Hash },
]

/** Fuller labels for the evidence-panel accordion rows. */
export const SYSTEM_LABEL: Record<string, string> = {
  profile: 'Client profile',
  wc: "Workers' Comp (TRIR / EMR)",
  lossdev: 'Loss development',
  epl: 'EPL readiness',
  property: 'Property / SOV',
  venue: 'Venue exposure',
  limits: 'Limit adequacy',
  controls: 'Controls evidence',
  exclusions: 'Emerging exclusions',
  readiness: 'Submission readiness',
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

export const STARTERS = [
  'Give me an underwriting read on the WC reserve development and biggest EPL and catastrophe exposures.',
  'Summarize what the uploaded documents show and how it squares with the platform data on file.',
  'Compare the quoted premium against the loss history — is the pricing supported?',
  'Where is the data thin or low-confidence, and what will an underwriter ask for next?',
]

export const DISCLAIMER =
  'Analysis is grounded only in the uploaded documents and platform records on file. Verify all figures against actual policy forms before relying on them.'
