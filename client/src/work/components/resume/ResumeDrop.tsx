import { useRef, useState } from 'react'
import { FileUp, Loader2 } from 'lucide-react'
import { RESUME_ACCEPT } from '../../hooks/useMyResume'

/** Drop a résumé here, or pick one. `onFile` uploads it; while it runs the
 *  zone says so. */
export default function ResumeDrop({ onFile, busy, label = 'Drop your résumé here', compact = false }: {
  onFile: (file: File) => void
  busy: boolean
  label?: string
  compact?: boolean
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  function take(files: FileList | null) {
    const file = files?.[0]
    if (file) onFile(file)
    if (input.current) input.current.value = ''
  }
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy) take(e.dataTransfer.files) }}
      className={`flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed text-center transition-colors ${
        over ? 'border-w-accent bg-w-accent/5' : 'border-w-line'} ${compact ? 'px-3 py-3' : 'px-6 py-8'}`}
    >
      {busy ? <Loader2 size={compact ? 16 : 22} className="animate-spin text-w-dim" /> : <FileUp size={compact ? 16 : 22} className="text-w-faint" />}
      <p className="text-xs font-medium text-w-text">{busy ? 'Reading your résumé…' : label}</p>
      {!busy && (
        <>
          <p className="text-[10px] text-w-dim">PDF, Word or text, up to 10 MB</p>
          <input ref={input} type="file" accept={RESUME_ACCEPT} className="hidden" aria-label="Choose a résumé file"
            onChange={(e) => take(e.target.files)} />
          <button type="button" onClick={() => input.current?.click()}
            className="rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2">
            Choose a file…
          </button>
        </>
      )}
    </div>
  )
}
