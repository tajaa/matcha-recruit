import { useRef, useState } from 'react'
import { FileText, ImagePlus, Loader2, X } from 'lucide-react'
import { cappeApi } from '../api'

/** URL input + S3 upload button + thumbnail. Used for logos, product images,
 *  post covers (images via /upload) and digital deliverables (files via
 *  /upload-file). */
export default function ImageUpload({
  siteId,
  value,
  onChange,
  placeholder = 'Image URL',
  className = '',
  endpoint = '/upload',
  accept = 'image/*',
  kind = 'image',
}: {
  siteId: string
  value: string
  onChange: (url: string) => void
  placeholder?: string
  className?: string
  endpoint?: string
  accept?: string
  kind?: 'image' | 'file'
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function upload(file: File) {
    setBusy(true)
    setErr(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await cappeApi.upload<{ url: string }>(`/sites/${siteId}${endpoint}`, fd)
      onChange(res.url)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={className}>
      <div className="flex items-center gap-2">
        {kind === 'image' && value ? (
          <img src={value} alt="" className="h-9 w-9 shrink-0 rounded-lg border border-zinc-700 object-cover" />
        ) : (
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${value ? 'border-emerald-600 text-emerald-400' : 'border-dashed border-zinc-700 text-zinc-600'}`}>
            {kind === 'file' ? <FileText className="h-4 w-4" /> : <ImagePlus className="h-4 w-4" />}
          </span>
        )}
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
        />
        {value && (
          <button type="button" onClick={() => onChange('')} className="shrink-0 text-zinc-500 hover:text-red-400" title="Clear">
            <X className="h-4 w-4" />
          </button>
        )}
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-zinc-700 px-2.5 py-2 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImagePlus className="h-3.5 w-3.5" />}
          Upload
        </button>
      </div>
      {err && <p className="mt-1 text-xs text-red-400">{err}</p>}
      <input
        ref={fileRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }}
      />
    </div>
  )
}
