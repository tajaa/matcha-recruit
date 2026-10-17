import { useEffect, useRef, useState } from 'react'
import { Briefcase, ChevronLeft, ChevronRight, Clock, DollarSign, FileText, Lock, PlusCircle, X, type LucideIcon } from 'lucide-react'

type Page = { stage: string; icon: LucideIcon; title: string; body?: string; points?: string[]; numbered?: boolean }

// The macOS app's Job search guide (`FeatureGuides.swift`), worded for the web page.
const PAGES: Page[] = [
  {
    stage: 'What it is', icon: Briefcase, title: 'A serious search from one sentence',
    body: 'Tell Espresso what you’re after, like “COO roles across the US — I care most about salary, bonus and equity.” '
      + 'It searches live job listings, ranks them by what matters to you, and drafts how to go after the best ones.',
  },
  {
    stage: 'How to use it', icon: PlusCircle, title: 'Start a search', numbered: true,
    points: [
      'In Tasks, click New job search. Your searches are listed there with your other tasks.',
      'Describe the job in your own words. Add titles, places, remote or on-site, and a minimum base if you have one.',
      'Choose whether Espresso may use your saved résumé to judge fit and write the drafts.',
      'Read what’s shared and where, tick I agree, then Start search.',
      'If you have Tasks, you can also ask Espresso in its chat. It asks for what it needs with a short form.',
    ],
  },
  {
    stage: 'What to expect', icon: Clock, title: 'Give it a few minutes',
    points: [
      'It searches the web and employers’ own job boards, scores each job’s fit out of 5 and drops what doesn’t fit.',
      'It keeps only jobs that are still posted. If you named places, a job must be within 50 miles of one of them, or remote if you’ll take remote.',
      'It reads and ranks your strongest matches first: 4/5 and 5/5 (3/5 if nothing scores that high). Show more at 3/5 adds the next tier for free, once a search, and Show weaker matches lists the rest.',
      'You can close this page while it works. The list fills in as it goes, Cancel stops it, and when it’s done you get an email with the top jobs.',
      'Ranking follows What matters. Change the weights to re-rank anytime.',
    ],
  },
  {
    stage: 'What to expect', icon: DollarSign, title: 'Pay is only what’s posted',
    points: [
      'Every pay figure comes from the posting itself, with the line it was quoted from.',
      'A job that doesn’t post pay says Not posted. It’s never guessed or counted as zero, and it ranks after jobs that do.',
    ],
  },
  {
    stage: 'What to expect', icon: FileText, title: 'Drafts you send yourself',
    points: [
      'The top jobs get an approach plan, an outreach email, answers to the application’s questions and a cover letter.',
      'Draft email puts a job’s outreach email in your Gmail drafts. Fill in anything in [brackets], then send it from Gmail. The job shows when it’s sent.',
      'Edit draft finds the existing draft in Gmail. If you already sent or deleted it in Gmail itself, the job says so and makes nothing. Click Draft email if you want a new one.',
      'Nothing is ever sent, applied for or submitted for you.',
      'Work authorization, sponsorship, clearance, demographic and upload questions are left for you to answer.',
      'Once a search finishes, Draft or Redraft any job from its page. Re-ranking and redrafting don’t use up a search.',
    ],
  },
  {
    stage: 'What to expect', icon: Lock, title: 'Limits and privacy',
    points: [
      'Each new search uses units from your monthly allowance, shown at the bottom of Tasks.',
      'Search terms go to the job listing services. Your résumé is used only by Espresso’s AI models, never sent to job sites.',
      'Deleting a search removes its jobs and drafts, but it still counts for the month.',
    ],
  },
]

/** How Job search works, a page at a time. Opens on a first visit and from "How it works". */
export default function JobSearchGuide({ onClose }: { onClose: () => void }) {
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
        aria-label="How Job search works"
        className="flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-w-line bg-w-surface shadow-2xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-center justify-between border-b border-w-line px-5 py-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-w-accent">{page.stage}</p>
            <p className="mt-1 text-xs text-w-dim">Job search · {step + 1} of {PAGES.length}</p>
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
              {page.points.map((point, i) => (
                <li key={point} className="flex gap-3 text-sm leading-6 text-w-dim">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-w-accent/15 text-[11px] font-semibold text-w-accent">
                    {page.numbered ? i + 1 : '✓'}
                  </span>
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
