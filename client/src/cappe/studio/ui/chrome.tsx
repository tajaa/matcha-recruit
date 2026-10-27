import { useEffect, useRef, useState } from 'react'
import { Circle, CircleHelp, Hand, Image as ImageIcon, LayoutGrid, Minus, MousePointer2, Sparkles, Square, Type, X, ZoomIn } from 'lucide-react'
import type { Panel, Tool } from '../store/store'
import { useStudio } from '../store/store'
import { command, zoomTo, type Command } from './commands'
import { useCtx } from './context'

const MENUS: { label: string; items: (string | '-')[] }[] = [
  { label: 'File', items: ['save', 'story', 'revisions', '-', 'close'] },
  { label: 'Edit', items: ['undo', 'redo', '-', 'cut', 'copy', 'paste', 'duplicate', 'delete', '-', 'select-all', 'deselect'] },
  { label: 'Insert', items: ['add-templates', 'add-elements', 'add-text', 'add-photos', 'add-uploads', 'add-board', '-', 'place', 'tool-text'] },
  { label: 'Layout', items: ['board', '-', 'page-add', 'spread-add', 'page-delete', '-', 'page-up', 'page-down', '-', 'margins'] },
  { label: 'Type', items: ['story-editor', 'tool-text', '-', 'fonts'] },
  { label: 'Object', items: ['arrange-front', 'arrange-forward', 'arrange-backward', 'arrange-back', '-', 'lock', 'hide', 'show-all', '-', 'place', 'edit-picture', 'cut-out', 'subject-front', '-', 'across-spread', 'spine-clear', 'link-crops', 'unlink-crops'] },
  { label: 'View', items: ['zoom-in', 'zoom-out', 'fit-page', 'fit-spread', 'actual', '-', 'view-rulers', 'view-guides', 'view-margins', 'view-baseline', 'view-grid', 'view-gutter', 'view-snap', '-', 'board'] },
]
const HELP = { label: 'Help', items: ['ask', '-', 'guide', 'shortcuts'] }

/** The menus: every command with the key that does it too. */
export function MenuBar() {
  const c = useCtx()
  const state = useStudio(c.store, (s) => s)
  const [open, setOpen] = useState<number | null>(null)
  const bar = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (open === null) return
    const away = (e: PointerEvent) => { if (!bar.current?.contains(e.target as Node)) setOpen(null) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(null) }
    window.addEventListener('pointerdown', away, true)
    window.addEventListener('keydown', esc)
    return () => { window.removeEventListener('pointerdown', away, true); window.removeEventListener('keydown', esc) }
  }, [open])
  const run = (cmd: Command) => { setOpen(null); cmd.run(c) }
  const checked = (id: string) => id.startsWith('view-') && state.view[id.slice(5) as keyof typeof state.view] === true
  const menu = (m: { label: string; items: (string | '-')[] }, k: number) => (
        <div key={m.label} className="relative">
          <button type="button" role="menuitem" aria-haspopup="menu" aria-expanded={open === k}
            onClick={() => setOpen(open === k ? null : k)} onPointerEnter={() => open !== null && setOpen(k)}
            className={`rounded px-2 py-0.5 ${open === k ? 'bg-zinc-700 text-white' : 'hover:bg-zinc-800'}`}>{m.label}</button>
          {open === k && (
            <div role="menu" className="absolute left-0 top-full z-50 mt-1 min-w-[230px] rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-2xl">
              {m.items.map((id, j) => id === '-' ? <div key={j} className="my-1 border-t border-zinc-800" /> : (() => {
                const cmd = command(id)
                const enabled = cmd.enabled ? cmd.enabled(state) : true
                return (
                  <button key={id} type="button" role="menuitem" disabled={!enabled} onClick={() => run(cmd)}
                    className="flex w-full items-center justify-between gap-6 px-3 py-1 text-left text-zinc-200 hover:bg-emerald-600 hover:text-white disabled:text-zinc-600 disabled:hover:bg-transparent">
                    <span className="flex items-center gap-2"><span className="w-3 text-emerald-400">{checked(id) ? '✓' : ''}</span>{cmd.label}</span>
                    {cmd.keys && <kbd className="font-sans text-[11px] text-zinc-500">{cmd.keys}</kbd>}
                  </button>
                )
              })())}
            </div>
          )}
        </div>
  )
  return (
    <div ref={bar} role="menubar" className="flex h-7 items-center gap-0.5 px-2 text-[12px] text-zinc-300">
      {MENUS.map(menu)}
      <WindowMenu />
      {menu(HELP, MENUS.length)}
    </div>
  )
}

const PANELS: { key: Panel; label: string }[] = [
  { key: 'identity', label: 'Magazine identity' },
  { key: 'pages', label: 'Pages' }, { key: 'props', label: 'Object' }, { key: 'character', label: 'Character' },
  { key: 'paragraph', label: 'Paragraph' }, { key: 'story', label: 'Story Editor' }, { key: 'ask', label: 'Ask the Studio' },
]

function WindowMenu() {
  const { store } = useCtx()
  const panels = useStudio(store, (s) => s.panels)
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className={`rounded px-2 py-0.5 ${open ? 'bg-zinc-700 text-white' : 'hover:bg-zinc-800'}`}>Window</button>
      {open && (
        <div role="menu" className="absolute left-0 top-full z-50 mt-1 min-w-[180px] rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-2xl"
          onPointerLeave={() => setOpen(false)}>
          {PANELS.map((p) => (
            <button key={p.key} type="button" role="menuitemcheckbox" aria-checked={panels.includes(p.key)}
              onClick={() => store.set((s) => ({ panels: s.panels.includes(p.key) ? s.panels.filter((x) => x !== p.key) : [...s.panels, p.key] }))}
              className="flex w-full items-center gap-2 px-3 py-1 text-left text-zinc-200 hover:bg-emerald-600 hover:text-white">
              <span className="w-3 text-emerald-400">{panels.includes(p.key) ? '✓' : ''}</span>{p.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const TOOLS: { tool: Tool; label: string; key: string; icon: React.ReactNode }[] = [
  { tool: 'select', label: 'Selection', key: 'V', icon: <MousePointer2 className="h-4 w-4" /> },
  { tool: 'text', label: 'Type', key: 'T', icon: <Type className="h-4 w-4" /> },
  { tool: 'frame', label: 'Picture frame', key: 'F', icon: <ImageIcon className="h-4 w-4" /> },
  { tool: 'rect', label: 'Rectangle', key: 'M', icon: <Square className="h-4 w-4" /> },
  { tool: 'ellipse', label: 'Ellipse', key: 'L', icon: <Circle className="h-4 w-4" /> },
  { tool: 'line', label: 'Line', key: '\\', icon: <Minus className="h-4 w-4 -rotate-45" /> },
  { tool: 'hand', label: 'Hand', key: 'H', icon: <Hand className="h-4 w-4" /> },
  { tool: 'zoom', label: 'Zoom', key: 'Z', icon: <ZoomIn className="h-4 w-4" /> },
]

/** The tools, down the left. */
export function ToolBar() {
  const c = useCtx()
  const tool = useStudio(c.store, (s) => s.tool)
  return (
    <div role="toolbar" aria-label="Tools" aria-orientation="vertical" className="flex w-11 shrink-0 flex-col items-center gap-1 border-r border-zinc-800 bg-zinc-900 py-2">
      {TOOLS.map((t) => (
        <button key={t.tool} type="button" title={`${t.label} (${t.key})`} aria-label={t.label} aria-pressed={tool === t.tool}
          onClick={() => {
            command(`tool-${t.tool}`).run(c)
            // A picture is placed from the library; drawing an empty frame stays the tool's.
            if (t.tool === 'frame') command('place').run(c)
          }}
          className={`flex h-8 w-8 items-center justify-center rounded-md ${tool === t.tool ? 'bg-emerald-500/20 text-emerald-300' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'}`}>
          {t.icon}
        </button>
      ))}
    </div>
  )
}

const ZOOMS = [0.25, 0.5, 0.75, 1, 4 / 3, 2, 3, 4, 8]

/** Zoom, the page in view, what's left over, whether it's saved. */
export function StatusBar() {
  const c = useCtx()
  const zoom = useStudio(c.store, (s) => s.view.zoom)
  const page = useStudio(c.store, (s) => s.page)
  const pages = useStudio(c.store, (s) => s.doc.pages.length)
  const overset = useStudio(c.store, (s) => s.overset.size)
  const save = useStudio(c.store, (s) => s.save)
  const threading = useStudio(c.store, (s) => s.threading)
  const tool = useStudio(c.store, (s) => s.tool)
  const pct = Math.round((zoom * 72 / 96) * 100)
  return (
    <div className="flex h-7 shrink-0 items-center gap-4 border-t border-zinc-800 bg-zinc-900 px-3 text-[11px] text-zinc-400">
      <label className="flex items-center gap-1">
        <span className="sr-only">Zoom</span>
        <select value="" onChange={(e) => zoomTo(c, Number(e.target.value))}
          className="rounded bg-transparent text-zinc-300 outline-none">
          <option value="">{pct}%</option>
          {ZOOMS.map((z) => <option key={z} value={z * 96 / 72}>{Math.round(z * 100)}%</option>)}
        </select>
      </label>
      <span>Page {page + 1} of {pages}</span>
      {threading && <span className="text-emerald-300">Click a text frame to flow the text into it (Esc to stop)</span>}
      {!threading && TOOL_HINT[tool] && <span className="text-emerald-300">{TOOL_HINT[tool]} · Esc for the Selection tool</span>}
      {overset > 0 && <span className="text-red-300">{overset === 1 ? 'Some text doesn’t fit' : `${overset} texts don’t fit`}</span>}
      <span className="ml-auto" role="status">{SAVE_LABEL[save.state]}{save.message ? ` — ${save.message}` : ''}</span>
    </div>
  )
}

/** What a tool does, said in the status bar while it is in hand. */
const TOOL_HINT: Partial<Record<Tool, string>> = {
  text: 'Type: click a page for a text frame the width of the column, or drag one out; click a text frame to type in it',
  frame: 'Picture frame: drag one out on a page, then choose its picture',
  rect: 'Rectangle: click a page for a 2-inch square, or drag one out (Shift: a square)',
  ellipse: 'Ellipse: click a page for a 2-inch circle, or drag one out (Shift: a circle)',
  line: 'Line: drag on a page (Shift: at 45°), or click for a 2-inch line',
  hand: 'Hand: drag to move around the pages (Space does this with any tool)',
  zoom: 'Zoom: click to zoom in, Alt-click to zoom out',
}

const SAVE_LABEL = { saved: 'Saved', dirty: 'Unsaved changes', saving: 'Saving…', error: 'Couldn’t save', conflict: 'Saved elsewhere' }

/** The story's name, where its changes are going, and the way out. */
export function TopBar({ onPreview, onPublish }: { onPreview: () => void; onPublish: () => void }) {
  const c = useCtx()
  const save = useStudio(c.store, (s) => s.save)
  const published = c.post.status === 'published'
  return (
    <div className="flex h-11 shrink-0 items-center gap-3 border-b border-zinc-800 bg-zinc-950 px-3">
      <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">Studio</span>
      <button type="button" onClick={() => c.store.set({ dialog: 'story' })} title="Story settings"
        className="min-w-0 truncate text-sm font-medium text-zinc-100 hover:text-white">{c.post.title || 'Untitled story'}</button>
      {published && (
        <span className="text-[11px] text-zinc-500">{save.draft ? 'Changes not live yet' : 'Live'}</span>
      )}
      <div className="ml-auto flex items-center gap-2">
        <button type="button" onClick={() => command('board').run(c)} title="Every page together, to put the issue in order (⌥⌘P)"
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-white">
          <LayoutGrid className="h-3.5 w-3.5" />Board
        </button>
        <button type="button" onClick={() => command('ask').run(c)} title="Ask how to do something, or how to get a look"
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-white">
          <Sparkles className="h-3.5 w-3.5 text-emerald-400" />Ask
        </button>
        <button type="button" onClick={() => c.store.set({ guide: 'start' })} aria-label="How the Studio works" title="How the Studio works"
          className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><CircleHelp className="h-4 w-4" /></button>
        <button type="button" onClick={onPreview} className="rounded-md border border-zinc-700 px-3 py-1 text-xs text-zinc-200 hover:border-zinc-500">Preview</button>
        {(!published || save.draft) && (
          <button type="button" onClick={onPublish}
            className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500">
            {published ? 'Update live story' : 'Publish'}
          </button>
        )}
        <button type="button" onClick={c.close} aria-label="Close the Studio" title="Close"
          className="rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><X className="h-4 w-4" /></button>
      </div>
    </div>
  )
}
