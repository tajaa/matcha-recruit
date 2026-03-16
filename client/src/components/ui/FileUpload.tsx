import { useRef, useState, type ReactNode, type DragEvent } from 'react'

type FileUploadProps = {
  onFiles: (files: File[]) => void
  accept?: string
  multiple?: boolean
  maxSizeMB?: number
  disabled?: boolean
  children?: ReactNode
}

export function FileUpload({
  onFiles,
  accept,
  multiple = false,
  maxSizeMB = 50,
  disabled = false,
  children,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState('')

  function validate(fileList: FileList) {
    const files = Array.from(fileList)
    const maxBytes = maxSizeMB * 1024 * 1024
    const oversized = files.filter((f) => f.size > maxBytes)
    if (oversized.length) {
      setError(`${oversized[0].name} exceeds ${maxSizeMB}MB limit`)
      return
    }
    setError('')
    onFiles(files)
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault()
    setDragOver(false)
    if (disabled || !e.dataTransfer.files.length) return
    validate(e.dataTransfer.files)
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault()
    if (!disabled) setDragOver(true)
  }

  return (
    <div>
      <div
        onClick={() => !disabled && inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragOver(false)}
        className={`rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm cursor-pointer transition-colors ${
          disabled
            ? 'border-zinc-800 text-zinc-600 cursor-not-allowed'
            : dragOver
              ? 'border-emerald-500 bg-emerald-500/5 text-emerald-400'
              : 'border-zinc-700 text-zinc-400 hover:border-zinc-600'
        }`}
      >
        {children ?? (
          <p>Drop files here or <span className="text-emerald-400 underline">browse</span></p>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(e) => {
          if (e.target.files?.length) validate(e.target.files)
          e.target.value = ''
        }}
      />
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
    </div>
  )
}
