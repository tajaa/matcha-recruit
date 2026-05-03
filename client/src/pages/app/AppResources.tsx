import { Link } from 'react-router-dom'
import { BookOpen, Briefcase, Calculator, ChevronRight, ClipboardList, FileText } from 'lucide-react'

type Card = {
  to: string
  title: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  count: string
}

const CARDS: Card[] = [
  {
    to: '/app/resources/templates',
    title: 'HR Templates',
    description: 'Offer letters, PIPs, severance agreements, disciplinary warnings, termination checklists, I-9, W-4, and more.',
    icon: FileText,
    count: '14',
  },
  {
    to: '/app/resources/templates/job-descriptions',
    title: 'Job Descriptions',
    description: '62 ready-to-edit job descriptions across hospitality, healthcare, retail, and corporate roles.',
    icon: Briefcase,
    count: '62',
  },
  {
    to: '/app/resources/calculators',
    title: 'HR Calculators',
    description: 'PTO accrual, turnover cost, overtime, and total compensation calculators — interactive, no login.',
    icon: Calculator,
    count: '4',
  },
  {
    to: '/app/resources/audit',
    title: 'Compliance Audit',
    description: '12 questions → a tailored compliance gap report for your state, headcount, and industry.',
    icon: ClipboardList,
    count: '12Q',
  },
  {
    to: '/app/resources/glossary',
    title: 'HR Glossary',
    description: 'Plain-English definitions for FLSA, ACA, FMLA, COBRA, OWBPA, and every other HR acronym.',
    icon: BookOpen,
    count: '120+',
  },
]

export default function AppResources() {
  return (
    <div>
      <div className="flex items-center gap-4 mb-8 flex-wrap">
        <h1 className="text-2xl font-semibold text-vsc-text">Resources</h1>
        <div className="flex items-center gap-2 ml-auto">
          <div className="rounded-lg border border-vsc-border bg-vsc-panel px-4 py-2 flex items-center gap-3">
            <p className="text-[10px] font-medium uppercase tracking-wider text-vsc-text/50">Templates</p>
            <p className="text-xl font-bold text-vsc-text">14</p>
          </div>
          <div className="rounded-lg border border-vsc-border bg-vsc-panel px-4 py-2 flex items-center gap-3">
            <p className="text-[10px] font-medium uppercase tracking-wider text-vsc-text/50">Job Descriptions</p>
            <p className="text-xl font-bold text-vsc-text">62</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {CARDS.map(card => (
          <Link
            key={card.to}
            to={card.to}
            className="group rounded-xl border border-vsc-border bg-vsc-panel p-5 flex flex-col gap-3 hover:border-vsc-text/30 transition-colors"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-md bg-vsc-bg flex items-center justify-center shrink-0">
                  <card.icon className="w-4 h-4 text-vsc-text/60" />
                </div>
                <p className="text-sm font-medium text-vsc-text group-hover:text-white transition-colors">{card.title}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-medium uppercase tracking-wider text-vsc-text/40">{card.count}</span>
                <ChevronRight className="w-3.5 h-3.5 text-vsc-text/20 group-hover:text-vsc-text/50 transition-colors" />
              </div>
            </div>
            <p className="text-xs text-vsc-text/50 leading-relaxed">{card.description}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
