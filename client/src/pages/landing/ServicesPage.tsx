import { useState } from 'react'
import { motion } from 'framer-motion'
import { PricingContactModal } from '../../components/PricingContactModal'
import { DOT_GRID_BG } from '../../components/landing/shared'
import LandingNav from './LandingNav'

export default function ServicesPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <LandingNav onPricingClick={() => setIsPricingOpen(true)} />

      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="relative pt-32 pb-24 px-4 sm:px-8"
      >
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
        />
        <div className="relative max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <span className="text-xs tracking-[0.3em] text-zinc-500 uppercase flex items-center justify-center gap-2 mb-4">
              <span className="h-1.5 w-1.5 rounded-full bg-zinc-500 shadow-[0_0_8px_#71717a]" />
              Beyond the Platform
            </span>
            <h1 className="text-4xl sm:text-5xl font-bold uppercase tracking-wide text-zinc-100">
              Consulting Services
            </h1>
            <p className="text-zinc-500 text-sm sm:text-base mt-4 max-w-xl mx-auto leading-relaxed">
              Hands-on expertise for organizations that need more than software.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8 max-w-5xl mx-auto">
            {/* HR Consulting */}
            <motion.div
              whileHover={{ y: -4 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
              className="relative group rounded-xl border border-zinc-700/50 p-8 overflow-hidden"
              style={{ background: 'linear-gradient(135deg, rgba(24,24,27,0.9) 0%, rgba(39,39,42,0.4) 100%)' }}
            >
              <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-emerald-500/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                    <circle cx="9" cy="7" r="4" />
                    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 uppercase tracking-wide">HR Consulting</h3>
                  <span className="text-[10px] text-emerald-500 uppercase tracking-[0.2em]">Operations & Strategy</span>
                </div>
              </div>
              <ul className="space-y-3 text-sm text-zinc-400">
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-emerald-500 mt-2 shrink-0" />
                  <span>HR infrastructure setup for startups and scaling companies &mdash; handbooks, policies, compliance foundations</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-emerald-500 mt-2 shrink-0" />
                  <span>Multi-state employment law navigation &mdash; hiring, termination, classification, leave management</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-emerald-500 mt-2 shrink-0" />
                  <span>Workforce operations &mdash; onboarding, credentialing, performance management, and organizational design</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-emerald-500 mt-2 shrink-0" />
                  <span>Compliance audits and gap analysis for regulated industries &mdash; healthcare, biotech, manufacturing, finance</span>
                </li>
              </ul>
              <div className="mt-8">
                <span
                  onClick={() => setIsPricingOpen(true)}
                  className="text-[11px] text-zinc-500 uppercase hover:text-emerald-400 cursor-pointer transition-colors duration-300 tracking-widest"
                >
                  Get in touch &rarr;
                </span>
              </div>
            </motion.div>

            {/* AI Consulting */}
            <motion.div
              whileHover={{ y: -4 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
              className="relative group rounded-xl border border-zinc-700/50 p-8 overflow-hidden"
              style={{ background: 'linear-gradient(135deg, rgba(24,24,27,0.9) 0%, rgba(39,39,42,0.4) 100%)' }}
            >
              <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-amber-500/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83" />
                    <circle cx="12" cy="12" r="4" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-lg font-bold text-zinc-100 uppercase tracking-wide">AI Consulting</h3>
                  <span className="text-[10px] text-amber-500 uppercase tracking-[0.2em]">Implementation & Strategy</span>
                </div>
              </div>
              <ul className="space-y-3 text-sm text-zinc-400">
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-amber-500 mt-2 shrink-0" />
                  <span>AI integration into existing tech stacks &mdash; LLM orchestration, RAG pipelines, embedding strategies, tool-use architectures</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-amber-500 mt-2 shrink-0" />
                  <span>Autonomous agent development &mdash; multi-step agentic workflows, chain-of-thought reasoning systems, human-in-the-loop design</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-amber-500 mt-2 shrink-0" />
                  <span>AI strategy and roadmapping &mdash; where AI creates leverage in your operations vs. where it doesn't, build vs. buy analysis</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <span className="w-1 h-1 rounded-full bg-amber-500 mt-2 shrink-0" />
                  <span>The future of AI in your industry &mdash; capability forecasting, infrastructure planning, and preparing your team for what's next</span>
                </li>
              </ul>
              <div className="mt-8">
                <span
                  onClick={() => setIsPricingOpen(true)}
                  className="text-[11px] text-zinc-500 uppercase hover:text-amber-400 cursor-pointer transition-colors duration-300 tracking-widest"
                >
                  Get in touch &rarr;
                </span>
              </div>
            </motion.div>
          </div>
        </div>
      </motion.section>

      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
    </div>
  )
}
