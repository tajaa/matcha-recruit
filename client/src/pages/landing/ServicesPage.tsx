import { useState } from 'react'
import { motion } from 'framer-motion'
import { PricingContactModal } from '../../components/PricingContactModal'
import { DOT_GRID_BG } from '../../components/landing/shared'
import { AsciiHalftone } from '../../components/AsciiHalftone'
import LandingNav from './LandingNav'

export default function ServicesPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  const services = [
    {
      title: "HR Consulting",
      subtitle: "Operations & Strategy",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      ),
      points: [
        "HR infrastructure build-out for startups through enterprise",
        "Multi-state employment law — hiring, termination, classification",
        "Workforce operations — onboarding, credentialing, org design",
        "Employee relations — investigations and separation risk review",
        "Advisory sessions — standing access to senior HR guidance"
      ]
    },
    {
      title: "Compliance Consulting",
      subtitle: "Regulatory & Audit",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      ),
      points: [
        "Regulatory gap analysis across all operating jurisdictions",
        "Compliance program design for healthcare and manufacturing",
        "Audit preparation — CMS, Joint Commission, OSHA, and State boards",
        "Policy & handbook remediation and gap identification",
        "Credential & license program setup and audit-ready tracking"
      ]
    },
    {
      title: "AI / Tech Consulting",
      subtitle: "Implementation & Strategy",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83" />
          <circle cx="12" cy="12" r="4" />
        </svg>
      ),
      points: [
        "AI integration — LLM orchestration and RAG pipelines",
        "Autonomous agent development and agentic workflows",
        "AI strategy & roadmapping — leverage analysis and build vs buy",
        "Tech stack modernization and infrastructure planning",
        "Industry-specific AI forecasting and team preparation"
      ]
    }
  ]

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 overflow-x-hidden selection:bg-zinc-100 selection:text-zinc-950">
      <LandingNav onPricingClick={() => setIsPricingOpen(true)} />

      <section className="relative pt-32 pb-24 px-4 sm:px-8">
        <AsciiHalftone />
        <div
          className="absolute inset-0 opacity-[0.03] pointer-events-none"
          style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
        />
        
        <div className="relative max-w-7xl mx-auto">
          {/* System tag */}
          <div className="text-[10px] font-mono text-zinc-600 border-l border-zinc-800 pl-3 py-1 mb-16 uppercase tracking-widest hidden lg:block">
            System Core // Service_Registry.v3
          </div>

          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1 }}
            className="text-center mb-24 relative"
          >
            <span className="text-[10px] tracking-[0.4em] text-zinc-500 uppercase mb-6 block">
              Beyond the Platform
            </span>
            <h1 className="font-[Orbitron] text-4xl sm:text-5xl lg:text-6xl font-black uppercase tracking-tight text-zinc-100 mb-8">
              Consulting Services
            </h1>
            <div className="max-w-2xl mx-auto space-y-4">
              <p className="text-zinc-300 text-lg sm:text-xl font-medium tracking-wide leading-relaxed">
                Regulated companies don't fail from one event. They fail from disconnected gaps.
              </p>
              <p className="text-zinc-500 text-sm sm:text-base leading-relaxed max-w-xl mx-auto uppercase tracking-[0.2em] font-light">
                Identifying and closing systemic risk through hands-on technical and operational expertise.
              </p>
            </div>
          </motion.div>

          <div className="grid lg:grid-cols-3 gap-1px bg-zinc-700/30 border border-zinc-800/80 max-w-7xl mx-auto backdrop-blur-sm">
            {services.map((service, idx) => (
              <div
                key={idx}
                className="group relative p-12 bg-zinc-900/40 flex flex-col h-full transition-all duration-300 hover:bg-zinc-800/30"
              >
                <div className="flex items-center justify-between mb-12">
                  <div className="text-zinc-400 group-hover:text-white transition-colors duration-300 scale-110">
                    {service.icon}
                  </div>
                  <span className="text-[10px] font-mono text-zinc-500 tracking-widest uppercase">
                    Ref. {idx + 1}
                  </span>
                </div>

                <div className="mb-10">
                  <h3 className="text-xl font-bold text-zinc-100 uppercase tracking-[0.1em] mb-2">
                    {service.title}
                  </h3>
                  <span className="text-xs text-zinc-400 uppercase tracking-[0.2em] font-medium border-b border-zinc-700/50 pb-1">
                    {service.subtitle}
                  </span>
                </div>

                <ul className="space-y-6 text-base text-zinc-300 flex-grow mb-16">
                  {service.points.map((point, pIdx) => (
                    <li key={pIdx} className="flex items-start gap-4">
                      <span className="w-1.5 h-1.5 rounded-full bg-zinc-600 mt-2 shrink-0 group-hover:bg-zinc-400 transition-colors" />
                      <span className="leading-relaxed font-light group-hover:text-white transition-colors duration-300">
                        {point}
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="mt-auto">
                  <span
                    onClick={() => setIsPricingOpen(true)}
                    className="inline-flex items-center gap-3 text-xs text-zinc-300 uppercase tracking-[0.3em] cursor-pointer hover:text-white transition-all duration-300 group/link font-bold py-2 border-t border-zinc-800/50 w-full"
                  >
                    Initialize Engagement
                    <span className="transition-transform duration-300 group-hover/link:translate-x-1">&rarr;</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
    </div>
  )
}
