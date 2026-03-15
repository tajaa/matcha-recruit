import { Shield, BarChart3, FileCheck, ArrowRight } from 'lucide-react'
import { LinkButton } from '../components/ui'
import { Card } from '../components/ui'
import { Logo } from '../components/ui'

const features = [
  {
    icon: Shield,
    title: 'Governance',
    description: 'Policy management, employee handbooks, and compliance frameworks — all in one place.',
  },
  {
    icon: BarChart3,
    title: 'Risk',
    description: 'Incident tracking, risk assessments, and real-time monitoring across your organization.',
  },
  {
    icon: FileCheck,
    title: 'Compliance',
    description: 'Jurisdiction-aware requirements, automated audits, and AI-powered gap analysis.',
  },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Nav */}
      <nav className="flex items-center justify-between px-8 py-5 max-w-6xl mx-auto">
        <Logo />
        <LinkButton to="/login" size="md">Log in</LinkButton>
      </nav>

      {/* Hero */}
      <section className="max-w-6xl mx-auto px-8 pt-28 pb-20">
        <h1 className="text-5xl sm:text-6xl font-bold tracking-tight leading-[1.1] font-[Space_Grotesk] max-w-2xl">
          GRC that actually
          <br />
          <span className="text-emerald-400">works for you</span>
        </h1>
        <p className="mt-6 text-lg text-zinc-400 max-w-lg leading-relaxed">
          Governance, risk, and compliance — powered by AI, built for modern HR
          and operations teams.
        </p>
        <div className="mt-10">
          <LinkButton to="/login" size="lg">
            Get started
            <ArrowRight className="h-4 w-4" />
          </LinkButton>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-8 pb-32">
        <div className="grid gap-6 sm:grid-cols-3">
          {features.map((f) => (
            <Card key={f.title}>
              <f.icon className="h-8 w-8 text-emerald-400 mb-5" />
              <h3 className="text-lg font-semibold mb-2 font-[Space_Grotesk]">
                {f.title}
              </h3>
              <p className="text-sm text-zinc-400 leading-relaxed">
                {f.description}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-zinc-800 py-8">
        <p className="text-center text-xs text-zinc-500">
          &copy; {new Date().getFullYear()} Matcha. All rights reserved.
        </p>
      </footer>
    </div>
  )
}
