import { Button, Modal, Input } from '../../../../components/ui'
import type { ApproveResult } from '../types'

// Codify modal — mint the authority citation for a live requirement, in
// place. Walks the approved rows one after another.
export function CodifyModal({
  codifyRow, setCodifyRow, codifyForm, setCodifyForm, codifyBusy, codifyError,
  submitCodify, nextUncodified, openCodify,
}: {
  codifyRow: ApproveResult | null
  setCodifyRow: (row: ApproveResult | null) => void
  codifyForm: { citation: string; heading: string; source_url: string }
  setCodifyForm: (form: { citation: string; heading: string; source_url: string }) => void
  codifyBusy: boolean
  codifyError: string | null
  submitCodify: () => void
  nextUncodified: (afterId: string) => ApproveResult | null
  openCodify: (row: ApproveResult) => void
}) {
  return (
    <Modal open={codifyRow !== null} onClose={() => setCodifyRow(null)}
      title="Codify requirement" width="md">
      {codifyRow && (
        <div className="space-y-3">
          <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
            <p className="text-xs font-medium text-zinc-200">{codifyRow.title}</p>
            <p className="mt-0.5 font-mono text-[10px] text-zinc-500">
              {codifyRow.regulation_key || 'no key'} · {(codifyRow.state || '').toUpperCase()}{codifyRow.city ? `, ${codifyRow.city}` : ''}
            </p>
            <p className="mt-1 text-[11px] text-zinc-500">
              Confirm the statute citation for this requirement. It's stored as a
              verified authority citation — the same registry the Authority tab reads.
            </p>
          </div>

          <Input id="codify-citation" label="Statute citation" required
            value={codifyForm.citation}
            onChange={(e) => setCodifyForm({ ...codifyForm, citation: e.target.value })}
            placeholder="e.g. C.R.S. § 12-220-101" />
          <Input id="codify-heading" label="Heading (optional)"
            value={codifyForm.heading}
            onChange={(e) => setCodifyForm({ ...codifyForm, heading: e.target.value })}
            placeholder="short label for the statute" />
          <Input id="codify-source" label="Source URL (optional)"
            value={codifyForm.source_url}
            onChange={(e) => setCodifyForm({ ...codifyForm, source_url: e.target.value })}
            placeholder="https://…" />

          {codifyError && <p className="text-[11px] text-red-400">{codifyError}</p>}

          <div className="flex items-center justify-between gap-2 pt-1">
            <button type="button"
              onClick={() => { const n = nextUncodified(codifyRow.id); if (n) openCodify(n); else setCodifyRow(null) }}
              className="text-xs text-zinc-600 hover:text-zinc-300 transition-colors">Skip</button>
            <Button size="sm" disabled={codifyBusy || !codifyForm.citation.trim()} onClick={submitCodify}>
              {codifyBusy ? 'Codifying…' : 'Codify + next'}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
