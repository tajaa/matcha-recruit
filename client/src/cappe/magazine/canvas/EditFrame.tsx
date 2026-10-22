import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { readMessage, sameTarget, type Device, type FrameMessage, type Place } from './bridge'
import { fitFrame } from './fit'

export type { Device } from './bridge'

type Buffer = { html: string; gen: number }
type Buffers = [Buffer | null, Buffer | null]

const other = (i: 0 | 1): 0 | 1 => (i === 0 ? 1 : 0)

/** The page being edited, in a frame that runs its own scripts (the
 *  magazine's book and the editor's, render/assets/editor.js) but not as our
 *  origin (`sandbox="allow-scripts"`, no same-origin), so nothing on it can
 *  reach the dashboard's session. It speaks only by messages: what it sends
 *  is checked (bridge.ts) and only the shown frame is listened to.
 *
 *  A new render loads in a second, hidden frame, which turns to `place` (the
 *  selection, else the spread) and then takes the first one's place, so the
 *  page never flashes back to its start. While words are typed the frame is
 *  never replaced: a render that arrives then waits until typing stops, and
 *  one already loading is dropped once words are typed (it was made before
 *  them; the render of the new words follows). */
export default function EditFrame({ html, place, stories, device, title, onMessage }: {
  html: string
  /** Where to turn after a reload, and what to select. A change of target
   *  from outside (the panel, the outline) selects it on the page too. */
  place: Place
  /** The stories on the page, by the id the page uses. */
  stories: ReadonlySet<string>
  device: Device
  title: string
  /** Every checked message from the shown page. */
  onMessage: (m: FrameMessage) => void
}) {
  const pane = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const frame0 = useRef<HTMLIFrameElement>(null)
  const frame1 = useRef<HTMLIFrameElement>(null)
  const [buffers, setBuffers] = useState<Buffers>([null, null])
  const [front, setFront] = useState<0 | 1 | null>(null)
  const [editing, setEditing] = useState(false)
  const [loaded, setLoaded] = useState('')
  // Each render's own number, never reused (a dropped one stays dropped).
  const [gens, setGens] = useState(0)

  // A render not yet on a page goes into the frame not being shown, unless
  // words are being typed (then it waits for them to stop).
  if (html && !editing && html !== loaded) {
    setLoaded(html)
    if (front === null || buffers[front]?.html !== html) {
      const back: 0 | 1 = front === null ? 0 : other(front)
      const buf = { html, gen: gens + 1 }
      setGens(gens + 1)
      setBuffers(back === 0 ? [buf, buffers[1]] : [buffers[0], buf])
    }
  }

  const latest = useRef({ place, stories, onMessage, front, buffers })
  useLayoutEffect(() => { latest.current = { place, stories, onMessage, front, buffers } })
  const typing = useRef(false)
  // Renders made before words were typed on the shown page: never shown.
  const stale = useRef(new Set<number>())
  // The target the page last told us it selected: not sent back to it.
  const heard = useRef<Place['target']>(null)

  useEffect(() => {
    const win = (i: 0 | 1) => (i === 0 ? frame0 : frame1).current?.contentWindow
    const goto = (i: 0 | 1) => {
      const { target, spread } = latest.current.place
      win(i)?.postMessage({ type: 'mz-goto', target, spread }, '*')
    }
    const onMsg = (e: MessageEvent) => {
      const i = e.source && e.source === win(0) ? 0 : e.source && e.source === win(1) ? 1 : null
      if (i === null) return
      const msg = readMessage(e.data, { stories: latest.current.stories })
      if (!msg) return
      const { front: shown, buffers: bufs } = latest.current
      if (bufs[i] && stale.current.has(bufs[i]!.gen)) return
      if (i !== shown) {
        // The frame being loaded: turn it to the place, then show it, unless
        // typing started on the shown one meanwhile.
        if (msg.type === 'mz-ready') goto(i)
        else if (msg.type === 'mz-shown' && !typing.current) setFront(i)
        return
      }
      if (msg.type === 'mz-ready') { goto(i); return }
      if (msg.type === 'mz-edit') {
        // Words typed here: a render still loading behind predates them.
        const back = other(i)
        const behind = bufs[back]
        if (behind && behind.gen > (bufs[i]?.gen ?? 0) && !stale.current.has(behind.gen)) {
          stale.current.add(behind.gen)
          setBuffers((bs) => (bs[back]?.gen === behind.gen ? (back === 0 ? [null, bs[1]] : [bs[0], null]) : bs))
        }
      }
      if (msg.type === 'mz-editing') {
        typing.current = msg.on
        setEditing(msg.on)
        // A render that finished loading while words were typed: show it now.
        const back = other(i)
        if (!msg.on && (bufs[back]?.gen ?? 0) > (bufs[i]?.gen ?? 0) && !stale.current.has(bufs[back]!.gen)) goto(back)
      }
      if (msg.type === 'mz-select') heard.current = msg.target
      latest.current.onMessage(msg)
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  // The pane's size: the page is laid out at a reader's window and fitted to it.
  useEffect(() => {
    const el = pane.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.round(e.contentRect.width), h: Math.round(e.contentRect.height) }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Selected from outside: select it on the shown page as well.
  useEffect(() => {
    if (front === null || sameTarget(place.target, heard.current)) return
    heard.current = place.target
    const win = (front === 0 ? frame0 : frame1).current?.contentWindow
    win?.postMessage({ type: 'mz-select', target: place.target || { kind: 'none' } }, '*')
  }, [place.target, front])

  const fit = fitFrame(device, size.w, size.h)
  const layout = fit ? `${device}:${fit.width}x${Math.round(fit.height)}` : device

  // A page laid out at a new size (the phone, a wider pane) has its pages
  // set again: turn back to what is selected once the book has refitted.
  useEffect(() => {
    if (front === null) return
    const t = setTimeout(() => {
      const target = latest.current.place.target
      const win = (front === 0 ? frame0 : frame1).current?.contentWindow
      if (target) win?.postMessage({ type: 'mz-goto', target, spread: latest.current.place.spread }, '*')
    }, 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new layout turns back; `front` changing has its own goto
  }, [layout])

  const phone = device === 'phone'
  return (
    <div ref={pane} className={`relative h-full min-h-0 w-full overflow-hidden ${phone ? 'bg-zinc-900' : ''}`}>
      <div className={`absolute ${phone ? 'box-content overflow-hidden rounded-[2rem] border-zinc-700 shadow-2xl' : ''} ${fit ? '' : 'inset-0'}`}
        style={fit ? {
          left: fit.left, top: fit.top, width: fit.width, height: fit.height, borderWidth: fit.bezel,
          transform: fit.scale === 1 ? undefined : `scale(${fit.scale})`, transformOrigin: '0 0',
        } : undefined}>
        {buffers.map((b, i) => (
          <iframe key={b ? b.gen : `empty-${i}`} ref={i === 0 ? frame0 : frame1} title={i === front ? title : `${title} (loading)`}
            srcDoc={b?.html || ''} sandbox="allow-scripts" aria-hidden={i !== front} tabIndex={i === front ? 0 : -1}
            className={`absolute inset-0 h-full w-full border-0 bg-white ${i === front ? '' : 'pointer-events-none invisible'}`} />
        ))}
      </div>
      {front === null && (
        <p className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">Setting the pages…</p>
      )}
      {fit && fit.scale < 0.999 && (
        <p className="pointer-events-none absolute bottom-2 right-3 rounded bg-black/60 px-2 py-0.5 text-[11px] text-zinc-300">
          {Math.round(fit.scale * 100)}% of a reader’s {phone ? 'phone' : 'window'}
        </p>
      )}
    </div>
  )
}
