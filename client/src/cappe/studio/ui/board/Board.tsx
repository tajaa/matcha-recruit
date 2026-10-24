import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react'
import {
  ArrowDown, ArrowUp, BookmarkPlus, ChevronLeft, ChevronRight, CircleHelp, Columns2, Focus, GripVertical, Image, Images, Layers,
  Maximize2, Palette, Redo2, Square, TriangleAlert, Type, Undo2, User, X, type LucideIcon,
} from 'lucide-react'
import { pageSide, spreads } from '../../model/doc'
import { gutterIssues, type GutterIssue } from '../../model/gutter'
import { BEAT_LABEL, beats, type Beat, type PageBeat } from '../../model/rhythm'
import { moveBlock, removeSection, renameSection, runs, startSection, type Run } from '../../model/sections'
import type { Doc } from '../../model/types'
import { frameThreads, pageItemsHtml, type Draw } from '../../render/layoutRender'
import { setHtml } from '../../render/sink'
import { useStudio } from '../../store/store'
import { useCtx } from '../context'
import { PAIRS, applyPair, pairTarget, type Pair } from './pairs'
import { boundPages, nudge, sidesChanged, slotAt, type Tile } from './sequence'

const SIZES = { s: 84, m: 124, l: 176 } as const
type Size = keyof typeof SIZES
const SIZE_KEY = 'cappe-studio-board-size'

const BEAT_ICON: Record<Beat, LucideIcon> = {
  bleed: Maximize2, picture: Image, portrait: User, pictures: Images, detail: Focus, words: Type, mixed: Layers,
  colour: Palette, white: Square,
}
const SHORT: Record<Beat, string> = {
  bleed: 'Bleed', picture: 'Picture', portrait: 'Portrait', pictures: 'Pictures', detail: 'Detail', words: 'Words',
  mixed: 'Mixed', colour: 'Colour', white: 'White',
}

function savedSize(): Size {
  try {
    const v = localStorage.getItem(SIZE_KEY)
    return v === 's' || v === 'm' || v === 'l' ? v : 'm'
  } catch {
    return 'm'
  }
}

type Drag = { ids: string[]; story: boolean }

/** The issue board: every page of the story, spread by spread and story by
 *  story, big enough to judge the rhythm, to put in order by dragging. */
export default function Board() {
  const c = useCtx()
  const { store } = c
  const doc = useStudio(store, (s) => s.doc)
  const page = useStudio(store, (s) => s.page)
  const [size, setSizeState] = useState<Size>(savedSize)
  const [showBeats, setShowBeats] = useState(true)
  const [picked, setPicked] = useState<string[]>(() => (doc.pages[page] ? [doc.pages[page].id] : []))
  const [anchor, setAnchor] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [pairsOpen, setPairsOpen] = useState(false)
  // React hears only that a drag began or ended; the bar and the label move
  // by their own elements, so a drag never draws the board again.
  const [drag, setDrag] = useState<Drag | null>(null)
  const bar = useRef<HTMLDivElement>(null)
  const label = useRef<HTMLDivElement>(null)
  const target = useRef<ReturnType<typeof slotAt>>(null)
  const root = useRef<HTMLDivElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const pending = useRef<{ ids: string[]; x: number; y: number; story: boolean } | null>(null)
  const dragged = useRef(false)

  const allRuns = useMemo(() => runs(doc), [doc])
  const rhythm = useMemo(() => beats(doc), [doc])
  const issues = useMemo(() => gutterIssues(doc), [doc])
  const live = new Set(doc.pages.map((p) => p.id))
  const chosen = picked.filter((id) => live.has(id))
  const chosenIndex = chosen.map((id) => doc.pages.findIndex((p) => p.id === id)).sort((a, b) => a - b)
  const pairOk = pairTarget(doc, chosenIndex)

  useEffect(() => { root.current?.focus() }, [])

  const close = () => store.set({ dialog: null })
  const open = (index: number) => {
    store.set({ dialog: null, page: index, selection: [] })
    requestAnimationFrame(() => c.fit(index, true))
  }
  const setSize = (s: Size) => {
    setSizeState(s)
    try { localStorage.setItem(SIZE_KEY, s) } catch { /* private window: this time only */ }
  }

  /** Change the document, saying so when pages turned over. */
  const change = (fn: (d: Doc) => Doc, after?: (d: Doc) => void) => {
    const before = store.get().doc
    store.edit(fn)
    const now = store.get().doc
    if (now === before) return
    const k = sidesChanged(before, now)
    setNote(k === null ? null : `Pages from page ${k + 1} on now face the other way: check what sits by the spine.`)
    after?.(now)
  }

  const pick = (id: string, e: { shiftKey: boolean; metaKey: boolean; ctrlKey: boolean }) => {
    if (dragged.current) { dragged.current = false; return }
    if (e.shiftKey && anchor && live.has(anchor)) {
      const a = doc.pages.findIndex((p) => p.id === anchor), b = doc.pages.findIndex((p) => p.id === id)
      setPicked(doc.pages.slice(Math.min(a, b), Math.max(a, b) + 1).map((p) => p.id))
      return
    }
    setAnchor(id)
    if (e.metaKey || e.ctrlKey) setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
    else setPicked([id])
  }

  // ── dragging ────────────────────────────────────────────────────────────
  const tiles = (): Tile[] => [...(scroller.current?.querySelectorAll<HTMLElement>('[data-board-page]') ?? [])].map((el) => {
    const r = el.getBoundingClientRect()
    return { index: Number(el.dataset.boardPage), left: r.left, top: r.top, right: r.right, bottom: r.bottom }
  })
  const press = (ids: string[], e: React.PointerEvent, story = false) => {
    if (e.button !== 0) return
    pending.current = { ids, x: e.clientX, y: e.clientY, story }
  }
  /** Stop a drag without moving anything (Esc, a cancelled pointer). */
  const cancelDrag = () => {
    pending.current = null
    target.current = null
    setDrag(null)
  }
  // The handlers below are added once; they read the newest of these.
  const latest = useRef({ drag, change, cancelDrag })
  useLayoutEffect(() => { latest.current = { drag, change, cancelDrag } })
  useEffect(() => {
    const move = (e: PointerEvent) => {
      const p = pending.current
      if (!p) return
      // No button held: the release went somewhere we didn't hear (outside
      // the window, a pen lifted), so this is not a drag.
      if ((e.buttons & 1) === 0) { latest.current.cancelDrag(); return }
      if (!latest.current.drag) {
        if (Math.hypot(e.clientX - p.x, e.clientY - p.y) < 5) return
        setDrag({ ids: p.ids, story: p.story })
      }
      const sc = scroller.current
      if (sc) {
        const r = sc.getBoundingClientRect()
        if (e.clientY < r.top + 40) sc.scrollTop -= 12
        else if (e.clientY > r.bottom - 40) sc.scrollTop += 12
      }
      const at = slotAt(tiles(), e.clientX, e.clientY)
      target.current = at
      if (label.current) Object.assign(label.current.style, { left: `${e.clientX + 14}px`, top: `${e.clientY + 10}px` })
      if (bar.current) {
        Object.assign(bar.current.style, at
          ? { display: '', left: `${at.x}px`, top: `${at.top - 8}px`, height: `${at.bottom - at.top + 16}px` }
          : { display: 'none' })
      }
    }
    const up = () => {
      const d = latest.current.drag
      const at = target.current
      pending.current = null
      target.current = null
      if (!d) return
      dragged.current = true
      setDrag(null)
      if (at) latest.current.change((x) => moveBlock(x, d.ids, at.slot, at.before ? 'after' : 'before'))
      setTimeout(() => { dragged.current = false }, 0)
    }
    const cancel = () => latest.current.cancelDrag()
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
    }
  }, [])

  const keys = (e: ReactKeyboardEvent) => {
    const t = e.target as HTMLElement
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return
    const mod = e.metaKey || e.ctrlKey
    if (e.key === 'Escape') {
      e.preventDefault()
      if (drag) cancelDrag()
      else if (pairsOpen) setPairsOpen(false)
      else close()
    } else if (mod && e.key.toLowerCase() === 'z') {
      e.preventDefault()
      if (e.shiftKey) store.redo()
      else store.undo()
    } else if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && chosen.length) {
      e.preventDefault()
      change((d) => nudge(d, boundPages(d, chosen), e.key === 'ArrowLeft' ? -1 : 1))
    }
  }

  const blockOf = (id: string) => boundPages(doc, chosen.includes(id) ? chosen : [id])
  return (
    <div ref={root} role="dialog" aria-modal="true" aria-label="Issue board" tabIndex={-1} onKeyDown={keys}
      className="fixed inset-0 z-50 flex flex-col bg-zinc-950 text-zinc-100 outline-none">
      <header className="flex items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-4 py-2">
        <h2 className="text-sm font-semibold">Issue board</h2>
        <span className="text-xs text-zinc-500">
          {doc.pages.length} {doc.pages.length === 1 ? 'page' : 'pages'}
          {allRuns.some((r) => r.section) && ` · ${allRuns.filter((r) => r.section).length} stories`}
        </span>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <button type="button" onClick={() => store.undo()} title="Undo (⌘Z)" aria-label="Undo"
            className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><Undo2 className="h-4 w-4" /></button>
          <button type="button" onClick={() => store.redo()} title="Redo (⇧⌘Z)" aria-label="Redo"
            className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><Redo2 className="h-4 w-4" /></button>
          <label className="flex items-center gap-1.5 text-zinc-300">
            <input type="checkbox" checked={showBeats} onChange={(e) => setShowBeats(e.target.checked)} className="accent-emerald-500" />
            Beats
          </label>
          <div className="flex overflow-hidden rounded-md border border-zinc-700" role="group" aria-label="Page size">
            {(Object.keys(SIZES) as Size[]).map((s) => (
              <button key={s} type="button" onClick={() => setSize(s)} aria-pressed={size === s}
                className={`px-2 py-0.5 ${size === s ? 'bg-zinc-700 text-white' : 'text-zinc-400 hover:text-white'}`}>{s.toUpperCase()}</button>
            ))}
          </div>
          <button type="button" onClick={() => store.set({ guide: 'board' })} title="How the board works" aria-label="How the board works"
            className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><CircleHelp className="h-4 w-4" /></button>
          <button type="button" onClick={close}
            className="rounded-md bg-emerald-600 px-3 py-1 font-medium text-white hover:bg-emerald-500">Back to the pages</button>
        </div>
      </header>
      <Strip doc={doc} allRuns={allRuns} rhythm={rhythm} picked={chosen} onGo={(i) => {
        scroller.current?.querySelector(`[data-board-page="${i}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
        setPicked([doc.pages[i].id])
        setAnchor(doc.pages[i].id)
      }} />
      <div className="flex min-h-9 items-center gap-2 border-b border-zinc-800 px-4 py-1.5 text-xs">
        {chosen.length ? (
          <>
            <span className="text-zinc-400">{chosen.length === 1 ? `Page ${chosenIndex[0] + 1}` : `${chosen.length} pages`}</span>
            <Tool icon={ChevronLeft} label="Move earlier" keys="⌥←" onClick={() => change((d) => nudge(d, boundPages(d, chosen), -1))} />
            <Tool icon={ChevronRight} label="Move later" keys="⌥→" onClick={() => change((d) => nudge(d, boundPages(d, chosen), 1))} />
            <Tool icon={BookmarkPlus} label="Start a story here" disabled={allRuns.some((r) => r.section && r.start === chosenIndex[0])}
              onClick={() => change((d) => startSection(d, chosenIndex[0]))} />
            <div className="relative">
              <Tool icon={Columns2} label="Lay out the spread…" disabled={!pairOk} onClick={() => setPairsOpen((o) => !o)}
                title={pairOk ? undefined : 'Select the two pages of a spread'} />
              {pairsOpen && pairOk && (
                <PairMenu doc={doc} fresh={pairOk.fresh} onPick={(p) => {
                  setPairsOpen(false)
                  const made = applyPair(store.get().doc, chosenIndex, p)
                  if ('problem' in made) { setNote(made.problem); return }
                  change(() => made.doc)
                  const now = store.get().doc
                  setPicked([now.pages[made.left].id, now.pages[made.left + 1].id])
                  setNote(`${p.label} laid out on pages ${made.left + 1}–${made.left + 2}. Fill a frame with a picture to see it.`)
                }} onClose={() => setPairsOpen(false)} />
              )}
            </div>
            <Tool icon={Maximize2} label="Open the page" onClick={() => open(chosenIndex[0])} />
            <button type="button" onClick={() => setPicked([])} className="ml-1 text-zinc-500 hover:text-zinc-200">Clear</button>
          </>
        ) : (
          <span className="text-zinc-500">Click a page to select it (Shift-click for a run of pages), drag pages to put them in order, double-click to open one.</span>
        )}
        {note && (
          <span role="status" className="ml-auto flex items-center gap-2 text-amber-300">
            {note}
            <button type="button" onClick={() => setNote(null)} aria-label="Dismiss" className="text-amber-200/70 hover:text-amber-100"><X className="h-3.5 w-3.5" /></button>
          </span>
        )}
      </div>
      <div ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {!allRuns.some((r) => r.section) && (
          <p className="mb-4 max-w-2xl text-xs leading-relaxed text-zinc-500">
            Mark where each story starts (select its first page, then Start a story here) to see the issue story by story and drag whole stories into order.
          </p>
        )}
        {allRuns.map((run, k) => (
          <RunBlock key={run.section?.id ?? 'front'} run={run} doc={doc} size={size} first={k === 0} last={k === allRuns.length - 1}
            showHeader={allRuns.some((r) => r.section)} rhythm={showBeats ? rhythm : null} issues={issues} picked={chosen}
            onPick={pick} onOpen={open}
            onPress={(id, e) => press(blockOf(id), e)}
            onPressStory={(e) => press(boundPages(doc, doc.pages.slice(run.start, run.end).map((p) => p.id)), e, true)}
            onChange={change} prevStart={allRuns[k - 1]?.section ? allRuns[k - 1].start : null} nextEnd={allRuns[k + 1]?.end ?? null} />
        ))}
      </div>
      {drag && (
        <div ref={bar} aria-hidden className="pointer-events-none fixed z-[60] w-1 -translate-x-1/2 rounded bg-emerald-400"
          style={{ display: 'none' }} />
      )}
      {drag && (
        <div ref={label} className="pointer-events-none fixed z-[60] rounded-md bg-emerald-600 px-2 py-1 text-xs font-medium text-white shadow-lg">
          {drag.story ? 'Moving the story' : `Moving ${drag.ids.length} ${drag.ids.length === 1 ? 'page' : 'pages'}`}
        </div>
      )}
    </div>
  )
}

function Tool({ icon: Icon, label, onClick, disabled, keys, title }: {
  icon: LucideIcon; label: string; onClick: () => void; disabled?: boolean; keys?: string; title?: string
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title ?? (keys ? `${label} (${keys})` : label)}
      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-zinc-200 hover:bg-zinc-800 disabled:cursor-default disabled:text-zinc-600 disabled:hover:bg-transparent">
      <Icon className="h-3.5 w-3.5" />{label}
    </button>
  )
}

/** The issue's rhythm in one line: a block per page, as heavy as the page
 *  looks, spreads together and stories apart. Click one to go to it. */
function Strip({ doc, allRuns, rhythm, picked, onGo }: {
  doc: Doc; allRuns: Run[]; rhythm: PageBeat[]; picked: string[]; onGo: (index: number) => void
}) {
  const pairs = spreads(doc)
  const spreadOf = new Map(pairs.flatMap((s, k) => s.map((p) => [p, k] as const)))
  return (
    <div className="overflow-x-auto border-b border-zinc-800 bg-zinc-900/60 px-4 py-2" aria-label="The rhythm of the issue">
      <div className="flex items-end gap-3">
        {allRuns.map((run) => (
          <div key={run.section?.id ?? 'front'} className="shrink-0">
            <p className="mb-1 max-w-[16rem] truncate text-[10px] uppercase tracking-wider text-zinc-500">{run.section?.name ?? ' '}</p>
            <div className="flex items-end">
              {Array.from({ length: run.end - run.start }, (_, k) => {
                const i = run.start + k
                const b = rhythm[i]
                const tone = Math.round(244 - b.weight * 210)
                const gap = i > run.start && spreadOf.get(i) !== spreadOf.get(i - 1)
                return (
                  <button key={doc.pages[i].id} type="button" onClick={() => onGo(i)}
                    title={`Page ${i + 1} · ${BEAT_LABEL[b.beat]}`} aria-label={`Page ${i + 1}: ${BEAT_LABEL[b.beat]}`}
                    className={`h-7 w-3 shrink-0 ${gap ? 'ml-1' : ''} ${picked.includes(doc.pages[i].id) ? 'outline outline-2 outline-emerald-500' : ''}`}
                    style={{ background: `rgb(${tone},${tone},${tone})` }} />
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RunBlock({ run, doc, size, first, last, showHeader, rhythm, issues, picked, onPick, onOpen, onPress, onPressStory,
  onChange, prevStart, nextEnd }: {
  run: Run; doc: Doc; size: Size; first: boolean; last: boolean; showHeader: boolean; rhythm: PageBeat[] | null
  issues: GutterIssue[]; picked: string[]
  onPick: (id: string, e: { shiftKey: boolean; metaKey: boolean; ctrlKey: boolean }) => void; onOpen: (index: number) => void
  onPress: (id: string, e: React.PointerEvent) => void; onPressStory: (e: React.PointerEvent) => void
  onChange: (fn: (d: Doc) => Doc) => void
  /** The start of the story before (null when the run before isn't a story:
   *  a story never goes ahead of the pages before the first one). */
  prevStart: number | null
  nextEnd: number | null
}) {
  const s = run.section
  // The name being typed (null: not typing, so the story's own name shows).
  const [draft, setDraft] = useState<string | null>(null)
  const ids = doc.pages.slice(run.start, run.end).map((p) => p.id)
  // The run's pages, in the spreads they're in (a story may start or end half way through one).
  const groups = useMemo(() => spreads(doc).map((sp) => sp.filter((p) => p >= run.start && p < run.end)).filter((g) => g.length),
    [doc, run.start, run.end])
  return (
    <section className="mb-7" aria-label={s ? `Story: ${s.name}` : 'Before the first story'}>
      {showHeader && (
        <div className="mb-2 flex items-center gap-2 text-xs">
          {s ? (
            <>
              <span onPointerDown={onPressStory} title="Drag to move the whole story" aria-label="Drag the story"
                className="cursor-grab rounded p-0.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><GripVertical className="h-4 w-4" /></span>
              <input value={draft ?? s.name} onChange={(e) => setDraft(e.target.value)} aria-label="Story name" maxLength={160}
                onBlur={() => { if (draft !== null) onChange((d) => renameSection(d, s.id, draft || s.name)); setDraft(null) }}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); (e.target as HTMLInputElement).blur() } }}
                className="w-56 rounded border border-transparent bg-transparent px-1.5 py-0.5 text-sm font-semibold text-zinc-100 hover:border-zinc-700 focus:border-emerald-500 focus:outline-none" />
            </>
          ) : <span className="px-1.5 text-sm font-semibold text-zinc-400">Before the first story</span>}
          <span className="text-zinc-500">{run.end - run.start === 1 ? `Page ${run.start + 1}` : `Pages ${run.start + 1}–${run.end}`}</span>
          {s && (
            <span className="ml-1 flex">
              <IconButton label="Move the story earlier" disabled={first || prevStart === null}
                onClick={() => prevStart !== null && onChange((d) => moveBlock(d, boundPages(d, ids), prevStart))}><ArrowUp className="h-3.5 w-3.5" /></IconButton>
              <IconButton label="Move the story later" disabled={last || nextEnd === null}
                onClick={() => nextEnd !== null && onChange((d) => moveBlock(d, boundPages(d, ids), nextEnd))}><ArrowDown className="h-3.5 w-3.5" /></IconButton>
              <IconButton label="Remove the story break (its pages join the story before)"
                onClick={() => onChange((d) => removeSection(d, s.id))}><X className="h-3.5 w-3.5" /></IconButton>
            </span>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-5">
        {groups.map((g) => (
          <SpreadCard key={doc.pages[g[0]].id} doc={doc} pages={g} size={size} rhythm={rhythm} picked={picked}
            issues={issues.filter((x) => g.includes(x.page))} onPick={onPick} onOpen={onOpen} onPress={onPress} />
        ))}
      </div>
    </section>
  )
}

function IconButton({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={label} aria-label={label}
      className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white disabled:text-zinc-700 disabled:hover:bg-transparent">{children}</button>
  )
}

/** A spread (or the part of one in this story) drawn by the page renderer,
 *  both pages in one frame so a picture across the spine shows across it. */
function SpreadCard({ doc, pages, size, rhythm, picked, issues, onPick, onOpen, onPress }: {
  doc: Doc; pages: number[]; size: Size; rhythm: PageBeat[] | null; picked: string[]
  issues: GutterIssue[]
  onPick: (id: string, e: { shiftKey: boolean; metaKey: boolean; ctrlKey: boolean }) => void; onOpen: (index: number) => void
  onPress: (id: string, e: React.PointerEvent) => void
}) {
  const { store, fonts } = useCtx()
  const assets = useStudio(store, (s) => s.assets)
  const pw = SIZES[size]
  const scale = pw / doc.size.w
  const ph = doc.size.h * scale
  const els = useRef<(HTMLDivElement | null)[]>([])
  useLayoutEffect(() => {
    const d: Draw = { assets, faces: fonts.book.face, used: new Map(), threads: frameThreads(doc) }
    pages.forEach((p, k) => { const el = els.current[k]; if (el) setHtml(el, pageItemsHtml(doc, p, d)) })
  }, [doc, assets, fonts, pages])
  // A page on its own keeps its side of the spread (the cover on the right).
  const lone = doc.facing && pages.length === 1 ? pageSide(doc, pages[0]) : null
  return (
    <div className="flex flex-col" style={{ paddingLeft: lone === 'right' ? pw : 0, paddingRight: lone === 'left' ? pw : 0 }}>
      <div className="relative">
        <div className="relative overflow-hidden shadow-lg shadow-black/40" style={{ width: pages.length * pw, height: ph, background: doc.paper,
          ['--u' as string]: `${scale}px` }}>
          {pages.map((p, k) => <div key={p} ref={(el) => { els.current[k] = el }} className="absolute top-0" style={{ left: k * pw, width: pw, height: ph }} />)}
          {pages.length === 2 && <div aria-hidden className="absolute top-0 h-full w-px bg-black/15" style={{ left: pw }} />}
        </div>
        {pages.map((p, k) => {
          const id = doc.pages[p].id
          const on = picked.includes(id)
          return (
            <button key={id} type="button" data-board-page={p} aria-label={`Page ${p + 1}`} aria-pressed={on}
              onClick={(e) => onPick(id, e)} onDoubleClick={() => onOpen(p)} onPointerDown={(e) => onPress(id, e)}
              className={`absolute top-0 cursor-grab outline-none ring-inset focus-visible:ring-2 focus-visible:ring-emerald-400 ${on ? 'ring-2 ring-emerald-500' : 'hover:ring-1 hover:ring-zinc-400/60'}`}
              style={{ left: k * pw, width: pw, height: ph }}>
              {doc.paywall_page !== null && p + 1 >= doc.paywall_page && (
                <span className="absolute right-1 top-1 rounded bg-black/60 px-1 text-[9px] text-amber-300" title="For subscribers">$</span>
              )}
            </button>
          )
        })}
        {issues.length > 0 && (
          <span role="img" aria-label={issues.map((x) => x.message).join(' ')} title={issues.map((x) => x.message).join('\n')}
            className="absolute -right-2 -top-2 rounded-full bg-amber-500 p-0.5 text-zinc-950 shadow"><TriangleAlert className="h-3 w-3" /></span>
        )}
      </div>
      <div className="mt-1 flex" style={{ width: pages.length * pw }}>
        {pages.map((p) => {
          const b = rhythm?.[p]
          const Icon = b ? BEAT_ICON[b.beat] : null
          return (
            <div key={p} className="flex min-w-0 items-center gap-2 px-0.5 text-[10px] text-zinc-500" style={{ width: pw }}>
              <span className="font-medium tabular-nums text-zinc-300">{p + 1}</span>
              {b && Icon && <span className="flex min-w-0 items-center gap-0.5 truncate" title={BEAT_LABEL[b.beat]}><Icon className="h-3 w-3 shrink-0" />{SHORT[b.beat]}</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** The paired layouts, drawn as little spreads. */
function PairMenu({ doc, fresh, onPick, onClose }: { doc: Doc; fresh: boolean; onPick: (p: Pair) => void; onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const away = (e: PointerEvent) => { if (box.current && !box.current.contains(e.target as Node)) onClose() }
    window.addEventListener('pointerdown', away)
    return () => window.removeEventListener('pointerdown', away)
  }, [onClose])
  const w = 44, h = (44 * doc.size.h) / doc.size.w, s = w / doc.size.w
  return (
    <div ref={box} role="menu" aria-label="Spread layouts"
      className="absolute left-0 top-full z-10 mt-1 w-80 rounded-lg border border-zinc-700 bg-zinc-900 p-2 shadow-2xl">
      <p className="px-1 pb-2 text-[11px] text-zinc-500">{fresh ? 'These pages have things on them, so the layout comes in as a new spread after them.' : 'Lays out these two pages.'}</p>
      {PAIRS.map((p) => (
        <button key={p.id} type="button" role="menuitem" onClick={() => onPick(p)}
          className="flex w-full items-center gap-3 rounded-md p-1.5 text-left hover:bg-zinc-800">
          <svg width={w * 2} height={h} className="shrink-0 overflow-hidden rounded-sm bg-zinc-100" aria-hidden>
            {p.slots(doc).map((slot, k) => (
              <rect key={k} x={(slot.side * doc.size.w + slot.box.x) * s} y={slot.box.y * s} width={slot.box.w * s} height={slot.box.h * s}
                fill={slot.link !== undefined ? '#6b7280' : '#9ca3af'} />
            ))}
            <line x1={w} x2={w} y1={0} y2={h} stroke="rgba(0,0,0,.25)" />
          </svg>
          <span className="min-w-0">
            <span className="block text-xs font-medium text-zinc-100">{p.label}</span>
            <span className="block text-[11px] leading-snug text-zinc-400">{p.hint}</span>
          </span>
        </button>
      ))}
    </div>
  )
}
