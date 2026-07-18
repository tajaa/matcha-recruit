import { Hammer, DollarSign, Sparkles, Bug, FileText, Wrench, type LucideIcon } from 'lucide-react'
import type { TaskPriority } from '../types/matchaWork'

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
