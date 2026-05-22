import { Link } from 'react-router-dom'
import { BookOpen, Briefcase, Calculator, ChevronRight, ClipboardList, FileText } from 'lucide-react'

import PinnedResourcesPanel from '../../components/PinnedResourcesPanel'
import HeadlinesPanel from '../../components/resources-free/HeadlinesPanel'

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
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Resources</h1>
          <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
            Templates, calculators, audits, and references
          </p>
        </div>
      </div>

      <HeadlinesPanel compact />

      <PinnedResourcesPanel />

      {/* Cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {CARDS.map((card) => {
          const Icon = card.icon
          return (
            <Link
              key={card.to}
              to={card.to}
              className="group bg-zinc-900 border border-white/10 rounded-2xl p-5 flex flex-col gap-3 hover:border-white/20 hover:bg-zinc-800/50 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-xl bg-zinc-950 border border-white/5 flex items-center justify-center shrink-0">
                    <Icon className="w-4 h-4 text-zinc-400 group-hover:text-zinc-200 transition-colors" />
                  </div>
                  <p className="text-sm font-medium text-zinc-100 truncate">{card.title}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest">{card.count}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-zinc-700 group-hover:text-zinc-400 transition-colors" />
                </div>
              </div>
              <p className="text-[12px] text-zinc-500 leading-relaxed">{card.description}</p>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
