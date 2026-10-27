import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft, ExternalLink, Images, Library, Link2, Loader2, Maximize, Minus, Pencil, Plus, StickyNote, Trash2, Upload, X,
} from 'lucide-react'
import LibraryPanel from '../magazine/library/LibraryPanel'
import type { CappeAsset } from '../types'
import { boardsApi, fileUrl, type Board, type Pin } from './api'
import BoardCanvas, { type Pending } from './BoardCanvas'
import { cascade, fitView, layoutOf, raise, toBoard, zoomAt, type Point, type View } from './board'
import { MAX_FILE_BYTES, NOTE_COLORS, TITLE_MAX, type NoteColor } from './limits'
import { fromTransfer, pinnable, tooBig, typingIn, type Pasted } from './paste'
import { NOTE_BG } from './look'
import ToLibraryForm from './ToLibraryForm'

const DRAFT = 'draft-note'
const SAVE_AFTER_MS = 500

function message(e: unknown, fallback: string) {
  return e instanceof Error && e.message ? e.message : fallback
}

function draftNote(boardId: string, at: Point, z: number): Pin {
  const now = new Date().toISOString()
  return {
    id: DRAFT, board_id: boardId, kind: 'note', x: at.x, y: at.y, w: 220, h: 180, rotation: 0, z, asset_id: null,
    in_library: false, src: null, full: null, file_url: null, alt: null, filename: null, mime: null, size_bytes: 0,
    width: null, height: null, note: '', color: 'yellow', url: null, title: null, description: null, site_name: null,
    created_at: now, updated_at: now,
  }
}

/** `sites/:siteId/boards/:boardId` — one mood board. Pin anything that
 *  inspires: drop or paste photos, screenshots and files, paste a link, write a
 *  note, or bring a picture from the library. Pins go anywhere, over or beside
 *  each other. */
export default function BoardPage() {
  const { siteId, boardId } = useParams<{ siteId: string; boardId: string }>()
  const [board, setBoard] = useState<Board | null>(null)
  const [pins, setPins] = useState<Pin[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [view, setView] = useState<View>({ x: 48, y: 48, zoom: 1 })
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [selected, setSelected] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [pending, setPending] = useState<Pending[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [dialog, setDialog] = useState<null | 'link' | 'library' | 'to-library' | 'picture'>(null)
  const pinsRef = useRef(pins)
  useLayoutEffect(() => { pinsRef.current = pins })
  // The first view shows everything, once both the pins and the canvas's size are known.
  const fit = useRef<{ pins: Pin[] | null; w: number; h: number; done: boolean }>({ pins: null, w: 0, h: 0, done: false })
  const fitOnce = useCallback(() => {
    const f = fit.current
    if (f.done || !f.pins || !f.w) return
    f.done = true
    setView(fitView(f.pins, f.w, f.h))
  }, [])
  const dirty = useRef(new Set<string>())
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const counter = useRef(0)

  useEffect(() => {
    if (!siteId || !boardId) return
    let alive = true
    boardsApi.get(siteId, boardId)
      .then((res) => {
        if (!alive) return
        setBoard(res.board)
        setPins(res.pins)
        fit.current.pins = res.pins
        fitOnce()
      })
      .catch((e) => { if (alive) setLoadError(message(e, 'This board didn’t load.')) })
    return () => { alive = false }
  }, [siteId, boardId, fitOnce])

  const sized = useCallback((w: number, h: number) => {
    setSize({ w, h })
    Object.assign(fit.current, { w, h })
    fitOnce()
  }, [fitOnce])

  const flush = useCallback(() => {
    if (saveTimer.current) { clearTimeout(saveTimer.current); saveTimer.current = null }
    if (!siteId || !boardId || !dirty.current.size) return
    const ids = dirty.current
    dirty.current = new Set()
    const items = pinsRef.current.filter((p) => ids.has(p.id) && p.id !== DRAFT).map(layoutOf)
    if (!items.length) return
    boardsApi.layout(siteId, boardId, items)
      .catch((e) => setNotice(message(e, 'Where things are wasn’t saved. Move it again to retry.')))
  }, [siteId, boardId])

  useEffect(() => () => flush(), [flush])

  const markDirty = (ids: string[], later = false) => {
    ids.forEach((id) => dirty.current.add(id))
    if (later) {
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(flush, SAVE_AFTER_MS)
    }
  }

  const patchLocal = useCallback((id: string, patch: Partial<Pin>) => {
    setPins((list) => list.map((p) => (p.id === id ? { ...p, ...patch } : p)))
    dirty.current.add(id)
  }, [])

  const press = useCallback((id: string | null) => {
    setSelected(id)
    if (!id) return
    const r = raise(pinsRef.current, id)
    if (r.changed.length) {
      pinsRef.current = r.pins
      setPins(r.pins)
      r.changed.forEach((p) => dirty.current.add(p.id))
    }
  }, [])

  const centre = useCallback((): Point => toBoard(view, size.w / 2, size.h / 2), [view, size])
  // Things added one after another without moving the board step down and
  // right from the middle of the view, so none lands on the one before.
  const placedHere = useRef(0)
  useEffect(() => { placedHere.current = 0 }, [view])
  const nextSpot = (box = { w: 240, h: 180 }): Point => cascade(centre(), placedHere.current++, box)

  const landed = (pin: Pin) => {
    setPins((list) => [...list.filter((p) => p.id !== pin.id), pin])
    setBoard((b) => (b ? { ...b, pin_count: b.pin_count + 1 } : b))
  }

  const withPending = async (label: string, at: Point, work: () => Promise<Pin>) => {
    const key = `p${counter.current++}`
    setPending((list) => [...list, { key, label, x: at.x, y: at.y }])
    try {
      landed(await work())
    } catch (e) {
      setNotice(message(e, `“${label}” couldn’t be pinned.`))
    } finally {
      setPending((list) => list.filter((p) => p.key !== key))
    }
  }

  const addFiles = (files: File[], at: Point) => {
    if (!siteId || !boardId) return
    const refused = files.filter((f) => !pinnable(f) || tooBig(f))
    if (refused.length) {
      setNotice(`${refused.map((f) => f.name).join(', ')}: pin photos, screenshots, PDFs, Word or Excel files, or text, up to ${MAX_FILE_BYTES / (1024 * 1024)} MB each.`)
    }
    files.filter((f) => pinnable(f) && !tooBig(f)).forEach((file, i) => {
      const spot = cascade(at, i)
      void withPending(file.name || 'Screenshot', spot, () => boardsApi.upload(siteId, boardId, spot, file))
    })
  }

  const addLink = (url: string, at: Point) => {
    if (!siteId || !boardId) return
    void withPending(url, at, () => boardsApi.addLink(siteId, boardId, at, url))
  }

  const addNoteText = (text: string, at: Point) => {
    if (!siteId || !boardId) return
    void withPending(text.slice(0, 40), at, () => boardsApi.addNote(siteId, boardId, at, text))
  }

  const add = (what: Pasted, at: Point) => {
    if (what.kind === 'files') addFiles(what.files, at)
    else if (what.kind === 'link') addLink(what.url, at)
    else addNoteText(what.text, at)
  }

  const startNote = () => {
    const at = nextSpot({ w: 220, h: 180 })
    const top = pinsRef.current.reduce((m, p) => Math.max(m, p.z), 0)
    setPins((list) => [...list.filter((p) => p.id !== DRAFT), draftNote(boardId ?? '', at, top + 1)])
    setSelected(DRAFT)
    setEditing(DRAFT)
  }

  const noteDone = (id: string, text: string) => {
    setEditing(null)
    const words = text.trim()
    const pin = pinsRef.current.find((p) => p.id === id)
    if (!pin || !siteId || !boardId) return
    if (id === DRAFT) {
      setPins((list) => list.filter((p) => p.id !== DRAFT))
      setSelected(null)
      const at = { x: pin.x, y: pin.y }
      if (words) void withPending(words.slice(0, 40), at, () => boardsApi.addNote(siteId, boardId, at, words, pin.color ?? 'yellow'))
      return
    }
    if (!words || words === pin.note) return
    patchLocal(id, { note: words })
    boardsApi.update(siteId, boardId, id, { note: words }).catch((e) => setNotice(message(e, 'The note wasn’t saved.')))
  }

  const recolour = (pin: Pin, color: NoteColor) => {
    if (!siteId || !boardId || pin.id === DRAFT) return patchLocal(pin.id, { color })
    patchLocal(pin.id, { color })
    boardsApi.update(siteId, boardId, pin.id, { color }).catch((e) => setNotice(message(e, 'The colour wasn’t saved.')))
  }

  const remove = (pin: Pin) => {
    if (!siteId || !boardId) return
    if (pin.id !== DRAFT && !window.confirm('Take this off the board?')) return
    setPins((list) => list.filter((p) => p.id !== pin.id))
    setSelected(null)
    if (pin.id === DRAFT) return
    setBoard((b) => (b ? { ...b, pin_count: Math.max(0, b.pin_count - 1) } : b))
    boardsApi.removePin(siteId, boardId, pin.id).catch((e) => {
      setNotice(message(e, 'That wasn’t removed.'))
      setPins((list) => [...list, pin])
    })
  }

  const open = (pin: Pin) => {
    setSelected(pin.id)
    if (pin.kind === 'image') setDialog('picture')
    else if (pin.kind === 'link' && pin.url) window.open(pin.url, '_blank', 'noopener,noreferrer')
    else if (pin.kind === 'file' && pin.file_url) window.open(fileUrl(pin.file_url) ?? undefined, '_blank', 'noopener,noreferrer')
  }

  // Paste anywhere on the page (not into a field): screenshots, links, words.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (dialog || editing || typingIn(e.target)) return
      const what = fromTransfer(e.clipboardData)
      if (!what) return
      e.preventDefault()
      add(what, nextSpot())
    }
    document.addEventListener('paste', onPaste)
    return () => document.removeEventListener('paste', onPaste)
  })

  // Keys for the selected pin: Delete takes it off, arrows nudge it, Esc lets go.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (dialog || editing || typingIn(e.target)) return
      const pin = pinsRef.current.find((p) => p.id === selected)
      if (e.key === 'Escape') { setSelected(null); return }
      if (!pin) return
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); remove(pin); return }
      const step = e.shiftKey ? 10 : 1
      const nudge = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key]
      if (!nudge) return
      e.preventDefault()
      patchLocal(pin.id, { x: pin.x + nudge[0], y: pin.y + nudge[1] })
      markDirty([pin.id], true)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  const selectedPin = useMemo(() => pins.find((p) => p.id === selected) ?? null, [pins, selected])

  if (!siteId || !boardId) return null
  if (loadError) {
    return (
      <div className="p-8 text-sm">
        <p role="alert" className="text-red-300">{loadError}</p>
        <Link to={`/cappe/sites/${siteId}/boards`} className="mt-3 inline-block text-emerald-400 hover:text-emerald-300">Back to mood boards</Link>
      </div>
    )
  }

  const rename = (title: string) => {
    const t = title.trim()
    if (!board || !t || t === board.title) return
    setBoard({ ...board, title: t })
    boardsApi.rename(siteId, boardId, t).catch((e) => setNotice(message(e, 'The name wasn’t saved.')))
  }

  const zoomBy = (factor: number) => setView((v) => zoomAt(v, factor, size.w / 2, size.h / 2))

  return (
    <div className="flex h-full min-h-[480px] flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-900 px-4 py-2.5">
        <Link to={`/cappe/sites/${siteId}/boards`} aria-label="All mood boards" className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        {board ? (
          <input key={board.id} defaultValue={board.title} maxLength={TITLE_MAX} aria-label="Board name"
            onBlur={(e) => rename(e.currentTarget.value)} onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
            className="min-w-0 max-w-xs flex-1 rounded-md border border-transparent bg-transparent px-2 py-1 text-base font-semibold text-zinc-50 outline-none hover:border-zinc-700 focus:border-emerald-500" />
        ) : <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />}
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <ToolButton icon={<StickyNote className="h-4 w-4" />} label="Note" onClick={startNote} />
          <ToolButton icon={<Link2 className="h-4 w-4" />} label="Link" onClick={() => setDialog('link')} />
          <ToolButton icon={<Upload className="h-4 w-4" />} label="Upload" onClick={() => fileInput.current?.click()} />
          <ToolButton icon={<Images className="h-4 w-4" />} label="From library" onClick={() => setDialog('library')} />
          <input ref={fileInput} type="file" multiple hidden aria-label="Files to pin"
            accept="image/jpeg,image/png,image/gif,image/webp,application/pdf,.doc,.docx,.xls,.xlsx,.txt,.md,.csv"
            onChange={(e) => { addFiles(Array.from(e.currentTarget.files ?? []), nextSpot()); e.currentTarget.value = '' }} />
          <span className="mx-1 h-5 w-px bg-zinc-800" aria-hidden />
          <ToolButton icon={<Minus className="h-4 w-4" />} label="Zoom out" iconOnly onClick={() => zoomBy(1 / 1.25)} />
          <span className="w-10 text-center text-xs tabular-nums text-zinc-400">{Math.round(view.zoom * 100)}%</span>
          <ToolButton icon={<Plus className="h-4 w-4" />} label="Zoom in" iconOnly onClick={() => zoomBy(1.25)} />
          <ToolButton icon={<Maximize className="h-4 w-4" />} label="Show everything" iconOnly onClick={() => setView(fitView(pins, size.w, size.h))} />
        </div>
      </div>

      {selectedPin && selectedPin.id !== DRAFT && editing !== selectedPin.id && (
        <SelectionBar pin={selectedPin} onOpen={() => open(selectedPin)} onEdit={() => setEditing(selectedPin.id)}
          onColour={(c) => recolour(selectedPin, c)} onToLibrary={() => setDialog('to-library')} onRemove={() => remove(selectedPin)} />
      )}
      {notice && (
        <div role="status" className="flex items-start gap-2 border-b border-amber-500/20 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          <p className="flex-1">{notice}</p>
          <button type="button" aria-label="Dismiss" onClick={() => setNotice(null)} className="text-amber-300 hover:text-amber-100"><X className="h-4 w-4" /></button>
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        <BoardCanvas
          pins={pins} pending={pending} view={view} onView={setView} selected={selected} editing={editing}
          onPress={press} onChange={patchLocal} onRelease={flush} onOpen={open} onEdit={(id) => { setSelected(id); setEditing(id) }}
          onNoteDone={noteDone} onDropped={add} onSize={sized}
        />
        {board && !pins.length && !pending.length && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6">
            <div className="max-w-sm text-center text-sm text-zinc-400">
              <p className="text-base font-medium text-zinc-200">Pin anything that inspires you</p>
              <p className="mt-1">Drop photos, screenshots and documents here, paste with ⌘V, or add a note or a link above.
                Put things side by side or on top of each other: drag them anywhere.</p>
            </div>
          </div>
        )}
      </div>

      {dialog === 'link' && (
        <Modal title="Pin a link" onClose={() => setDialog(null)}>
          <LinkForm onAdd={(url) => { setDialog(null); addLink(url, nextSpot({ w: 280, h: 200 })) }} />
        </Modal>
      )}
      {dialog === 'library' && (
        <Modal title="Pin a picture from your library" wide onClose={() => setDialog(null)}>
          <LibraryPanel siteId={siteId} onPick={(a: CappeAsset) => {
            setDialog(null)
            const at = nextSpot({ w: 280, h: 200 })
            void withPending(a.alt || 'Picture', at, () => boardsApi.addAsset(siteId, boardId, at, a.id))
          }} />
        </Modal>
      )}
      {dialog === 'to-library' && selectedPin && (
        <Modal title="Add to your library" onClose={() => setDialog(null)}>
          <ToLibraryForm siteId={siteId} pin={selectedPin} onCancel={() => setDialog(null)}
            onDone={(pin) => { setPins((list) => list.map((p) => (p.id === pin.id ? pin : p))); setDialog(null) }} />
        </Modal>
      )}
      {dialog === 'picture' && selectedPin?.kind === 'image' && (
        <Modal title={selectedPin.alt || selectedPin.filename || 'Picture'} wide onClose={() => setDialog(null)}>
          <img src={fileUrl(selectedPin.full || selectedPin.src) ?? undefined} alt={selectedPin.alt || ''} className="mx-auto max-h-[70vh] rounded" />
          {selectedPin.url && (
            <a href={selectedPin.url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-emerald-400 hover:text-emerald-300">
              <ExternalLink className="h-3.5 w-3.5" />Where it came from
            </a>
          )}
        </Modal>
      )}
    </div>
  )
}

function ToolButton({ icon, label, onClick, iconOnly = false }: {
  icon: ReactNode; label: string; onClick: () => void; iconOnly?: boolean
}) {
  return (
    <button type="button" onClick={onClick} aria-label={iconOnly ? label : undefined} title={label}
      className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-sm text-zinc-200 hover:bg-zinc-800">
      {icon}{!iconOnly && <span className="hidden sm:inline">{label}</span>}
    </button>
  )
}

function SelectionBar({ pin, onOpen, onEdit, onColour, onToLibrary, onRemove }: {
  pin: Pin
  onOpen: () => void
  onEdit: () => void
  onColour: (c: NoteColor) => void
  onToLibrary: () => void
  onRemove: () => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-900/60 px-4 py-2 text-sm">
      {pin.kind === 'note' ? (
        <>
          <button type="button" onClick={onEdit} className="inline-flex items-center gap-1 text-zinc-200 hover:text-white"><Pencil className="h-3.5 w-3.5" />Edit</button>
          <div className="flex items-center gap-1" role="group" aria-label="Note colour">
            {NOTE_COLORS.map((c) => (
              <button key={c} type="button" aria-label={c} aria-pressed={pin.color === c} onClick={() => onColour(c)}
                className={`h-5 w-5 rounded-full ${NOTE_BG[c]} ${pin.color === c ? 'ring-2 ring-emerald-400 ring-offset-1 ring-offset-zinc-900' : ''}`} />
            ))}
          </div>
        </>
      ) : (
        <button type="button" onClick={onOpen} className="inline-flex items-center gap-1 text-zinc-200 hover:text-white">
          <ExternalLink className="h-3.5 w-3.5" />{pin.kind === 'image' ? 'View' : 'Open'}
        </button>
      )}
      {pin.kind === 'image' && !pin.in_library && (
        <button type="button" onClick={onToLibrary} className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300">
          <Library className="h-3.5 w-3.5" />Add to library
        </button>
      )}
      {pin.kind === 'image' && pin.in_library && <span className="text-xs text-zinc-500">In your library</span>}
      <button type="button" onClick={onRemove} className="ml-auto inline-flex items-center gap-1 text-red-400 hover:text-red-300">
        <Trash2 className="h-3.5 w-3.5" />Remove
      </button>
    </div>
  )
}

function LinkForm({ onAdd }: { onAdd: (url: string) => void }) {
  const [url, setUrl] = useState('')
  return (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (url.trim()) onAdd(url.trim()) }}>
      <input autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" aria-label="Link"
        className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500" />
      <button type="submit" disabled={!url.trim()} className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">Pin</button>
    </form>
  )
}

function Modal({ title, children, onClose, wide = false }: {
  title: string; children: ReactNode; onClose: () => void; wide?: boolean
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 p-4" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-modal="true" aria-label={title}
        className={`max-h-[90vh] w-full overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-5 ${wide ? 'max-w-4xl' : 'max-w-md'}`}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="truncate text-base font-semibold text-zinc-50">{title}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="text-zinc-400 hover:text-zinc-200"><X className="h-4 w-4" /></button>
        </div>
        {children}
      </div>
    </div>
  )
}
