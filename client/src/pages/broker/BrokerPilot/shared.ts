import type { DocStatus, DocType } from '../../../api/brokerPilot'

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
  processing: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  ready: 'bg-emerald-950/60 text-emerald-400 border-emerald-900',
  text_only: 'bg-amber-950/60 text-amber-400 border-amber-900',
  failed: 'bg-red-950/60 text-red-400 border-red-900',
}

export const SOURCE_LABEL: Record<string, string> = {
  platform: 'Platform data',
  documents: 'Uploaded documents',
  doc_figures: 'Extracted figures',
}

export function fmtSize(bytes: number | null | undefined): string {
  if (!bytes) return '—'
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
  'Summarize what the uploaded documents show and how it squares with the platform data.',
  'Compare the quoted premium against the loss history — is the pricing supported?',
  'What coverage changes or exclusions appear in these documents that I should flag?',
  'What is missing from this material that an underwriter will ask for?',
]

export const DISCLAIMER =
  'Analysis is grounded in the uploaded documents and platform records only. Verify all figures against actual policy forms before relying on them.'
