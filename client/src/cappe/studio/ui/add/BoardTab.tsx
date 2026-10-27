import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, FileText, Globe, Loader2, Lock } from 'lucide-react'
import { boardsApi, fileUrl, type Board, type BoardDetail, type Pin } from '../../../boards/api'
import { NOTE_BG } from '../../../boards/look'
import ToLibraryForm from '../../../boards/ToLibraryForm'
import { cappePath } from '../../../host'
import type { CappeAsset } from '../../../types'
import { useCtx } from '../context'
import { endDrag, startDrag } from './drag'
import { addPicture } from './place'

const HINT = 'text-[11px] leading-snug text-zinc-500'
const chosenKey = (siteId: string) => `cappe-studio-board:${siteId}`

function remembered(siteId: string): string | null {
  try { return localStorage.getItem(chosenKey(siteId)) } catch { return null }
}

function remember(siteId: string, boardId: string) {
  try { localStorage.setItem(chosenKey(siteId), boardId) } catch { /* private window: forget it */ }
}

function message(e: unknown, fallback: string) {
  return e instanceof Error && e.message ? e.message : fallback
}

/** The site's mood boards beside the pages, to design from. A library
 *  picture on a board goes onto the page like any of Yours (click, or drag
 *  onto a frame); a pinned reference picture is added to the library first,
 *  with the owner's word that they may use it. Notes, links and files are
 *  there to read and open. */
export default function BoardTab() {
  const c = useCtx()
  const [boards, setBoards] = useState<Board[] | null>(null)
  const [boardId, setBoardId] = useState('')
  const [detail, setDetail] = useState<BoardDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [promoting, setPromoting] = useState<Pin | null>(null)

  useEffect(() => {
    let alive = true
    boardsApi.list(c.siteId).then((list) => {
      if (!alive) return
      setBoards(list)
      const keep = remembered(c.siteId)
      setBoardId(list.find((b) => b.id === keep)?.id ?? list[0]?.id ?? '')
    }, (e) => { if (alive) setError(message(e, 'Your mood boards didn’t load.')) })
    return () => { alive = false }
  }, [c.siteId])

  useEffect(() => {
    if (!boardId) return
    let alive = true
    boardsApi.get(c.siteId, boardId).then((d) => { if (alive) { setDetail(d); setError(null) } },
      (e) => { if (alive) setError(message(e, 'That board didn’t load.')) })
    return () => { alive = false }
  }, [c.siteId, boardId])

  // A board chosen a moment ago shows Loading… until its own answer comes.
  const shown = detail?.board.id === boardId ? detail : null
  const assets = useMemo(() => new Map((shown?.assets ?? []).map((a) => [a.id, a])), [shown])
  const pins = useMemo(() => [...(shown?.pins ?? [])].sort((a, b) => b.z - a.z), [shown])

  const choose = (id: string) => {
    setBoardId(id)
    setPromoting(null)
    remember(c.siteId, id)
  }

  const promoted = (pin: Pin, asset: CappeAsset) => {
    setDetail((d) => d && {
      ...d, pins: d.pins.map((p) => (p.id === pin.id ? pin : p)), assets: [...d.assets.filter((a) => a.id !== asset.id), asset],
    })
    setPromoting(null)
    addPicture(c, asset)
  }

  const boardHref = cappePath(`/cappe/sites/${c.siteId}/boards${boardId ? `/${boardId}` : ''}`)
  if (boards === null) {
    return error
      ? <p role="alert" className="text-xs text-red-300">{error}</p>
      : <p className="flex items-center gap-1.5 text-xs text-zinc-400"><Loader2 className="h-3 w-3 animate-spin" />Loading…</p>
  }
  if (!boards.length) {
    return (
      <div className="space-y-2 text-xs text-zinc-400">
        <p>Mood boards hold what inspires a story: photos, screenshots, documents, notes and links, pinned side by side or on top of each other.</p>
        <a href={boardHref} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300">
          Start a mood board<ExternalLink className="h-3 w-3" />
        </a>
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label className="min-w-0 flex-1">
          <span className="sr-only">Mood board</span>
          <select value={boardId} onChange={(e) => choose(e.target.value)}
            className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-100 focus:border-emerald-500 focus:outline-none">
            {boards.map((b) => <option key={b.id} value={b.id}>{b.title}</option>)}
          </select>
        </label>
        <a href={boardHref} target="_blank" rel="noopener noreferrer" title="Open the board"
          className="rounded p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white"><ExternalLink className="h-4 w-4" /><span className="sr-only">Open the board</span></a>
      </div>
      {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
      {!shown && !error && <p className="flex items-center gap-1.5 text-xs text-zinc-400"><Loader2 className="h-3 w-3 animate-spin" />Loading…</p>}
      {promoting && (
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
          {promoting.src && <img src={fileUrl(promoting.src) ?? undefined} alt="" className="mb-2 max-h-32 rounded object-contain" />}
          <ToLibraryForm dark siteId={c.siteId} pin={promoting} onDone={promoted} onCancel={() => setPromoting(null)} />
        </div>
      )}
      {shown && !pins.length && <p className="text-xs text-zinc-500">Nothing pinned on this board yet.</p>}
      {shown && !!pins.length && (
        <>
          <p className={HINT}>Click a library picture to add it to the page, or drag it onto a frame. A <Lock className="inline h-3 w-3" aria-label="locked" /> picture is private reference: add it to your library first.</p>
          <ul className="columns-2 gap-2 [&>li]:mb-2" aria-label="Pinned on this board">
            {pins.map((pin) => <li key={pin.id} className="break-inside-avoid"><PinTile pin={pin} asset={pin.asset_id ? assets.get(pin.asset_id) : undefined} onPromote={() => setPromoting(pin)} /></li>)}
          </ul>
        </>
      )}
    </div>
  )
}

function PinTile({ pin, asset, onPromote }: { pin: Pin; asset?: CappeAsset; onPromote: () => void }) {
  const c = useCtx()
  const tile = 'block w-full overflow-hidden rounded-md text-left'
  if (pin.kind === 'image' && asset) {
    return (
      <button type="button" draggable onDragStart={(e) => startDrag(e, { kind: 'asset', asset })} onDragEnd={endDrag}
        onClick={() => addPicture(c, asset)} aria-label={`Add ${asset.alt || 'this picture'}`}
        className={`${tile} bg-zinc-800 hover:ring-2 hover:ring-emerald-500`}>
        <img src={fileUrl(pin.src) ?? undefined} alt="" loading="lazy" draggable={false} className="w-full" />
      </button>
    )
  }
  if (pin.kind === 'image') {
    return (
      <button type="button" onClick={onPromote} aria-label="Add this reference picture to your library"
        className={`${tile} relative bg-zinc-800 hover:ring-2 hover:ring-emerald-500`}>
        <img src={fileUrl(pin.src) ?? undefined} alt="" loading="lazy" draggable={false} className="w-full opacity-80" />
        <span className="absolute left-1 top-1 rounded bg-zinc-950/70 p-1 text-zinc-300"><Lock className="h-3 w-3" aria-hidden /></span>
      </button>
    )
  }
  if (pin.kind === 'note') {
    return <p className={`${tile} whitespace-pre-wrap break-words p-2 text-[11px] leading-snug ${NOTE_BG[pin.color ?? 'yellow']}`}>{pin.note}</p>
  }
  const href = pin.kind === 'link' ? pin.url : fileUrl(pin.file_url)
  return (
    <a href={href ?? undefined} target="_blank" rel="noopener noreferrer"
      className={`${tile} border border-zinc-800 bg-zinc-950/60 hover:border-emerald-500`}>
      {pin.src && <img src={fileUrl(pin.src) ?? undefined} alt="" loading="lazy" className="w-full" />}
      <span className="flex items-start gap-1 p-2 text-[11px] text-zinc-300">
        {pin.kind === 'link' ? <Globe className="mt-px h-3 w-3 shrink-0" aria-hidden /> : <FileText className="mt-px h-3 w-3 shrink-0" aria-hidden />}
        <span className="line-clamp-2">{pin.title || pin.filename || pin.url}</span>
      </span>
    </a>
  )
}
