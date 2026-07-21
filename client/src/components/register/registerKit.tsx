import { FileDown, Loader2 } from 'lucide-react'

// Shared primitives for the register/tracker page family (risk assets, compliance
// trackers, limit-adequacy). Extracted verbatim from the pages so the rendered DOM
// stays byte-identical — do not restyle.

// Canonical value from pages/app/compliance/WorkforceCompliance.tsx.
export const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'

// Today as an ISO yyyy-mm-dd string.
export const today = () => new Date().toISOString().slice(0, 10)

// The register loading gate.
export function RegisterSpinner() {
  return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
}

// The FileDown-with-spinner export button (common shape, with shrink-0).
export function DownloadButton({ onClick, downloading, label = 'PDF' }: { onClick: () => void; downloading: boolean; label?: string }) {
  return (
    <button onClick={onClick} disabled={downloading} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50 shrink-0">
      {downloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}{' ' + label}
    </button>
  )
}
