import { ArrowLeft, Loader2, MousePointerClick, Pencil, Redo2, Save, Sparkles, Undo2 } from 'lucide-react'
import { EditorHelp } from './EditorHelp'
import { PromosPanel } from './PromosPanel'
import { ThemeMenu } from './ThemeMenu'
import type { useMerlin } from './useMerlin'
import type { useThemeEditor } from './useThemeEditor'

export function EditorToolbar({
  title, setTitle, slug, notice, error,
  meta, setMeta, promosDirty, setPromosDirty,
  designerUnlocked, themeEditor, merlin,
  canvasUnlocked, editMode, setEditMode,
  status, setStatus, saving, onSave, onBack,
  onUndo, onRedo, canUndo, canRedo,
}: {
  title: string
  setTitle: (v: string) => void
  slug: string
  notice: string | null
  error: string | null
  meta: Record<string, unknown>
  setMeta: (m: Record<string, unknown>) => void
  promosDirty: boolean
  setPromosDirty: (v: boolean) => void
  designerUnlocked: boolean
  themeEditor: ReturnType<typeof useThemeEditor>
  merlin: ReturnType<typeof useMerlin>
  canvasUnlocked: boolean
  editMode: 'form' | 'canvas'
  setEditMode: (m: 'form' | 'canvas') => void
  status: 'draft' | 'published'
  setStatus: (s: 'draft' | 'published') => void
  saving: boolean
  onSave: () => void
  onBack: () => void
  onUndo: () => void
  onRedo: () => void
  canUndo: boolean
  canRedo: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-zinc-800 bg-zinc-900 px-6 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <button onClick={onBack} className="text-zinc-500 hover:text-zinc-200"><ArrowLeft className="h-5 w-5" /></button>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="min-w-0 rounded-md border border-transparent bg-transparent px-2 py-1 text-lg font-semibold text-zinc-50 hover:border-zinc-700 focus:border-emerald-500 focus:outline-none"
        />
        <span className="shrink-0 text-xs text-zinc-500">/{slug}</span>
      </div>
      <div className="flex items-center gap-2">
        {notice && <span className="text-sm text-emerald-400">{notice}</span>}
        {error && <span className="text-sm text-red-400">{error}</span>}

        {/* Undo / redo (⌘Z / ⌘⇧Z) */}
        <div className="flex rounded-lg border border-zinc-700 p-0.5">
          <button onClick={onUndo} disabled={!canUndo} title="Undo (⌘Z)" className="rounded-md px-1.5 py-1 text-zinc-400 hover:text-zinc-100 disabled:opacity-30"><Undo2 className="h-4 w-4" /></button>
          <button onClick={onRedo} disabled={!canRedo} title="Redo (⌘⇧Z)" className="rounded-md px-1.5 py-1 text-zinc-400 hover:text-zinc-100 disabled:opacity-30"><Redo2 className="h-4 w-4" /></button>
        </div>

        {/* "What can I do here?" helper */}
        <EditorHelp designerUnlocked={designerUnlocked} />

        {/* Site-wide promos (announcement bar + pop-up) */}
        <PromosPanel meta={meta} premium={designerUnlocked} dirty={promosDirty} onChange={(m) => { setMeta(m); setPromosDirty(true) }} />

        {/* Live theme switcher toggle — the drawer itself renders in index.tsx
            as a flex sibling of the preview, not here. */}
        <ThemeMenu themeEditor={themeEditor} />

        {/* The three editing surfaces, mutually exclusive — Merlin is the
            pro-level way to edit; Canvas/Form are the basic sub-editors.
            Never more than one rendered at once (index.tsx picks exactly
            one), so this is a single 3-way selector rather than an
            independent Merlin toggle plus a separate Canvas/Form pair. */}
        <div className="flex rounded-lg border border-zinc-700 p-0.5">
          <button
            onClick={() => merlin.setOpen((o) => !o)}
            className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${merlin.open ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}
          >
            <Sparkles className="h-3.5 w-3.5" /> Merlin
          </button>
          {canvasUnlocked && (
            <button
              onClick={() => setEditMode('canvas')}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${!merlin.open && editMode === 'canvas' ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}
            >
              <MousePointerClick className="h-3.5 w-3.5" /> Canvas
            </button>
          )}
          <button
            onClick={() => setEditMode('form')}
            className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${!merlin.open && editMode === 'form' ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}
          >
            <Pencil className="h-3.5 w-3.5" /> Form
          </button>
        </div>

        <select value={status} onChange={(e) => setStatus(e.target.value as 'draft' | 'published')} className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-100">
          <option value="draft">Draft</option>
          <option value="published">Published</option>
        </select>
        <button onClick={onSave} disabled={saving} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save
        </button>
      </div>
    </div>
  )
}
