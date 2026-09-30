import { useRef, useState, type DragEvent } from 'react'
import { Upload } from 'lucide-react'
import { DRIVE_ACCEPT } from './driveTree'

interface Props {
  onFiles: (files: File[]) => void
  busy?: boolean
  /** Drop-box folders get the large target — it's the only thing there. */
  prominent?: boolean
}

export default function DriveUploadDropzone({ onFiles, busy, prominent }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    const files = Array.from(e.dataTransfer.files ?? [])
    if (files.length) onFiles(files)
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`rounded-xl border border-dashed text-center transition-colors ${over ? 'border-w-accent bg-w-accent/10' : 'border-w-line'} ${prominent ? 'px-6 py-12' : 'px-4 py-4'}`}
    >
      <Upload size={prominent ? 22 : 16} className="mx-auto mb-1.5 text-w-faint" />
      <p className="text-sm text-w-dim">
        Drop files here or{' '}
        <button
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
          className="font-medium text-w-accent hover:underline disabled:opacity-50"
        >
          choose files
        </button>
      </p>
      <p className="mt-0.5 text-[11px] text-w-faint">PDF, Word, text, CSV, Excel or images, up to 25 MB each.</p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={DRIVE_ACCEPT}
        data-testid="drive-file-input"
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (files.length) onFiles(files)
        }}
      />
    </div>
  )
}
