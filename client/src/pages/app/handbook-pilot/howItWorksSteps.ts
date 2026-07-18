import { CheckCircle2, FileCheck, MessageSquarePlus, Pencil, Scale } from 'lucide-react'
import type { HowItWorksStep } from '../../../components/ui/HowItWorksModal'

export const HOW_IT_WORKS_STEPS: HowItWorksStep[] = [
  {
    icon: MessageSquarePlus,
    title: 'Start a session',
    body: 'Describe what you need — a new policy, or expanding an existing handbook section.',
    detail: 'Give it a clear goal up front and the first draft lands closer to final.',
  },
  {
    icon: Scale,
    title: 'Grounded on YOUR jurisdictions',
    body: 'Pulls the actual jurisdiction requirements for your work locations, your industry baseline, '
      + 'and your existing handbook/policies — not generic boilerplate.',
    detail: 'Change where you operate and the grounding changes with you — no stale template library to maintain.',
  },
  {
    icon: FileCheck,
    title: 'Cited drafts',
    body: 'Every enforceable clause traces to a real jurisdiction id; anything uncited is dropped '
      + 'automatically before you ever see it.',
    detail: 'A citation check runs on every turn — invented legal references never reach the draft.',
  },
  {
    icon: Scale,
    title: 'Close the gaps',
    body: 'The Requirements panel lists every requirement that applies to your locations and which '
      + 'ones no draft cites yet. Hit Draft on one and the pilot picks it up.',
    detail: 'Uncited doesn\'t mean non-compliant — your existing handbook may already cover it. Run a '
      + 'compliance scan to grade the drafted language itself.',
  },
  {
    icon: Pencil,
    title: 'Review & edit',
    body: 'Tweak the drafted language before anything becomes real.',
    detail: 'Edit the title and body inline; nothing is committed while you refine it.',
  },
  {
    icon: CheckCircle2,
    title: 'Promote',
    body: 'Turns a reviewed draft into a real draft handbook section or standalone policy — it never '
      + 'auto-publishes; you finish publishing through the normal Handbooks/Policies flow.',
    detail: 'Promoted items land as drafts in Handbooks/Policies, ready for your normal review-and-publish step.',
  },
]
