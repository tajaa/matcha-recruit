import { Hammer, DollarSign, Sparkles, Bug, FileText, Wrench, Search, Mail, type LucideIcon } from 'lucide-react'
import type { TaskPriority } from '../types'

export type TemplateFieldKind = 'single' | 'multi' | { picker: string[] }

export interface TemplateField {
  key: string
  label: string
  placeholder: string
  kind: TemplateFieldKind
}

export interface KanbanTemplate {
  key: string
  displayName: string
  icon: LucideIcon
  colorClass: string
  defaultPriority: TaskPriority
  fields: TemplateField[]
  /** One line shown under the form — what has to be true for the card to do
   *  anything (e.g. a Research card only runs once AutoPR owns it). */
  hint?: string
}

/** Built-in ticket starting points — port of the desktop `KanbanTemplate` enum.
 *  `key` is the wire string stored in `mw_tasks.category`; `manual` (blank
 *  task) maps to no template. */
export const KANBAN_TEMPLATES: KanbanTemplate[] = [
  {
    key: 'engineering',
    displayName: 'Engineering',
    icon: Hammer,
    colorClass: 'text-blue-400',
    defaultPriority: 'medium',
    fields: [
      { key: 'context', label: 'Context', placeholder: "What's the problem and why now?", kind: 'multi' },
      { key: 'scope', label: 'Scope', placeholder: '- \n- ', kind: 'multi' },
      { key: 'acceptance', label: 'Acceptance criteria', placeholder: '- ', kind: 'multi' },
      { key: 'technical', label: 'Technical notes', placeholder: 'Approach, affected files/services, risks.', kind: 'multi' },
      { key: 'outofscope', label: 'Out of scope', placeholder: 'What this explicitly does not cover.', kind: 'multi' },
    ],
  },
  {
    key: 'sales',
    displayName: 'Sales',
    icon: DollarSign,
    colorClass: 'text-w-accent',
    defaultPriority: 'medium',
    fields: [
      { key: 'account', label: 'Account', placeholder: 'Company · contact · role', kind: 'single' },
      { key: 'opportunity', label: 'Opportunity', placeholder: 'Deal size · timeline · source', kind: 'single' },
      { key: 'stage', label: 'Stage', placeholder: '', kind: { picker: ['Prospecting', 'Demo', 'Proposal', 'Negotiation', 'Closing'] } },
      { key: 'pain', label: 'Pain / need', placeholder: 'What hurts today?', kind: 'multi' },
      { key: 'nextstep', label: 'Next step', placeholder: 'The single next action.', kind: 'single' },
      { key: 'blockers', label: 'Blockers', placeholder: "What's in the way?", kind: 'multi' },
    ],
  },
  {
    key: 'product',
    displayName: 'Product Feature',
    icon: Sparkles,
    colorClass: 'text-purple-400',
    defaultPriority: 'medium',
    fields: [
      { key: 'problem', label: 'Problem', placeholder: 'Who hurts, and how today?', kind: 'multi' },
      { key: 'userstory', label: 'User story', placeholder: 'As a ___, I want ___ so that ___.', kind: 'multi' },
      { key: 'solution', label: 'Proposed solution', placeholder: '', kind: 'multi' },
      { key: 'metric', label: 'Success metric', placeholder: "How we'll know it worked.", kind: 'single' },
      { key: 'questions', label: 'Open questions', placeholder: '', kind: 'multi' },
      { key: 'outofscope', label: 'Out of scope', placeholder: '', kind: 'multi' },
    ],
  },
  {
    key: 'bug',
    displayName: 'Bug',
    icon: Bug,
    colorClass: 'text-red-400',
    defaultPriority: 'high',
    fields: [
      { key: 'summary', label: 'Summary', placeholder: 'One line.', kind: 'single' },
      { key: 'environment', label: 'Environment', placeholder: 'Build / OS / device', kind: 'single' },
      { key: 'steps', label: 'Steps to reproduce', placeholder: '1. \n2. ', kind: 'multi' },
      { key: 'expected', label: 'Expected', placeholder: 'What should happen.', kind: 'multi' },
      { key: 'actual', label: 'Actual', placeholder: 'What happens instead.', kind: 'multi' },
      { key: 'severity', label: 'Severity / impact', placeholder: '', kind: { picker: ['Critical', 'High', 'Medium', 'Low'] } },
      { key: 'evidence', label: 'Evidence', placeholder: 'Screenshots / logs — drag files onto the ticket.', kind: 'multi' },
    ],
  },
  {
    key: 'general',
    displayName: 'General',
    icon: FileText,
    colorClass: 'text-w-dim',
    defaultPriority: 'medium',
    fields: [{ key: 'description', label: 'Description', placeholder: 'What needs to happen?', kind: 'multi' }],
  },
  {
    key: 'feat',
    displayName: 'Feature',
    icon: Sparkles,
    colorClass: 'text-teal-400',
    defaultPriority: 'medium',
    fields: [
      { key: 'what', label: 'What & why', placeholder: 'The feature and the user value.', kind: 'multi' },
      { key: 'where', label: 'Where in the code', placeholder: 'Files/areas it touches.', kind: 'multi' },
      { key: 'steps', label: 'Steps', placeholder: '- ', kind: 'multi' },
    ],
  },
  {
    key: 'fix',
    displayName: 'Fix',
    icon: Wrench,
    colorClass: 'text-orange-400',
    defaultPriority: 'high',
    fields: [
      { key: 'problem', label: 'Problem', placeholder: "What's broken.", kind: 'multi' },
      { key: 'rootcause', label: 'Root cause', placeholder: 'Where in the code.', kind: 'multi' },
      { key: 'steps', label: 'Steps', placeholder: '- ', kind: 'multi' },
    ],
  },
  {
    // Assigned to the AutoPR bot, a research card runs the research lane
    // (web search + repo clone + attached screenshots) and the report lands
    // under the card's attachments instead of a PR — docs/ops/KANBAN_AUTOPR.md.
    key: 'research',
    displayName: 'Research',
    icon: Search,
    colorClass: 'text-indigo-400',
    defaultPriority: 'medium',
    hint: 'Assign the card to AutoPR on a board granted research; the report lands under its attachments and the card moves to Review.',
    fields: [
      { key: 'subject', label: 'Subject', placeholder: 'One line: what to research.', kind: 'single' },
      { key: 'questions', label: 'Questions to answer', placeholder: '- ', kind: 'multi' },
      { key: 'why', label: 'Why it matters to us', placeholder: 'The decision this informs.', kind: 'multi' },
      { key: 'constraints', label: 'Constraints / scope', placeholder: 'Budget, timeline, what to leave out.', kind: 'multi' },
      { key: 'sources', label: 'Preferred sources', placeholder: 'Vendor docs, a competitor, a paper — or leave blank.', kind: 'single' },
    ],
  },
  {
    // The emails themselves arrive as `email-<id>.md` attachments from
    // Espresso's "Send to board"; assigned to the AutoPR bot on a board granted
    // `email`, the run attaches a triage report and stages reply drafts that a
    // person approves one at a time — docs/ops/KANBAN_AUTOPR.md.
    key: 'email',
    displayName: 'Email',
    icon: Mail,
    colorClass: 'text-cyan-400',
    defaultPriority: 'medium',
    hint: 'Send emails to this card from Espresso, then assign it to AutoPR on a board granted email; it attaches a triage report and stages reply drafts you approve one at a time.',
    fields: [
      { key: 'goal', label: 'What should the agent do with these emails?', placeholder: 'e.g. Summarize and draft replies to anything from customers', kind: 'single' },
      { key: 'instructions', label: 'Instructions', placeholder: 'Which senders matter, what to ignore, what a good reply looks like.', kind: 'multi' },
      { key: 'tone', label: 'Tone', placeholder: '', kind: { picker: ['professional', 'casual', 'brief'] } },
    ],
  },
]

/** Builds the markdown `description` from filled compose-sheet field values.
 *  A lone free-form "description" field (general) is emitted as plain text
 *  with no heading; everything else becomes `## Label\n<value>` blocks. */
export function composeDescription(fields: TemplateField[], values: Record<string, string>): string {
  if (fields.length === 1 && fields[0].key === 'description') {
    return (values.description ?? '').trim()
  }
  const blocks: string[] = []
  for (const f of fields) {
    const v = (values[f.key] ?? '').trim()
    if (!v) continue
    blocks.push(`## ${f.label}\n${v}`)
  }
  return blocks.join('\n\n')
}
