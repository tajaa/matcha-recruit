import { useState } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'

// Reusable "propose → review → add selected" panel for register-style sections.
// Proposes likely rows from the company's own context, lets the user uncheck any,
// then bulk-creates the chosen. Label is per-use ("Suggest tools" etc.) — the
// button describes the register it fills, not the machinery behind it.
export function AiSuggest<T>({ fetchSuggestions, itemLabel, createItem, onDone, label = 'Suggest likely' }: {
  fetchSuggestions: () => Promise<{ suggestions: T[]; available: boolean }>
  itemLabel: (t: T) => string
  createItem: (t: T) => Promise<unknown>
  onDone: () => void
  label?: string
}) {
  const [items, setItems] = useState<T[] | null>(null)
  const [sel, setSel] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)

  async function run() {
    setBusy(true)
    try {
      const r = await fetchSuggestions()
      setItems(r.suggestions)
      setSel(new Set(r.suggestions.map((_, i) => i)))
    } catch { setItems([]) } finally { setBusy(false) }
  }
  async function addSelected() {
    if (!items) return
    setSaving(true)
    try {
      for (let i = 0; i < items.length; i++) if (sel.has(i)) await createItem(items[i])
      setItems(null); onDone()
    } catch { /* leave */ } finally { setSaving(false) }
  }
  function toggle(i: number) {
    setSel((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n })
  }

  return (
    <>
      <button onClick={run} disabled={busy} className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded-lg border border-emerald-900/60 hover:border-emerald-700 disabled:opacity-50">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} {busy ? 'Thinking…' : label}
      </button>
      {items && (
        <div className="mt-3 p-3 rounded-xl bg-emerald-950/20 border border-emerald-900/40">
          {items.length === 0 ? (
            <p className="text-xs text-zinc-400">No suggestions — add manually.</p>
          ) : (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-emerald-400 font-medium">{items.length} suggested — uncheck any, then add.</span>
                <div className="flex items-center gap-2">
                  <button onClick={() => setItems(null)} className="text-[11px] text-zinc-500 hover:text-zinc-300">Dismiss</button>
                  <button onClick={addSelected} disabled={saving || sel.size === 0} className="text-xs bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-3 py-1 disabled:opacity-50">{saving ? 'Adding…' : `Add ${sel.size}`}</button>
                </div>
              </div>
              <div className="space-y-1">
                {items.map((it, i) => (
                  <label key={i} className="flex items-start gap-2 text-xs text-zinc-300 py-0.5 cursor-pointer">
                    <input type="checkbox" checked={sel.has(i)} onChange={() => toggle(i)} className="h-3.5 w-3.5 rounded border-zinc-700 bg-zinc-900 mt-0.5" />
                    <span>{itemLabel(it)}</span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </>
  )
}
