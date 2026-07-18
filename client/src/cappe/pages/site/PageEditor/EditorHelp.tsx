import { useState } from 'react'
import {
  Copy, CopyPlus, GripVertical, HelpCircle, Keyboard, Layers, MousePointerClick,
  Palette, Redo2, Sparkles, Undo2, Wand2,
} from 'lucide-react'

type Tip = { icon: typeof HelpCircle; title: string; body: string; pro?: boolean }
type Group = { heading: string; tips: Tip[] }

const GROUPS: Group[] = [
  {
    heading: 'Whole-site look',
    tips: [
      { icon: Palette, title: 'Theme', body: 'Top bar → Theme. Pick a preset, brand color, fonts, corners, light/dark.' },
      { icon: Sparkles, title: 'Layout & spacing', body: 'Inside Theme → tune type scale, section rhythm, container width, card & gap styling site-wide.', pro: true },
    ],
  },
  {
    heading: 'One section at a time',
    tips: [
      { icon: Wand2, title: 'Design inspector', body: 'Form mode → expand a block → Design. Background, motion, colors, padding, columns, borders, per-section fonts & anchor id.', pro: true },
      { icon: MousePointerClick, title: 'Canvas mode', body: 'Click any element on the page to edit it in place; drag & resize freeform blocks.', pro: true },
    ],
  },
  {
    heading: 'Rearrange & reuse',
    tips: [
      { icon: GripVertical, title: 'Drag to reorder', body: 'Form mode → drag a block’s grip handle (⠿) to move it. Arrows work too.' },
      { icon: CopyPlus, title: 'Duplicate', body: 'Copy a whole section (content + design) right below it.' },
      { icon: Copy, title: 'Copy / paste style', body: 'Copy one section’s design and paste it onto another to match looks fast.', pro: true },
      { icon: Layers, title: 'Saved styles', body: 'Save a theme or a section’s design as a reusable preset — build your own library.', pro: true },
    ],
  },
  {
    heading: 'Safety net',
    tips: [
      { icon: Undo2, title: 'Undo', body: '⌘Z (Ctrl+Z) — steps back through every edit, including theme changes.' },
      { icon: Redo2, title: 'Redo', body: '⌘⇧Z (Ctrl+Shift+Z) — replays what you undid.' },
    ],
  },
]

/** A dismissible "what can I do here?" panel for the page editor. */
export function EditorHelp({ designerUnlocked }: { designerUnlocked: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title="What can I do here?"
        className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-sm font-medium ${open ? 'border-emerald-500 text-emerald-400' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}
      >
        <HelpCircle className="h-4 w-4" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-30 mt-1 max-h-[80vh] w-96 overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-4 shadow-2xl shadow-black/50">
            <div className="mb-3 flex items-center justify-between">
              <p className="flex items-center gap-1.5 text-sm font-semibold text-zinc-100">
                <Sparkles className="h-4 w-4 text-amber-400" /> What you can do here
              </p>
              <span className="flex items-center gap-1 text-[11px] text-zinc-500"><Keyboard className="h-3 w-3" /> ⌘Z / ⌘⇧Z</span>
            </div>

            {!designerUnlocked && (
              <p className="mb-3 rounded-lg border border-dashed border-amber-700/40 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-300/90">
                Items marked <span className="font-semibold">Pro</span> unlock on the Pro/Business plan.
              </p>
            )}

            <div className="space-y-4">
              {GROUPS.map((g) => (
                <section key={g.heading} className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{g.heading}</p>
                  {g.tips.map((t) => (
                    <div key={t.title} className="flex gap-2.5">
                      <t.icon className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-zinc-200">
                          {t.title}
                          {t.pro && <span className="ml-1.5 rounded bg-amber-500/15 px-1 py-0.5 text-[9px] font-bold uppercase text-amber-400">Pro</span>}
                        </p>
                        <p className="text-xs leading-snug text-zinc-400">{t.body}</p>
                      </div>
                    </div>
                  ))}
                </section>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
