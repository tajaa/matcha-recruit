import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { followedLink, prepareFrame, wireBook, type BookControl, type BookState } from './book'

const ARROW = 'flex h-9 w-9 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-100 '
  + 'transition hover:bg-zinc-800 disabled:invisible'

/** A magazine page in a script-less frame (`sandbox="allow-same-origin"`),
 *  its pages turned from out here: the arrows, the page count and the keys
 *  are ours, because Safari won't run anything we attach inside the frame
 *  (`book.ts`). A link the page follows comes back as `onLink` with its path
 *  on the magazine (`/stories/low-tide`), and the page is put back. */
export default function BookFrame({
  html, title, onLink, openExternal = false, prepare, keys = false, keepPlace = false, spread, className = '', style,
}: {
  html: string
  title: string
  /** Links on the page; without it they do nothing. */
  onLink?: (path: string) => void
  /** Web links open in a new tab. */
  openExternal?: boolean
  /** Change the page before it is wired (a button of our own, say). */
  prepare?: (doc: Document) => void
  /** ←/→ and Page Up/Down on this window turn the pages. */
  keys?: boolean
  /** A new page opens on the spread the last one was showing (a live preview). */
  keepPlace?: boolean
  /** Turn to this spread whenever it changes (an editor showing what is being edited). */
  spread?: number
  className?: string
  style?: CSSProperties
}) {
  const frame = useRef<HTMLIFrameElement>(null)
  const book = useRef<BookControl | null>(null)
  const place = useRef(0)
  const [state, setState] = useState<BookState | null>(null)
  // A followed link leaves the frame on a blank page; a new key puts the page back.
  const [generation, setGeneration] = useState(0)
  const latest = useRef({ onLink, prepare, keepPlace, openExternal })
  useEffect(() => { latest.current = { onLink, prepare, keepPlace, openExternal } })

  useEffect(() => () => book.current?.dispose(), [])
  useEffect(() => {
    if (spread === undefined) return
    place.current = spread
    book.current?.go(spread)
  }, [spread])

  const onLoad = () => {
    const el = frame.current
    book.current?.dispose()
    book.current = null
    const link = followedLink(el?.contentWindow)
    if (link !== null) {
      setState(null)
      setGeneration((g) => g + 1)
      latest.current.onLink?.(link)
      return
    }
    const doc = el?.contentDocument
    if (!doc) return
    latest.current.prepare?.(doc)
    prepareFrame(doc, { follow: !!latest.current.onLink, openExternal: latest.current.openExternal })
    book.current = wireBook(doc, {
      start: latest.current.keepPlace ? place.current : 0,
      onState: (s) => { place.current = s.spread; setState(s) },
    })
    if (!book.current) setState(null)
  }

  useEffect(() => {
    if (!keys) return
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (e.metaKey || e.ctrlKey || e.altKey || t?.closest?.('input,textarea,select,[contenteditable="true"]')) return
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); book.current?.turn(1) }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); book.current?.turn(-1) }
    }
    window.addEventListener('keydown', onKey)
    // A click on the page puts the keyboard in the frame, where we can't
    // hear it: hand it back.
    const back = setInterval(() => { if (document.activeElement === frame.current) frame.current?.blur() }, 250)
    return () => { window.removeEventListener('keydown', onKey); clearInterval(back) }
  }, [keys])

  const turns = state && state.spreads > 1 ? state : null
  return (
    <div className={`flex flex-col ${className}`}>
      <iframe key={generation} ref={frame} title={title} srcDoc={html} onLoad={onLoad}
        sandbox={openExternal ? 'allow-same-origin allow-popups allow-popups-to-escape-sandbox' : 'allow-same-origin'}
        className="w-full flex-1 bg-white" style={style} />
      {/* Under the page, never over it: the arrows and the page count. */}
      <div className="flex shrink-0 items-center justify-center gap-4 border-t border-zinc-800 bg-zinc-950 px-3 py-2">
        <button type="button" aria-label="Previous page" disabled={!turns || turns.spread <= 0}
          onClick={() => book.current?.turn(-1)} className={ARROW}>
          <ChevronLeft className="h-5 w-5" />
        </button>
        <p aria-live="polite" className="min-w-[9rem] text-center text-[11px] uppercase tracking-[.16em] text-zinc-400">
          {turns?.folio || '\u00a0'}
        </p>
        <button type="button" aria-label="Next page" disabled={!turns || turns.spread >= turns.spreads - 1}
          onClick={() => book.current?.turn(1)} className={ARROW}>
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>
    </div>
  )
}
