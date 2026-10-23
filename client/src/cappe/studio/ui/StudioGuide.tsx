import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, X } from 'lucide-react'
import { COMMANDS } from './commands'
import { GUIDE, MORE_KEYS } from './guideContent'

const FOCUSABLE = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** How the Studio works, a section at a time, with the contents down the
 *  side. While it's open it keeps the keyboard: nothing behind it (the
 *  Studio, the Picture Editor) acts on a key, and Tab never leaves it. */
export default function StudioGuide({ section, onClose }: { section: string; onClose: () => void }) {
  const [at, setAt] = useState(() => Math.max(0, GUIDE.findIndex((s) => s.id === section)))
  const page = GUIDE[at]
  const Icon = page.icon
  const last = at === GUIDE.length - 1
  const box = useRef<HTMLDivElement>(null)

  // Focus starts in the guide, stays in it (Tab goes round its own buttons),
  // and goes back where it was when the guide closes.
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    box.current?.focus()
    const keepIn = (e: FocusEvent) => {
      if (box.current && e.target instanceof Node && !box.current.contains(e.target)) box.current.focus()
    }
    document.addEventListener('focusin', keepIn)
    return () => {
      document.removeEventListener('focusin', keepIn)
      if (opener?.isConnected) opener.focus()
    }
  }, [])
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      e.stopPropagation()
      if (e.key === 'Tab') {
        const inside = Array.from(box.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
        const now = document.activeElement
        const i = inside.findIndex((el) => el === now)
        e.preventDefault()
        if (!inside.length) { box.current?.focus(); return }
        const next = i < 0 ? (e.shiftKey ? inside.length - 1 : 0) : (i + (e.shiftKey ? -1 : 1) + inside.length) % inside.length
        inside[next].focus()
        return
      }
      if (e.key === 'Escape') { e.preventDefault(); onClose() }
      else if (e.key === 'ArrowRight') setAt((k) => Math.min(GUIDE.length - 1, k + 1))
      else if (e.key === 'ArrowLeft') setAt((k) => Math.max(0, k - 1))
    }
    // Capture, on the window: the Studio's and the Picture Editor's own keys never see it.
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={box} tabIndex={-1} role="dialog" aria-modal="true" aria-label="How the Studio works"
        className="studio-dark flex h-[min(620px,100%)] w-full max-w-4xl overflow-hidden rounded-xl border border-zinc-700 bg-zinc-950 text-zinc-100 shadow-2xl outline-none">
        <nav aria-label="Contents" className="hidden w-56 shrink-0 overflow-y-auto border-r border-zinc-800 bg-zinc-900 p-3 sm:block">
          <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">How the Studio works</p>
          {GUIDE.map((s, k) => {
            const head = k === 0 || GUIDE[k - 1].group !== s.group ? s.group : null
            const I = s.icon
            return (
              <div key={s.id}>
                {head && <p className="mt-3 px-2 pb-1 text-[10px] uppercase tracking-wider text-zinc-500">{head}</p>}
                <button type="button" onClick={() => setAt(k)} aria-current={k === at ? 'step' : undefined}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-[12px] ${k === at ? 'bg-emerald-500/15 text-emerald-200' : 'text-zinc-300 hover:bg-zinc-800 hover:text-white'}`}>
                  <I className="h-3.5 w-3.5 shrink-0" />{s.title}
                </button>
              </div>
            )
          })}
        </nav>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
            <span className="text-[11px] text-zinc-500">{page.group} · {at + 1} of {GUIDE.length}</span>
            <button type="button" onClick={onClose} aria-label="Close the guide" className="rounded p-1 text-zinc-400 hover:bg-zinc-800 hover:text-white"><X className="h-4 w-4" /></button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-500/30 bg-emerald-500/10">
                <Icon className="h-4 w-4 text-emerald-300" />
              </span>
              <h2 className="text-lg font-semibold">{page.title}</h2>
            </div>
            {page.body && <p className="mt-4 text-sm leading-relaxed text-zinc-300">{page.body}</p>}
            {page.points && (
              <ul className="mt-4 space-y-2.5">
                {page.points.map((p) => (
                  <li key={p} className="flex gap-2.5 text-sm leading-relaxed text-zinc-300">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />{p}
                  </li>
                ))}
              </ul>
            )}
            {page.id === 'keys' && <Shortcuts />}
          </div>
          <div className="flex items-center justify-between border-t border-zinc-800 px-5 py-3">
            <button type="button" onClick={() => setAt(at - 1)} disabled={at === 0}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-40">
              <ArrowLeft className="h-3 w-3" />Back
            </button>
            {last ? (
              <button type="button" onClick={onClose} className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500">Start designing</button>
            ) : (
              <button type="button" onClick={() => setAt(at + 1)} aria-label={`Next: ${GUIDE[at + 1].title}`}
                className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-500">
                {GUIDE[at + 1].title}<ArrowRight className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

/** Every command with a key, as the menus show them, then the keys that aren't commands. */
function Shortcuts() {
  const rows: [string, string][] = [
    ...COMMANDS.filter((c) => c.keys).map((c): [string, string] => [c.keys!, c.label]),
    ...MORE_KEYS,
  ]
  return (
    <table className="mt-4 w-full text-sm">
      <tbody>
        {rows.map(([keys, what]) => (
          <tr key={keys + what} className="border-b border-zinc-800/70">
            <td className="w-44 py-1.5 pr-4"><kbd className="rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 font-sans text-[12px] text-zinc-200">{keys}</kbd></td>
            <td className="py-1.5 text-zinc-300">{what}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
