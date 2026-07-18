import { useState } from 'react'
import { Lightbulb, Trash2, ImagePlus, Loader2, ArrowRight, CheckCircle2, X } from 'lucide-react'
import { api } from '../../../api/client'
import { uploadNewsletterMedia } from './uploadMedia'
import type { Idea, Newsletter } from './types'

/**
 * Idea scratchpad + template generator.
 *
 * Left: quick-capture (jot a title + notes, optionally attach a visual).
 * Right/list: captured ideas. Each idea's "Create Newsletter" action exports
 * it into a structured newsletter draft — but the template MANDATES a visual,
 * so an idea with no attached media prompts for an image before the export is
 * allowed (mirrors the backend's 422 media requirement).
 */
export function IdeasTab({
  ideas,
  onChange,
  onCreatedNewsletter,
}: {
  ideas: Idea[]
  onChange: () => Promise<void> | void
  onCreatedNewsletter: (nl: Newsletter) => void
}) {
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [captureMedia, setCaptureMedia] = useState<string | null>(null)
  const [capturing, setCapturing] = useState(false)
  const [saving, setSaving] = useState(false)

  // Per-idea "needs a visual before we can export" panel state.
  const [mediaPromptFor, setMediaPromptFor] = useState<string | null>(null)
  const [pendingMedia, setPendingMedia] = useState<string | null>(null)
  const [pendingUploading, setPendingUploading] = useState(false)
  const [creatingId, setCreatingId] = useState<string | null>(null)

  async function pickMedia(file: File, onUrl: (url: string) => void, setBusy: (b: boolean) => void) {
    setBusy(true)
    const url = await uploadNewsletterMedia(file)
    setBusy(false)
    if (!url) { alert('Upload failed — try a different file.'); return }
    onUrl(url)
  }

  async function saveIdea() {
    if (!title.trim()) return
    setSaving(true)
    try {
      await api.post('/admin/newsletter/ideas', {
        title: title.trim(),
        notes: notes.trim() || undefined,
        media_url: captureMedia || undefined,
      })
      setTitle(''); setNotes(''); setCaptureMedia(null)
      await onChange()
    } catch (err) {
      alert(`Could not save idea: ${(err as Error).message}`)
    }
    setSaving(false)
  }

  async function removeIdea(id: string) {
    if (!confirm('Delete this idea?')) return
    try {
      await api.delete(`/admin/newsletter/ideas/${id}`)
      await onChange()
    } catch (err) {
      alert(`Delete failed: ${(err as Error).message}`)
    }
  }

  // Export an idea into a structured newsletter draft. Enforces the mandatory
  // visual: if the idea has no media and none has been staged in the prompt,
  // open the media prompt instead of calling the API.
  async function createNewsletter(idea: Idea, mediaUrl?: string | null) {
    const media = mediaUrl ?? idea.media_url
    if (!media) {
      setMediaPromptFor(idea.id)
      setPendingMedia(null)
      return
    }
    setCreatingId(idea.id)
    try {
      const nl = await api.post<Newsletter>(`/admin/newsletter/ideas/${idea.id}/create-newsletter`, {
        media_url: media,
      })
      setMediaPromptFor(null); setPendingMedia(null)
      await onChange()
      onCreatedNewsletter(nl)
    } catch (err) {
      alert(`Could not create newsletter: ${(err as Error).message}`)
    }
    setCreatingId(null)
  }

  return (
    <div className="grid lg:grid-cols-[360px_1fr] gap-6 max-w-6xl">
      {/* Quick capture */}
      <div className="rounded-xl border border-zinc-800 p-4 space-y-3 self-start">
        <div className="flex items-center gap-2">
          <Lightbulb size={14} className="text-amber-400" />
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Capture an idea</p>
        </div>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) saveIdea() }}
          placeholder="Idea title"
          className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none"
        />
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Jot down the concept, angle, links, sources…"
          rows={5}
          className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none resize-y"
        />
        {captureMedia ? (
          <div className="relative rounded-lg overflow-hidden border border-zinc-700">
            <img src={captureMedia} alt="Attached visual" className="w-full max-h-40 object-cover" />
            <button
              onClick={() => setCaptureMedia(null)}
              className="absolute top-1.5 right-1.5 p-1 rounded-md bg-black/60 text-zinc-200 hover:text-white"
            >
              <X size={13} />
            </button>
          </div>
        ) : (
          <label className="flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-dashed border-zinc-700 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-300 cursor-pointer">
            {capturing ? <Loader2 size={13} className="animate-spin" /> : <ImagePlus size={13} />}
            {capturing ? 'Uploading…' : 'Attach a visual (optional)'}
            <input
              type="file"
              accept="image/*,video/*"
              className="hidden"
              disabled={capturing}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) pickMedia(f, setCaptureMedia, setCapturing)
                e.target.value = ''
              }}
            />
          </label>
        )}
        <button
          onClick={saveIdea}
          disabled={!title.trim() || saving}
          className="w-full px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg disabled:opacity-40 flex items-center justify-center gap-2"
        >
          {saving && <Loader2 size={14} className="animate-spin" />} Save idea
        </button>
      </div>

      {/* Idea list */}
      <div className="space-y-3">
        <p className="text-xs text-zinc-400">
          Ideas you've captured. Hit <span className="text-emerald-400">Create Newsletter</span> to turn one into a
          structured draft — a visual is required so every newsletter ships with imagery.
        </p>
        {ideas.length === 0 && <p className="text-zinc-500 text-sm py-4">No ideas yet — capture your first on the left.</p>}
        {ideas.map((idea) => {
          const converted = idea.status === 'converted'
          return (
            <div key={idea.id} className="rounded-xl border border-zinc-800 overflow-hidden">
              <div className="flex gap-3 px-4 py-3">
                {idea.media_url && !idea.media_url.match(/\.(mp4|mov|webm)(\?|$)/i) && (
                  <img src={idea.media_url} alt="" className="w-14 h-14 rounded-lg object-cover shrink-0 border border-zinc-800" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm text-zinc-200 truncate">{idea.title}</p>
                    {converted && (
                      <span className="flex items-center gap-1 text-[10px] text-emerald-400 shrink-0">
                        <CheckCircle2 size={11} /> Converted
                      </span>
                    )}
                  </div>
                  {idea.notes && <p className="text-[11px] text-zinc-500 line-clamp-2 whitespace-pre-wrap mt-0.5">{idea.notes}</p>}
                </div>
                <div className="flex items-center gap-2 shrink-0 self-start">
                  <button
                    onClick={() => createNewsletter(idea)}
                    disabled={creatingId === idea.id}
                    className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
                  >
                    {creatingId === idea.id ? <Loader2 size={12} className="animate-spin" /> : <ArrowRight size={12} />}
                    {converted ? 'Recreate' : 'Create Newsletter'}
                  </button>
                  <button onClick={() => removeIdea(idea.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={13} /></button>
                </div>
              </div>

              {/* Mandatory-media prompt — shown when an idea has no visual yet. */}
              {mediaPromptFor === idea.id && (
                <div className="px-4 py-3 border-t border-zinc-800 bg-zinc-900/40 space-y-3">
                  <p className="text-[11px] text-amber-300/90">
                    Newsletters require at least one visual. Add an image or video to continue.
                  </p>
                  {pendingMedia ? (
                    <div className="relative rounded-lg overflow-hidden border border-zinc-700 max-w-xs">
                      <img src={pendingMedia} alt="Selected visual" className="w-full max-h-40 object-cover" />
                      <button
                        onClick={() => setPendingMedia(null)}
                        className="absolute top-1.5 right-1.5 p-1 rounded-md bg-black/60 text-zinc-200 hover:text-white"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  ) : (
                    <label className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-zinc-700 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-300 cursor-pointer">
                      {pendingUploading ? <Loader2 size={13} className="animate-spin" /> : <ImagePlus size={13} />}
                      {pendingUploading ? 'Uploading…' : 'Upload visual'}
                      <input
                        type="file"
                        accept="image/*,video/*"
                        className="hidden"
                        disabled={pendingUploading}
                        onChange={(e) => {
                          const f = e.target.files?.[0]
                          if (f) pickMedia(f, setPendingMedia, setPendingUploading)
                          e.target.value = ''
                        }}
                      />
                    </label>
                  )}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => createNewsletter(idea, pendingMedia)}
                      disabled={!pendingMedia || creatingId === idea.id}
                      className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg disabled:opacity-40 flex items-center gap-1.5"
                    >
                      {creatingId === idea.id && <Loader2 size={12} className="animate-spin" />}
                      Create with this visual
                    </button>
                    <button
                      onClick={() => { setMediaPromptFor(null); setPendingMedia(null) }}
                      className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
