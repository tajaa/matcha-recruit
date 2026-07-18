import type { TourStep } from '../../components/panels/ProjectTour'

export const TOUR_DISMISSED_KEY = 'mw_project_tour_dismissed'

export const TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="sections-panel"]',
    title: 'Sections — your project document',
    description: 'Pre-filled when you pick a template. Click any [bracketed placeholder] to edit, drag to reorder, or send a message in chat to auto-fill all placeholders at once.',
    side: 'left',
  },
  {
    target: '[data-tour="chat-input"]',
    title: 'AI chat — your project copilot',
    description: 'Type something like "Acme Corp · B2B SaaS · $25k Q3" and Matcha fills bracketed placeholders across every section. Also use it to add new sections, rewrite, or summarize.',
    side: 'top',
  },
  {
    target: '[data-tour="collaborators-pill"]',
    title: 'See who else is here',
    description: 'When teammates open the same project, you see their colored cursors and carets in real time. Names appear in the header pill so you know who else is around.',
    side: 'bottom',
  },
  {
    target: '[data-tour="export-button"]',
    title: 'Export & share',
    description: 'Export the project as PDF or DOCX. Invite collaborators from the project menu — anyone you invite can edit alongside you.',
    side: 'left',
  },
]
