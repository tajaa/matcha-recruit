import { Link } from 'react-router-dom'
import { ArrowRight, FileText, Calculator, BookOpen, ClipboardList, Briefcase } from 'lucide-react'

type ResourceCard = {
  to: string
  title: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  badge?: string
}

const RESOURCES: ResourceCard[] = [
  {
    to: '/app/resources/templates',
    title: 'HR Templates',
    description: '14 editable HR templates — offer letters, PIPs, termination checklists, disciplinary warnings, severance agreements, I-9, W-4, and more.',
    icon: FileText,
    badge: '14 templates',
  },
  {
    to: '/app/resources/templates/job-descriptions',
    title: 'Job Descriptions',
    description: 'Ready-to-use job description templates across roles and departments. Download and customize for your openings.',
    icon: Briefcase,
  },
  {
    to: '/app/resources/calculators',
    title: 'HR Calculators',
    description: 'PTO accrual, turnover cost, overtime, and total compensation calculators — interactive and free.',
    icon: Calculator,
    badge: '2 live',
  },
  {
    to: '/app/resources/audit',
    title: 'Compliance Audit',
    description: '12 questions → a tailored compliance gap report for your state, headcount, and industry.',
    icon: ClipboardList,
  },
  {
    to: '/app/resources/glossary',
    title: 'HR Glossary',
    description: 'Plain-English definitions for FLSA, ACA, FMLA, COBRA, OWBPA, and the rest of the HR alphabet soup.',
    icon: BookOpen,
  },
]

export default function AppResources() {
  return (
    <div className="max-w-4xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Resources</h1>
        <p className="text-sm text-zinc-500 mt-1">HR templates, calculators, state guides, and compliance tools.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {RESOURCES.map((r) => (
          <Link
            key={r.to}
            to={r.to}
            className="group flex flex-col gap-3 border border-zinc-800 rounded-xl p-5 hover:border-zinc-600 hover:bg-zinc-900/40 transition-all"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-zinc-800 flex items-center justify-center shrink-0">
                  <r.icon className="w-4 h-4 text-zinc-400" />
                </div>
                <div>
                  <p className="text-sm font-medium text-zinc-100 group-hover:text-white">{r.title}</p>
                  {r.badge && (
                    <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wide">{r.badge}</span>
                  )}
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors shrink-0 mt-0.5" />
            </div>
            <p className="text-sm text-zinc-400 leading-relaxed">{r.description}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
