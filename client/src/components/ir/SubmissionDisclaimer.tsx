import { FileCheck } from 'lucide-react'

// Mandatory attestation shown on every public magic-link incident reporting form
// (/intake and /report). The act of submitting constitutes the confirmation
// (clickwrap), so the electronic submission stands in for a manual signature —
// this is the reassurance for reporters used to signing a paper form.
export function SubmissionDisclaimer() {
  return (
    <div className="flex items-start gap-2 rounded border border-zinc-800 bg-zinc-900/60 p-3 text-left">
      <FileCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
      <p className="text-xs text-zinc-400">
        By submitting this report, you confirm that the information provided is true and complete to the best of
        your knowledge. This electronic submission carries the same validity as a signed paper form.
      </p>
    </div>
  )
}
