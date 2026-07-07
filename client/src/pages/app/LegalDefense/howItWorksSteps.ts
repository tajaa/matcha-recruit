import { CalendarClock, FileWarning, MessageSquareQuote, Package, Sparkles } from 'lucide-react'
import type { HowItWorksStep } from '../../../components/ui/HowItWorksModal'

export const LEGAL_PILOT_HOW_IT_WORKS_STEPS: HowItWorksStep[] = [
  {
    icon: FileWarning,
    title: 'Open a matter',
    body: 'Pick the matter type — subpoena, class action, EEOC charge, single-plaintiff suit, or '
      + 'regulator audit. Upload the served document and its intake fields (claim, timeframe, scope) '
      + 'are prefilled for you to review before anything runs.',
    detail: 'Each matter is its own workspace — the type shapes the starter prompts the analyst offers.',
  },
  {
    icon: Sparkles,
    title: 'Evidence assembles itself',
    body: 'Evidence is scoped to the matter’s location and state, then drawn automatically from your '
      + 'own systems — IR / OSHA, ER cases, compliance, discipline, training, handbooks and policy '
      + 'acknowledgments, and accommodations. The systems strip shows live counts of what’s in scope.',
    detail: 'Nothing is uploaded record-by-record — it’s pulled from the data you already keep in Matcha.',
  },
  {
    icon: MessageSquareQuote,
    title: 'Ask the analyst — everything is cited',
    body: 'Ask what the record shows for this matter. Every claim traces to a real record id you can '
      + 'open, and anything your records don’t establish lands under open questions.',
    detail: 'Ungrounded claims are dropped by a citation check before you see them — never invented.',
  },
  {
    icon: CalendarClock,
    title: 'Chronology + deadlines',
    body: 'The Chronology tab merges every dated record across your systems into one timeline. The '
      + 'masthead runs a response-deadline countdown, with reminders as the date approaches at 14, 7, '
      + '3, and 1 days out.',
    detail: 'The countdown turns amber inside 7 days and red inside 3 or once overdue.',
  },
  {
    icon: Package,
    title: 'Export the evidence packet',
    body: 'One click renders a defense-memo PDF that cites only real records, plus a ZIP of the '
      + 'underlying source documents for your attorney.',
    detail: 'Shared links are logged with each open for chain of custody — nothing leaves unaccounted for.',
  },
]
