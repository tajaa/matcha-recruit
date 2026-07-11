import { useEffect, useState } from 'react'
import { Bookmark, Check, Loader2, Trash2 } from 'lucide-react'
import { cappeApi } from '../../../../api/cappeClient'
import type { CappeStylePreset } from '../../../../types/cappe'
import { dLabel, inputCls } from './styles'

/** Per-account saved-style library for one kind ('theme' | 'section'). */
export function useStylePresets(kind: 'theme' | 'section') {
  const [presets, setPresets] = useState<CappeStylePreset[]>([])
  const [loaded, setLoaded] = useState(false)

  const refresh = () =>
    cappeApi.get<CappeStylePreset[]>('/style-presets')
      .then((all) => setPresets(all.filter((p) => p.kind === kind)))
      .catch(() => { /* non-fatal */ })
      .finally(() => setLoaded(true))

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [])

  const save = async (name: string, data: Record<string, unknown>) => {
    const created = await cappeApi.post<CappeStylePreset>('/style-presets', { name, kind, data })
    setPresets((ps) => [created, ...ps])
  }
  const remove = async (id: string) => {
    await cappeApi.delete(`/style-presets/${id}`)
    setPresets((ps) => ps.filter((p) => p.id !== id))
  }
  return { presets, loaded, save, remove }
}

/** Compact "save current + apply saved" panel used in both the theme menu and
 *  the per-section design inspector. */
export function StylePresetsPanel({ kind, currentData, onApply, label }: {
  kind: 'theme' | 'section'
  currentData: Record<string, unknown>
  onApply: (data: Record<string, unknown>) => void
  label: string
}) {
  const { presets, loaded, save, remove } = useStylePresets(kind)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const onSave = async () => {
    const n = name.trim()
    if (!n || busy) return
    setBusy(true)
    try { await save(n, currentData); setName('') } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <span className={dLabel}>{label}</span>
      <div className="flex gap-1.5">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name this look"
          onKeyDown={(e) => { if (e.key === 'Enter') onSave() }}
          className={`${inputCls} py-1.5`} />
        <button type="button" onClick={onSave} disabled={!name.trim() || busy}
          className="flex shrink-0 items-center gap-1 rounded-lg border border-zinc-700 px-2.5 text-xs font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400 disabled:opacity-40">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bookmark className="h-3.5 w-3.5" />} Save
        </button>
      </div>
      {loaded && presets.length > 0 && (
        <div className="space-y-1">
          {presets.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-2 rounded-md border border-zinc-800 px-2 py-1">
              <button type="button" onClick={() => onApply(p.data)} title="Apply"
                className="flex min-w-0 items-center gap-1.5 text-xs text-zinc-300 hover:text-emerald-400">
                <Check className="h-3 w-3 shrink-0 text-zinc-600" /><span className="truncate">{p.name}</span>
              </button>
              <button type="button" onClick={() => remove(p.id)} title="Delete" className="shrink-0 text-zinc-600 hover:text-red-400">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
