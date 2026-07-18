import { AlertTriangle, Download, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button, Modal } from '../../ui'
import { EXPORT_DISCLAIMER } from './constants'

interface ExportAttestModalProps {
  attestExport: { label: string; preview: ReactNode; run: () => Promise<void> } | null
  setAttestExport: (v: null) => void
  attestChecked: boolean
  setAttestChecked: (v: boolean) => void
  attestBusy: boolean
  confirmExport: () => void
}

// Pre-export reviewer attestation — absolves the tool, records the human
// sign-off (audit). No OSHA file downloads until this is confirmed.
export function ExportAttestModal({
  attestExport,
  setAttestExport,
  attestChecked,
  setAttestChecked,
  attestBusy,
  confirmExport,
}: ExportAttestModalProps) {
  return (
    <Modal
      open={attestExport !== null}
      onClose={() => { if (!attestBusy) setAttestExport(null) }}
      title="Review &amp; confirm export"
      width="xl"
    >
      <div className="space-y-4">
        {attestExport && (
          <div className="flex items-start gap-2 text-amber-300">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span className="text-[13px] font-medium">{attestExport.label}</span>
          </div>
        )}
        {/* Exactly what will be exported — review before signing off. */}
        <div className="rounded-xl border border-white/10 bg-zinc-950/50 p-3 max-h-[45vh] overflow-auto">
          {attestExport?.preview}
        </div>
        <p className="text-[13px] text-zinc-300 leading-relaxed">{EXPORT_DISCLAIMER}</p>
        <label className="flex items-start gap-2.5 cursor-pointer">
          <input
            type="checkbox"
            checked={attestChecked}
            onChange={(e) => setAttestChecked(e.target.checked)}
            className="mt-0.5 accent-emerald-500"
          />
          <span className="text-[13px] text-zinc-200">
            I have reviewed this data for accuracy and accept responsibility for the exported records.
          </span>
        </label>
        <div className="flex justify-end gap-2 pt-1">
          <Button size="sm" variant="ghost" onClick={() => setAttestExport(null)} disabled={attestBusy}>
            Cancel
          </Button>
          <Button size="sm" onClick={confirmExport} disabled={!attestChecked || attestBusy}>
            {attestBusy ? <Loader2 size={12} className="mr-1.5 animate-spin" /> : <Download size={12} className="mr-1.5" />}
            Export
          </Button>
        </div>
      </div>
    </Modal>
  )
}
