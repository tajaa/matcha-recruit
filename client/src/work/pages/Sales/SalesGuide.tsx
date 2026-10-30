import { useEffect, useRef, useState } from 'react'
import {
  ChevronLeft, ChevronRight, Clock, Megaphone, PenLine, Search, Send, ShieldCheck, X, type LucideIcon,
} from 'lucide-react'
import { MAX_BATCH } from './salesLogic'

export const SALES_GUIDE_SEEN_KEY = 'espresso-sales-guide-seen'

type Page = { stage: string; icon: LucideIcon; title: string; body?: string; points?: string[] }

// Every limit and rule here is the server's (docs/ESPRESSO_SALES.md): keep
// them in step when one changes.
const PAGES: Page[] = [
  {
    stage: 'What it is', icon: Megaphone, title: 'Reach the right people, with a reason to talk',
    body: 'A campaign is a list of people to email about what you offer. Espresso can find them, read their own '
      + 'websites, and write each one a short, personal first email. Nothing goes out until you’ve read it and '
      + 'sent it yourself, from your own Gmail.',
  },
  {
    stage: 'How to use it', icon: PenLine, title: 'Set up a campaign',
    points: [
      'Campaigns live in a shared workspace. Pick one you can edit at the top left, or create one from Home first.',
      'Click New campaign. Say who you want to reach and what you offer.',
      'Choose Consulting outreach when you sell advisory work, like HR, compliance or AI reviews. Add your booking link: every email asks for a short call there.',
      'Matcha staff see “Start from Matcha’s consulting offer”. It fills in our four services and the hey-matcha.com booking link; anything you type takes its place.',
      'Add a footer: how to opt out (“reply unsubscribe”) and your business’s postal address. The law requires both, so a campaign can’t send without it.',
    ],
  },
  {
    stage: 'How to use it', icon: Search, title: 'Find people and research them',
    points: [
      'Click Research and draft with Espresso. Its chat opens with the campaign ready; add who you want (“20 growing companies in Texas without an HR lead”) and send.',
      'The first time, turn on Sales in Ask Espresso’s abilities and agree to what it shares. It only works in your private conversation.',
      'In a consulting campaign it looks for businesses with a public reason to talk now: hiring their first HR person, an OSHA inspection, AI in their hiring, a new location. It writes to the owner or leader, and saves why now, which service fits, and a fit from weak to strong, with the pages that show it.',
      'It only saves an email address you typed or one printed on a page it read. It never guesses one.',
      'Have your own list? Click Import and paste emails, one per line, or a CSV with email, name, company and website columns.',
      'It works in batches and tells you how many are left. Ask it to continue the same campaign.',
    ],
  },
  {
    stage: 'How to use it', icon: ShieldCheck, title: 'Read the drafts',
    points: [
      'People who need you come first: messages that couldn’t be confirmed or failed, then drafts. In a consulting campaign the strongest fit leads.',
      'Open someone to see why now, the research, the pages it came from, and the email. Edit it and click Save draft.',
      '“Things to check” means a draft breaks a consulting rule: over 150 words, a link other than your booking link, a number its research doesn’t state, or a line telling them they’re breaking a law. Espresso can’t save drafts like that; this catches your own edits.',
      'Someone asked to be left alone? Click Do not contact. No campaign of yours will email them again.',
      'Drafts Espresso writes while this page is open show up within a minute.',
    ],
  },
  {
    stage: 'How to use it', icon: Send, title: 'Review and send',
    points: [
      `Tick the drafts to send, up to ${MAX_BATCH} at a time, or click Select. Then Review and send.`,
      'You see every email exactly as it goes out, footer included, and who it’s from. Connect Gmail on the Email page first.',
      'Tick that you’ve read them all, then Send. Each person gets their own email, not a group message.',
      'If a draft changed or someone opted out meanwhile, nothing is sent: the review shows the current versions and why, and you read them again.',
    ],
  },
  {
    stage: 'What to expect', icon: Clock, title: 'What to expect',
    points: [
      'Sending is paced to stay inside Gmail’s limits: at most 35 emails an hour and 150 a day, so you can still reply to people. A big batch takes days. It keeps going after you close the page.',
      'Pause stops it; Resume carries on. Release pending drafts takes back what hasn’t gone yet.',
      'If Gmail didn’t confirm one, check your Gmail Sent folder, then mark it sent or put it back to draft.',
      'Espresso never sends anything itself. It finds, researches and drafts; you send.',
      'Your campaigns, contacts and drafts are private to you. Others in the workspace see only a campaign’s name and counts.',
    ],
  },
]

/** How Sales works, a page at a time. Opens on a first visit and from "How it works". */
export default function SalesGuide({ onClose }: { onClose: () => void }) {
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
        aria-label="How Sales works"
        className="flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl border border-w-line bg-w-surface shadow-2xl outline-none sm:rounded-2xl"
      >
        <div className="flex items-center justify-between border-b border-w-line px-5 py-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-w-accent">{page.stage}</p>
            <p className="mt-1 text-xs text-w-dim">Sales · {step + 1} of {PAGES.length}</p>
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
