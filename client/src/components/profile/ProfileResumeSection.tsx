import { useEffect, useRef, useState } from 'react'
import { FileText, Loader2, Trash2, Upload, Check } from 'lucide-react'
import { getMyResume, uploadMyResume, deleteMyResume } from '../../api/profileResume'
import type { ProfileResume } from '../../api/profileResume'

const ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt']
const MAX_BYTES = 10 * 1024 * 1024

export default function ProfileResumeSection() {
  const fileRef = useRef<HTMLInputElement>(null)
  const [resume, setResume] = useState<ProfileResume | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    getMyResume()
      .then((r) => setResume(r))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function handleFile(file: File) {
    const lower = file.name.toLowerCase()
    const ok = ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))
    if (!ok) {
      setError(`Only ${ALLOWED_EXTENSIONS.join(', ')} files are supported`)
      return
    }
    if (file.size > MAX_BYTES) {
      setError('File must be under 10 MB')
      return
    }

    setUploading(true)
    setError(null)
    setSuccess(false)
    try {
      const result = await uploadMyResume(file)
      setResume(result)
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleDelete() {
    if (!confirm('Delete your profile resume? You can always re-upload.')) return
    setDeleting(true)
    try {
      await deleteMyResume()
      setResume(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-sm font-medium text-zinc-300">Profile Resume</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Upload once. Auto-fills job applications in paid channels.
          </p>
        </div>
        {resume && !loading && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="text-xs text-zinc-500 hover:text-red-400 transition-colors flex items-center gap-1"
          >
            {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
            Remove
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <Loader2 size={14} className="animate-spin" />
          Loading…
        </div>
      ) : resume ? (
        <ResumePreview resume={resume} onReplace={() => fileRef.current?.click()} replacing={uploading} />
      ) : (
        <EmptyState onSelect={() => fileRef.current?.click()} uploading={uploading} />
      )}

      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.doc,.docx,.txt"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) handleFile(file)
          e.target.value = ''
        }}
      />

      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      {success && (
        <p className="mt-3 text-sm text-emerald-400 flex items-center gap-1.5">
          <Check className="w-3.5 h-3.5" /> Resume updated
        </p>
      )}
    </div>
  )
}

function EmptyState({ onSelect, uploading }: { onSelect: () => void; uploading: boolean }) {
  return (
    <button
      onClick={onSelect}
      disabled={uploading}
      className="w-full flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-zinc-700 hover:border-emerald-600 hover:bg-zinc-900/60 py-8 transition-colors disabled:opacity-60"
    >
      {uploading ? (
        <Loader2 size={20} className="text-zinc-400 animate-spin" />
      ) : (
        <Upload size={20} className="text-zinc-500" />
      )}
      <span className="text-sm text-zinc-300">
        {uploading ? 'Parsing resume…' : 'Upload your resume'}
      </span>
      <span className="text-xs text-zinc-500">PDF, DOC, DOCX, or TXT · 10 MB max</span>
    </button>
  )
}

function ResumePreview({
  resume,
  onReplace,
  replacing,
}: {
  resume: ProfileResume
  onReplace: () => void
  replacing: boolean
}) {
  const p = resume.parsed_data
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-emerald-950 border border-emerald-900 flex items-center justify-center shrink-0">
          <FileText size={18} className="text-emerald-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200 truncate">{resume.filename}</p>
          <p className="text-xs text-zinc-500 mt-0.5">
            Updated {new Date(resume.updated_at).toLocaleDateString()}
          </p>
        </div>
        <button
          onClick={onReplace}
          disabled={replacing}
          className="text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1.5 px-2.5 py-1 rounded border border-zinc-700 hover:border-zinc-600 shrink-0"
        >
          {replacing ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />}
          Replace
        </button>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 space-y-3">
        {p.name && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">Name</div>
            <div className="text-sm text-zinc-200">{p.name}</div>
          </div>
        )}
        {p.current_title && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">Current title</div>
            <div className="text-sm text-zinc-200">
              {p.current_title}
              {typeof p.experience_years === 'number' && ` · ${p.experience_years} yrs`}
            </div>
          </div>
        )}
        {p.location && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">Location</div>
            <div className="text-sm text-zinc-200">{p.location}</div>
          </div>
        )}
        {p.skills && p.skills.length > 0 && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Skills</div>
            <div className="flex flex-wrap gap-1.5">
              {p.skills.slice(0, 16).map((s) => (
                <span
                  key={s}
                  className="text-[11px] px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-300"
                >
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
        {p.summary && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-0.5">Summary</div>
            <div className="text-xs text-zinc-400 leading-relaxed">{p.summary}</div>
          </div>
        )}
      </div>
    </div>
  )
}
