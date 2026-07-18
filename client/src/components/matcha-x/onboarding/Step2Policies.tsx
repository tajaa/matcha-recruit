import { useRef, useState } from 'react'
import { CheckCircle2, FileText, Loader2, Upload } from 'lucide-react'
import { matchaXOnboarding } from '../../../api/billing/matchaXOnboarding'

// Skippable. On a successful PDF upload we hand the storage URL up to the wizard
// (`onUploaded`) so the build finale can overlay handbook coverage. PDF only —
// the coverage grader reads PDFs.
export default function Step2Policies({
  onDone,
  onUploaded,
  uploadedName,
}: {
  onDone: () => void
  onUploaded: (url: string | null, filename: string | null) => void
  uploadedName: string | null
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please upload a PDF — the coverage overlay reads PDFs only.')
      if (fileRef.current) fileRef.current.value = ''
      return
    }
    setUploading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await matchaXOnboarding.uploadHandbook(fd)
      onUploaded(res.url, res.filename || file.name)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload handbook')
      onUploaded(null, null)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Bring your current policies</h2>
        <p className="text-sm text-zinc-400">
          Drop in your employee handbook (PDF). During the build we'll grade it against
          each state's law live — showing exactly what you already cover and where the gaps are.
        </p>
      </div>

      <label
        className={
          'flex flex-col items-center justify-center gap-3 border-2 border-dashed rounded-xl py-10 cursor-pointer transition-colors ' +
          (uploadedName
            ? 'border-emerald-800 bg-emerald-950/20'
            : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700')
        }
      >
        {uploading ? (
          <Loader2 className="w-7 h-7 text-zinc-400 animate-spin" />
        ) : uploadedName ? (
          <CheckCircle2 className="w-7 h-7 text-emerald-400" />
        ) : (
          <Upload className="w-7 h-7 text-zinc-500" />
        )}
        <div className="text-center">
          {uploadedName ? (
            <>
              <div className="text-sm text-emerald-300 font-medium flex items-center gap-1.5 justify-center">
                <FileText className="w-4 h-4" /> {uploadedName}
              </div>
              <div className="text-xs text-zinc-500 mt-0.5">Click to replace</div>
            </>
          ) : (
            <>
              <div className="text-sm text-zinc-300 font-medium">
                {uploading ? 'Uploading…' : 'Drop your handbook here, or click to browse'}
              </div>
              <div className="text-xs text-zinc-500 mt-0.5">PDF up to ~50 MB</div>
            </>
          )}
        </div>
        <input ref={fileRef} type="file" accept=".pdf,application/pdf" onChange={handleFile} className="hidden" />
      </label>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onDone}
          className="bg-emerald-700 hover:bg-emerald-600 text-white font-medium px-5 py-2 rounded transition-colors"
        >
          Continue
        </button>
        <button
          type="button"
          onClick={() => { onUploaded(null, null); onDone() }}
          className="text-sm text-zinc-400 hover:text-zinc-200 underline"
        >
          Skip — I don't have one handy
        </button>
      </div>
    </div>
  )
}
