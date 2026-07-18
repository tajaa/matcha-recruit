/**
 * Hard-coded starter templates for matcha-work projects.
 *
 * Each template is a pre-defined section skeleton spawned at create time
 * (see `WorkSidebar.handleCreateProject` → `createProjectNew(..., template)`
 * → backend `project_service.create_project` → seeds `mw_projects.sections`).
 *
 * `content` strings are sanitized HTML using `[bracketed placeholders]` —
 * the existing `PlaceholderHighlight` TipTap extension styles them orange,
 * and the AI chat's `extractPlaceholderValue` flow lets a single user
 * message (e.g. "Acme Corp · B2B SaaS · $25k Q3") fan-fill placeholders
 * across every section.
 *
 * Mirrored on the backend in `server/app/matcha/services/project_service.py`
 * (PROJECT_TEMPLATE_SECTIONS) — keep the two in sync until we DB-back this.
 */

export interface ProjectTemplateSection {
  title: string
  content: string
}

export interface ProjectTemplate {
  id: string
  label: string
  description: string
  /** lucide-react icon name */
  icon: string
  sections: ProjectTemplateSection[]
}

export const PROJECT_TEMPLATES: ProjectTemplate[] = [
  {
    id: 'proposal',
    label: 'Proposal',
    description: 'Pitch a scope of work to a client or partner.',
    icon: 'FileText',
    sections: [
      {
        title: 'Executive Summary',
        content:
          '<p>[client name] is a [industry] company looking to [client goal]. ' +
          'This proposal outlines how we will deliver [solution headline] ' +
          'over [engagement length], for an investment of [pricing total].</p>',
      },
      {
        title: 'Problem',
        content:
          '<p>Today, [client name] faces [problem statement]. Without action, ' +
          'this leads to [business impact].</p>',
      },
      {
        title: 'Proposed Solution',
        content:
          '<p>We will [solution overview]. Key deliverables include:</p>' +
          '<ul><li>[deliverable 1]</li><li>[deliverable 2]</li><li>[deliverable 3]</li></ul>',
      },
      {
        title: 'Timeline & Deliverables',
        content:
          '<ul>' +
          '<li><strong>Week 1–2 — Discovery:</strong> [discovery scope]</li>' +
          '<li><strong>Week 3–[N] — Build:</strong> [build scope]</li>' +
          '<li><strong>Final week — Handoff:</strong> [handoff scope]</li>' +
          '</ul>',
      },
      {
        title: 'Pricing',
        content:
          '<p>Total engagement: <strong>[pricing total]</strong>.</p>' +
          '<p>Billing: [billing terms]. Payment terms: [payment terms].</p>',
      },
      {
        title: 'Next Steps',
        content:
          '<ol>' +
          '<li>Review this proposal with [client stakeholder]</li>' +
          '<li>Sign and return by [signature deadline]</li>' +
          '<li>Kickoff call on [kickoff date]</li>' +
          '</ol>',
      },
    ],
  },

  {
    id: 'project_brief',
    label: 'Project Brief',
    description: 'Align stakeholders on goals, scope, and success metrics.',
    icon: 'ClipboardList',
    sections: [
      {
        title: 'Background',
        content:
          '<p>[project name] is being undertaken because [reason / problem]. ' +
          'It builds on prior work in [related context].</p>',
      },
      {
        title: 'Goals',
        content:
          '<ul>' +
          '<li>[goal 1]</li>' +
          '<li>[goal 2]</li>' +
          '<li>[goal 3]</li>' +
          '</ul>',
      },
      {
        title: 'Scope',
        content:
          '<p><strong>In scope:</strong> [in-scope items]</p>' +
          '<p><strong>Out of scope:</strong> [out-of-scope items]</p>',
      },
      {
        title: 'Stakeholders',
        content:
          '<ul>' +
          '<li><strong>Owner:</strong> [project owner]</li>' +
          '<li><strong>Sponsor:</strong> [executive sponsor]</li>' +
          '<li><strong>Contributors:</strong> [contributors]</li>' +
          '<li><strong>Reviewers:</strong> [reviewers]</li>' +
          '</ul>',
      },
      {
        title: 'Success Metrics',
        content:
          '<ul>' +
          '<li>[metric 1] reaches [target 1] by [target date]</li>' +
          '<li>[metric 2] reaches [target 2] by [target date]</li>' +
          '</ul>',
      },
      {
        title: 'Timeline',
        content:
          '<ul>' +
          '<li><strong>[milestone 1]</strong> — [target date]</li>' +
          '<li><strong>[milestone 2]</strong> — [target date]</li>' +
          '<li><strong>Launch</strong> — [launch date]</li>' +
          '</ul>',
      },
    ],
  },

  {
    id: 'status_report',
    label: 'Status Report',
    description: 'Weekly update for leadership or async stakeholders.',
    icon: 'Activity',
    sections: [
      {
        title: 'Summary',
        content:
          '<p>Week of [report week]. Overall status: <strong>[on-track / at-risk / off-track]</strong>. ' +
          '[1-line summary of the week].</p>',
      },
      {
        title: 'Wins this week',
        content:
          '<ul>' +
          '<li>[win 1]</li>' +
          '<li>[win 2]</li>' +
          '<li>[win 3]</li>' +
          '</ul>',
      },
      {
        title: 'Risks & Blockers',
        content:
          '<ul>' +
          '<li><strong>[risk 1]</strong> — [mitigation / owner]</li>' +
          '<li><strong>[blocker 1]</strong> — needs [unblocker / decision]</li>' +
          '</ul>',
      },
      {
        title: 'Next week',
        content:
          '<ul>' +
          '<li>[priority 1]</li>' +
          '<li>[priority 2]</li>' +
          '<li>[priority 3]</li>' +
          '</ul>',
      },
      {
        title: 'Asks',
        content:
          '<p>What we need from leadership / partners:</p>' +
          '<ul><li>[ask 1]</li><li>[ask 2]</li></ul>',
      },
    ],
  },

  {
    id: 'pitch_deck',
    label: 'Pitch Deck',
    description: 'Outline for a fundraise / sales / internal pitch deck.',
    icon: 'Presentation',
    sections: [
      {
        title: 'Title',
        content:
          '<p><strong>[company / product name]</strong></p>' +
          '<p>[one-line tagline — what you do, who for]</p>',
      },
      {
        title: 'Problem',
        content:
          '<p>[target customer] suffers from [pain point]. Today they cope by ' +
          '[current workaround], which is [why workaround is bad].</p>',
      },
      {
        title: 'Solution',
        content:
          '<p>[product name] solves this by [solution headline].</p>' +
          '<p>Key capabilities:</p>' +
          '<ul><li>[capability 1]</li><li>[capability 2]</li><li>[capability 3]</li></ul>',
      },
      {
        title: 'Demo / Walkthrough',
        content:
          '<p>Walk through [demo scenario]:</p>' +
          '<ol>' +
          '<li>[step 1 — what user sees]</li>' +
          '<li>[step 2 — what user does]</li>' +
          '<li>[step 3 — outcome / wow moment]</li>' +
          '</ol>',
      },
      {
        title: 'Traction',
        content:
          '<ul>' +
          '<li>[users / customers / revenue metric]</li>' +
          '<li>[growth rate]</li>' +
          '<li>[notable logos / testimonials]</li>' +
          '</ul>',
      },
      {
        title: 'Ask',
        content:
          '<p>We are raising <strong>[ask amount]</strong> to [use of funds].</p>' +
          '<p>Next step: [next step / call to action].</p>',
      },
    ],
  },
]

export function getTemplateById(id: string | null | undefined): ProjectTemplate | null {
  if (!id) return null
  return PROJECT_TEMPLATES.find((t) => t.id === id) ?? null
}
