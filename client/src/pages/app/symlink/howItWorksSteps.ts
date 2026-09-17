import { KeyRound, MessageSquare, Plus, ShieldCheck } from 'lucide-react'
import type { HowItWorksStep } from '../../../components/ui/HowItWorksModal'

/**
 * Sym-link onboarding walkthrough. Same shell + shape every Pilot feature uses
 * (see legal-defense/howItWorksSteps.ts), shown once per browser via
 * `useShowOnce('symlink')` and reopenable from the page's "?" button.
 *
 * Two lines here are load-bearing claims about how the feature actually
 * behaves — keep them true or change them together with the code: the passcode
 * is deliberately absent from the invite email (services/symlink/CLAUDE.md),
 * and completion is decided server-side from the link's spec, never by the
 * model (chat.is_complete).
 */
export const SYMLINK_HOW_IT_WORKS_STEPS: HowItWorksStep[] = [
  {
    icon: Plus,
    title: 'Create the request',
    body: 'Pick what you need — a credential or document, a manager review, an info update, or a custom '
      + 'checklist you write yourself. Each kind already knows what it has to collect; add or edit items '
      + 'and mark them required or optional.',
    detail: 'For a credential upload, link it to an employee — that is whose record the document lands on.',
  },
  {
    icon: KeyRound,
    title: 'They unlock it with your passcode',
    body: 'The recipient gets a single-purpose link and enters your company passcode to open it. You will '
      + 'find the current code under Passcode; it rotates weekly, and anyone already mid-task keeps working '
      + 'when it changes.',
    detail: 'The passcode is deliberately left out of the invite email — a link carrying its own key is not '
      + 'a second factor. Send it in person, by text, or in a channel.',
  },
  {
    icon: MessageSquare,
    title: 'A guided chat collects everything',
    body: 'Instead of a form they can half-fill, the link asks one question at a time until it has every '
      + 'required answer and file, then shows them an editable review of everything before it is sent.',
    detail: 'It cannot finish early: completeness is decided on the server from your spec, not by the '
      + 'assistant, so a missing expiry date or an unattached document blocks submission.',
  },
  {
    icon: ShieldCheck,
    title: 'You review, then apply',
    body: 'A submission arrives as Needs review with nothing yet written to your records. Applying is what '
      + 'commits it — a credential is filed to the employee, an info update patches their contact details, '
      + 'a review or custom request is kept as a record. Or reject it with a note.',
    detail: 'Links expire on their own, and you can resend or revoke one at any time from its detail page.',
  },
]
