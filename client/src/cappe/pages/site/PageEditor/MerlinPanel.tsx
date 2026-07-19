import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Check, Loader2, Lock, Sparkles, X } from 'lucide-react'
import { usePremium } from './DesignPrimitives'
import { dHead } from './styles'
import { MERLIN_TIERS, type MerlinTier, type useMerlin } from './useMerlin'

/** Toolbar toggle only — the panel itself is `MerlinDrawer`, rendered by
 *  index.tsx as a flex sibling of the preview/canvas (same docking pattern as
 *  ThemeMenu/ThemeDrawer), so its width composes into the layout row instead
 *  of overlaying it. */
export function MerlinButton({ open, setOpen }: { open: boolean; setOpen: (fn: (o: boolean) => boolean) => void }) {
  return (
    <button
      onClick={() => setOpen((o) => !o)}
      className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${open ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}
    >
      <Sparkles className="h-4 w-4" /> Merlin
    </button>
  )
}

export function MerlinDrawer({ merlin }: { merlin: ReturnType<typeof useMerlin> }) {
  const premium = usePremium()
  const { open, setOpen, messages, send, sending, error, tier, setTier } = merlin
  const [input, setInput] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  // A locked tier could still be sitting in localStorage from a lapsed plan —
  // show it selected but send lite, matching what the server would clamp to.
  const tierLocked = (t: MerlinTier) => !premium && MERLIN_TIERS.find((x) => x.id === t)?.premium === true

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(() => false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  if (!open) return null

  const submit = () => {
    if (sending || !input.trim()) return
    send(input)
    setInput('')
  }

  return (
    <div className="flex w-80 shrink-0 flex-col overflow-hidden border-l border-zinc-800 bg-zinc-900">
      <div className="flex items-center justify-between border-b border-zinc-800 p-3">
        <p className={dHead}>Merlin</p>
        <button onClick={() => setOpen(() => false)} className="rounded p-0.5 text-zinc-500 hover:text-zinc-200" title="Close (Esc)"><X className="h-4 w-4" /></button>
      </div>

      <>
          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-3">
            {messages.length === 0 && (
              <p className="text-xs text-zinc-500">
                Tell Merlin what to change — "make the hero darker", "add an FAQ section", "swap the brand color for something warmer".
                Edits apply live to the preview; nothing saves until you hit Save, and ⌘Z undoes a whole turn at once.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'ml-6' : 'mr-2'}>
                <div className={`rounded-lg px-3 py-2 text-sm ${m.role === 'user' ? 'bg-emerald-500/10 text-emerald-100' : 'bg-zinc-800 text-zinc-100'}`}>
                  {m.content}
                </div>
                {m.role === 'assistant' && m.tier && (
                  <p className="mt-0.5 text-[10px] text-zinc-600">
                    {MERLIN_TIERS.find((t) => t.id === m.tier)?.label ?? m.tier}
                  </p>
                )}
                {m.results && m.results.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {m.results.map((r, j) => (
                      <span
                        key={j}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                          r.ok ? 'border-emerald-700/40 bg-emerald-500/[0.08] text-emerald-300' : 'border-amber-700/40 bg-amber-500/[0.08] text-amber-300'
                        }`}
                      >
                        {r.ok ? <Check className="h-2.5 w-2.5" /> : <AlertCircle className="h-2.5 w-2.5" />}
                        {r.summary}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {sending && (
              <div className="mr-2 flex items-center gap-2 rounded-lg bg-zinc-800 px-3 py-2 text-sm text-zinc-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
              </div>
            )}
            {error && <p className="text-xs text-red-400">{error}</p>}
          </div>

          <div className="border-t border-zinc-800 p-3">
            {/* Model tier. Lite is free on every plan; the rest need Pro/Business.
                Locked options stay visible (and selectable) — the server clamps
                to lite — so the upgrade path is discoverable instead of hidden. */}
            <div className="mb-2 flex rounded-lg border border-zinc-700 p-0.5">
              {MERLIN_TIERS.map((t) => {
                const locked = tierLocked(t.id)
                return (
                  <button
                    key={t.id}
                    onClick={() => setTier(t.id)}
                    title={locked ? `${t.hint} — Pro/Business only` : t.hint}
                    className={`flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium ${
                      tier === t.id ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {locked && <Lock className="h-2.5 w-2.5" />} {t.label}
                  </button>
                )
              })}
            </div>
            {tierLocked(tier) && (
              <p className="mb-2 text-[11px] text-amber-300/90">
                {MERLIN_TIERS.find((t) => t.id === tier)?.label} needs Pro or Business — running on Lite.
              </p>
            )}
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
                placeholder="Describe a change…"
                rows={2}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <button
              onClick={submit}
              disabled={sending || !input.trim()}
              className="mt-2 w-full rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
            >
              {sending ? 'Sending…' : 'Send'}
            </button>
          </div>
      </>
    </div>
  )
}
