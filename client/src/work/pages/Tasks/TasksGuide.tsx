import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, ClipboardList, Clock, Lock, MessageSquarePlus, SlidersHorizontal, X, type LucideIcon } from 'lucide-react'

export const TASKS_GUIDE_SEEN_KEY = 'espresso-tasks-guide-seen'

/** Tasks one person can have running (`MAX_LIVE` in agent_tasks/enqueue.py). */
const RUNNING_AT_ONCE = 2

type Page = { stage: string; icon: LucideIcon; title: string; body?: string; points?: string[] }

// The macOS app's Tasks guide (`FeatureGuides.swift`), worded for the web page.
const PAGES: Page[] = [
  {
    stage: 'What it is', icon: ClipboardList, title: 'Send Espresso off to do the legwork',
    body: 'Ask for something that takes real searching, like “find me a one-bedroom in SF under $3,500 that takes dogs.” '
      + 'Espresso works on it in the background and keeps what it finds here, with where each fact came from.',
  },
  {
    stage: 'How to use it', icon: MessageSquarePlus, title: 'Start one',
    points: [
      'Type what you want in the box at the top of Tasks and click Ask Espresso. Espresso’s chat opens with your words ready to send. Asking in the chat directly works too.',
      'Espresso picks the kind of task from what you ask: Products, Apartments, Places, or Research for anything else. Each asks its own questions, like beds and a move-in date for an apartment.',
      'An apartment search takes a rent range and a place to measure from, like “at least 10 miles north or south of Lady Bird Lake.” Each building shows the rents its floor plans list (it fits when any plan is in your range), its distance and direction from there, and any move-in specials its page advertises.',
      'If it needs more, like a move-in date, it posts a short form in the chat. Fill it in, add files if it asks for them, and start it. Typing your answer works too.',
      'Job searches live here too: click New job search, or ask Espresso for one.',
      'Running tasks show as a count next to Tasks in the sidebar, with a dot when one needs you.',
    ],
  },
  {
    stage: 'How to use it', icon: SlidersHorizontal, title: 'Work with what it found',
    points: [
      'Open a finding to see its facts. Verified ones show the quote and the page they came from.',
      'Where a building lists its homes online, open it to see each one: unit, floor, beds and baths, size, rent, move-in date, lease, any special, its floor plan and a 3D tour. The list says how many fit, like “3 of 18 homes fit.”',
      'Save, Choose or Dismiss findings, add notes, or Ask Espresso about one.',
      'Buy on a product shows exactly what will happen first, then gives you the store’s checkout with it in the cart (your saved shipping address filled in, if you have one). Done lists what you did with it.',
      'Apply on a home gives you the application its page links to, or the listing when it has none. You fill it in there.',
      'Refine changes what it’s looking for. Search more looks for more like these. Make document writes it all into a note in Journals.',
    ],
  },
  {
    stage: 'What to expect', icon: Clock, title: 'What to expect',
    points: [
      'A task takes a few minutes and runs on our servers, so you can close this page. When it’s done you get a notification and an email with what it found; if it needs you, a notification.',
      'It never pays, orders, books, applies or contacts anyone on its own. Buy takes you to the store’s checkout and Apply to the application; you review, fill in and pay there.',
      'Distances are straight-line miles from where Google Maps or the US Census puts each place. A home it couldn’t place is Unconfirmed, not ruled out.',
      'Only a fact it verified can rule a finding out. One it couldn’t check is marked Unconfirmed and ranked after the confirmed ones.',
      'A building fits only when one of its homes meets all your limits at once, not one home’s rent with another’s bedrooms. A special like “6 weeks free” counts: the net rent spreads the free weeks over the lease, and a home whose net rent is in your budget fits. “Up to” specials don’t count.',
      'Many buildings’ sites don’t list their homes one by one, or turn away anything but a person’s browser. Those show the rents their floor plans give instead.',
      `Up to ${RUNNING_AT_ONCE} tasks run at once.`,
    ],
  },
  {
    stage: 'What to expect', icon: Lock, title: 'Units and privacy',
    points: [
      'A new task uses units from your monthly allowance, shown at the bottom of the task list. Search more uses 1; Refine and Make document are free. A task that fails doesn’t count.',
      'Deleting a task removes what it found, but it still counts for the month.',
      'Files you give it are kept privately: only you can open them, and only Espresso’s AI models read them.',
    ],
  },
]

/** How Tasks works, a page at a time. Opens on a first visit and from "How it works". */
export default function TasksGuide({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0)
  const page = PAGES[step]
  const last = step === PAGES.length - 1
  const Icon = page.icon
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    dialogRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/70 sm:items-center sm:px-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="How Tasks works"
        className="flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-w-line bg-w-surface shadow-2xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-center justify-between border-b border-w-line px-5 py-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-w-accent">{page.stage}</p>
            <p className="mt-1 text-xs text-w-dim">Tasks · {step + 1} of {PAGES.length}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1.5 text-w-faint hover:bg-w-surface2 hover:text-w-text" aria-label="Close">
            <X size={17} />
          </button>
        </div>

        <div className="flex gap-1.5 px-5 pt-4" aria-hidden>
          {PAGES.map((p, i) => <span key={p.title} className={`h-1.5 rounded-full transition-all ${i === step ? 'w-8 bg-w-accent' : i < step ? 'w-1.5 bg-w-accent' : 'w-1.5 bg-w-surface2'}`} />)}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
          <div className="mb-4 flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-w-line bg-w-surface2/70"><Icon size={18} className="text-w-accent" /></span>
            <h2 className="text-lg font-semibold text-w-text">{page.title}</h2>
          </div>
          {page.body && <p className="text-sm leading-6 text-w-dim">{page.body}</p>}
          {page.points && (
            <ul className="space-y-2">
              {page.points.map((point) => (
                <li key={point} className="flex gap-3 text-sm leading-6 text-w-dim">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-w-accent/15 text-[11px] font-semibold text-w-accent">✓</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-w-line px-5 py-4">
          {step > 0
            ? <button type="button" onClick={() => setStep((s) => s - 1)} className="inline-flex items-center gap-1 text-sm text-w-dim hover:text-w-text"><ChevronLeft size={16} />Back</button>
            : <button type="button" onClick={onClose} className="text-sm text-w-dim hover:text-w-text">Skip</button>}
          {last
            ? <button type="button" onClick={onClose} className="rounded-lg bg-w-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-w-accent-hi">Got it</button>
            : <button type="button" onClick={() => setStep((s) => s + 1)} className="inline-flex items-center gap-1 rounded-lg bg-w-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-w-accent-hi">Next <ChevronRight size={16} /></button>}
        </div>
      </div>
    </div>
  )
}
