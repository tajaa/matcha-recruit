import { useEffect, useRef, useState, type RefObject } from 'react'
import { X } from 'lucide-react'
import BookFrame from '../../magazine/reader/BookFrame'
import Canvas from '../canvas/Canvas'
import './studio.css'
import { moveItems } from '../model/ops'
import { useStudio } from '../store/store'
import { studioApi } from '../api'
import { MenuBar, StatusBar, ToolBar, TopBar } from './chrome'
import { commandForKey } from './commands'
import { StudioContext, useCtx, type StudioCtx } from './context'
import { LibraryDialog, PictureDialog, RevisionsDialog, StoryDialog } from './dialogs'
import { markGuideSeen } from './guideContent'
import StudioGuide from './StudioGuide'
import AddPanel from './add/AddPanel'
import Board from './board/Board'
import { AskPanel } from './panels/AskPanel'
import { ObjectPanel } from './panels/ObjectPanel'
import { PagesPanel } from './panels/PagesPanel'
import { StoryPanel } from './panels/StoryPanel'
import { CharacterPanel, ParagraphPanel } from './panels/TypePanels'

/** Gummfit Studio: menus and a control strip across the top, tools down the
 *  left, the pasteboard of pages in the middle, panels down the right. */
export default function Studio({ ctx }: { ctx: StudioCtx }) {
  return (
    <StudioContext.Provider value={ctx}>
      <Shell />
    </StudioContext.Provider>
  )
}

function Shell() {
  const c = useCtx()
  const dialog = useStudio(c.store, (s) => s.dialog)
  const guide = useStudio(c.store, (s) => s.guide)
  const panels = useStudio(c.store, (s) => s.panels)
  const conflict = useStudio(c.store, (s) => s.save.state === 'conflict')
  const [preview, setPreview] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const storeNotice = useStudio(c.store, (s) => s.notice ?? null)
  // While the preview is up its keys turn its pages: none reach the Studio.
  const previewing = useRef(false)
  useEffect(() => { previewing.current = preview !== null }, [preview])
  useKeys(c, previewing)

  const openPreview = async () => {
    try {
      setPreview(await studioApi.preview(c.siteId, c.post, c.store.get().doc))
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Couldn’t make the preview.')
    }
  }
  const publish = async () => {
    try {
      if (c.post.status === 'published') await c.save({ publish: true })
      else {
        // Only pages that saved go live: a failed save stops here.
        await c.save({ strict: true })
        c.setPost({ ...c.post, ...(await studioApi.updatePost(c.siteId, c.postId, { status: 'published' })) })
        c.store.set((s) => ({ save: { ...s.save, live: true, draft: false } }))
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : 'Couldn’t publish.')
    }
  }

  return (
    <div className="studio-dark fixed inset-0 z-40 flex select-none flex-col bg-zinc-950 text-zinc-100">
      <TopBar onPreview={() => void openPreview()} onPublish={() => void publish()} />
      <div className="border-b border-zinc-800 bg-zinc-900"><MenuBar /></div>
      {conflict && (
        <div role="alert" className="flex items-center gap-3 bg-amber-500/15 px-4 py-2 text-xs text-amber-300">
          This story was saved somewhere else since you opened it, so your changes aren't being saved.
          <button type="button" onClick={() => window.location.reload()} className="rounded border border-amber-400/50 px-2 py-0.5 hover:bg-amber-500/20">Reload it</button>
        </div>
      )}
      {(notice || storeNotice) && (
        <div role="alert" className="flex items-center gap-3 bg-red-500/15 px-4 py-2 text-xs text-red-300">
          {notice || storeNotice}
          <button type="button" onClick={() => { setNotice(null); c.store.set({ notice: null }) }} aria-label="Dismiss" className="ml-auto"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <AddPanel />
        <ToolBar />
        <Canvas />
        <aside aria-label="Panels" className="flex w-[300px] shrink-0 flex-col overflow-y-auto border-l border-zinc-800 bg-zinc-900">
          {panels.includes('pages') && <PagesPanel />}
          {panels.includes('props') && <ObjectPanel />}
          {panels.includes('character') && <CharacterPanel />}
          {panels.includes('paragraph') && <ParagraphPanel />}
          {panels.includes('story') && <StoryPanel />}
          {panels.includes('ask') && <AskPanel />}
        </aside>
      </div>
      <StatusBar />
      {dialog === 'library' && <LibraryDialog />}
      {dialog === 'story' && <StoryDialog />}
      {dialog === 'revisions' && <RevisionsDialog />}
      {dialog === 'board' && <Board />}
      {(dialog === 'picture' || dialog === 'cutout') && <PictureDialog cutout={dialog === 'cutout'} />}
      {preview !== null && <Preview html={preview} onClose={() => setPreview(null)} />}
      {guide && <StudioGuide section={guide} onClose={() => { markGuideSeen(); c.store.set({ guide: null }) }} />}
    </div>
  )
}

/** The story as a reader would get it (unsaved changes included). */
function Preview({ html, onClose }: { html: string; onClose: () => void }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/80 p-4">
      <div className="mb-2 flex items-center justify-between text-sm text-zinc-200">
        <span>Preview — as readers will see it</span>
        <button type="button" onClick={onClose} aria-label="Close the preview" className="rounded p-1 hover:bg-zinc-800"><X className="h-4 w-4" /></button>
      </div>
      {/* Scripts don't run in it: its pages turn from out here (the arrows, the keys). */}
      <BookFrame html={html} title="Preview" keys className="min-h-0 flex-1 rounded-lg bg-white" />
    </div>
  )
}

const TEXTY = new Set(['undo', 'redo', 'cut', 'copy', 'paste', 'select-all', 'deselect', 'delete', 'duplicate', 'hide', 'lock'])

/** The Studio's keys: every command's shortcut, the tools' letters, arrows to
 *  nudge (Shift: ten points), Esc to let go. Typing keeps its own keys. */
function useKeys(c: StudioCtx, paused: RefObject<boolean>) {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (paused.current) return
      const t = e.target as HTMLElement | null
      const s = c.store.get()
      const typing = !!s.editing && !!t && c.editor.view?.dom.contains(t)
      const field = !!t && !typing && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))
      const cmd = commandForKey(e)
      if (field) {
        if (cmd?.id === 'save') { e.preventDefault(); cmd.run(c) }
        return
      }
      if (typing) {
        if (cmd && (e.metaKey || e.ctrlKey) && !TEXTY.has(cmd.id) && !cmd.id.startsWith('tool-')) { e.preventDefault(); cmd.run(c) }
        return
      }
      if (s.dialog || s.guide) return
      if (e.key === 'Escape') {
        // Esc puts a drawing tool down first, then lets go of the selection.
        c.store.set(s.tool !== 'select' && !s.threading ? { tool: 'select' } : { selection: [], threading: null })
        return
      }
      const arrows: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }
      if (arrows[e.key] && s.selection.length) {
        e.preventDefault()
        const k = e.shiftKey ? 10 : 1
        c.store.edit((d) => moveItems(d, s.selection, arrows[e.key][0] * k, arrows[e.key][1] * k), { key: 'nudge' })
        return
      }
      if (cmd && (!cmd.enabled || cmd.enabled(s))) { e.preventDefault(); cmd.run(c) }
    }
    window.addEventListener('keydown', down)
    return () => window.removeEventListener('keydown', down)
  }, [c, paused])
}
