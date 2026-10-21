import { useState, type FormEvent } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { CappeApiError, cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeAsset, IllustrationAspect } from '../../types'

const ASPECTS: { key: IllustrationAspect; label: string }[] = [
  { key: '3:2', label: 'Landscape 3:2' },
  { key: '16:9', label: 'Wide 16:9' },
  { key: '4:3', label: 'Landscape 4:3' },
  { key: '1:1', label: 'Square' },
  { key: '3:4', label: 'Portrait 3:4' },
  { key: '2:3', label: 'Portrait 2:3' },
  { key: '9:16', label: 'Tall 9:16' },
]

/**
 * "Illustrate": describe a picture and get an AI illustration in the library.
 * It is always credited "AI illustration", and the server refuses prompts
 * that show a real person (the reason is shown here, as a refusal, not an error).
 */
export default function IllustrateForm({ siteId, onDone, onCancel }: {
  siteId: string
  onDone: (asset: CappeAsset) => void
  onCancel: () => void
}) {
  const [prompt, setPrompt] = useState('')
  const [aspect, setAspect] = useState<IllustrationAspect>('3:2')
  const [busy, setBusy] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (prompt.trim().length < 3) return
    setBusy(true)
    setRefusal(null)
    setError(null)
    try {
      onDone(await cappeApi.post<CappeAsset>(`/sites/${siteId}/library/illustrate`, { prompt: prompt.trim(), aspect }))
    } catch (err) {
      if (err instanceof CappeApiError && err.code === 'real_person') setRefusal(err.message)
      else setError(err instanceof Error ? err.message : 'The illustration didn’t come out. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className={`${ui.card} grid gap-3 p-4`} aria-label="Illustrate">
      <label>
        <span className={ui.label}>Describe the illustration</span>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={1000} rows={3} className={ui.input}
          placeholder="A lighthouse keeper's kitchen at night, rain on the window, a kettle on the stove" />
      </label>
      <label className="max-w-xs">
        <span className={ui.label}>Shape</span>
        <select value={aspect} onChange={(e) => setAspect(e.target.value as IllustrationAspect)} className={ui.input}>
          {ASPECTS.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
        </select>
      </label>
      <p className="text-xs text-zinc-500">
        Drawn as an illustration, never a photograph, and always credited “AI illustration” in your stories.
        It can’t show real people; for them, use a photo from the archives or one you took.
      </p>
      {refusal && <p role="alert" className="rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-300">{refusal}</p>}
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" className={ui.btnPrimary} disabled={prompt.trim().length < 3 || busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {busy ? 'Drawing…' : 'Illustrate'}
        </button>
        <button type="button" className={ui.btnGhost} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  )
}
