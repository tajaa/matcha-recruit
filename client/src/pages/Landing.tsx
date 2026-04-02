import { lazy, Suspense, useEffect, useState, useRef } from 'react'
import { motion, useInView, useScroll, useTransform, useMotionTemplate, useMotionValue } from 'framer-motion'
import { LinkButton } from '../components/ui'
import { AsciiHalftone } from '../components/AsciiHalftone'
import { GlitchText } from '../components/GlitchText'
import { PricingContactModal } from '../components/PricingContactModal'
import { JurisdictionCascade } from '../components/landing/JurisdictionCascade'
import { SignalMonitor } from '../components/landing/SignalMonitor'
import { MonteCarloDistribution } from '../components/landing/MonteCarloDistribution'
import { TimelineConstructor } from '../components/landing/TimelineConstructor'
import { PatternGrid } from '../components/landing/PatternGrid'
import { RadarChart } from '../components/landing/RadarChart'
import { TerminalTyping } from '../components/landing/TerminalTyping'
import { FeatureSectionItem } from '../components/landing/FeatureSectionItem'
import { DOT_GRID_BG } from '../components/landing/shared'

const ParticleSphere = lazy(() => import('../components/ParticleSphere'))

/* ── Feature Section Data ─────────────────────────────────────── */
const SECTIONS = [
  {
    category: 'COMPLIANCE & LEGAL',
    accent: '#10b981',
    title: 'Compliance Engine',
    desc: 'Agentic jurisdiction research across federal, state, and local levels. Chain-of-reasoning compliance querying walks through regulatory logic step by step — citing sources, applying preemption rules, and surfacing gaps before returning a final answer.',
    graphic: JurisdictionCascade,
  },
  {
    category: 'COMPLIANCE & LEGAL',
    accent: '#f59e0b',
    title: 'Legislative Tracker',
    desc: 'Continuous monitoring of regulatory changes with pattern detection for coordinated legislative activity across jurisdictions. Real-time signal processing flags relevant changes before they become compliance gaps.',
    graphic: SignalMonitor,
  },
  {
    category: 'COMPLIANCE & LEGAL',
    accent: '#10b981',
    title: 'Risk Assessment',
    desc: '5-dimension live scoring with Monte Carlo simulation across 10,000 iterations, statistical anomaly detection on time-series metrics, and NAICS-benchmarked peer comparison sourced from BLS, OSHA, EEOC, and QCEW.',
    graphic: MonteCarloDistribution,
  },
  {
    category: 'INVESTIGATIONS & RISK',
    accent: '#f59e0b',
    title: 'ER Copilot',
    desc: 'Employment relations case management with agentic document analysis. Timeline construction and discrepancy detection. Encrypted PDF report generation with secure shared export links for external counsel.',
    graphic: TimelineConstructor,
  },
  {
    category: 'INVESTIGATIONS & RISK',
    accent: '#f59e0b',
    title: 'Incident Reports',
    desc: 'OSHA 300 and 300A auto-generation, anonymous reporting, and trend analytics with pattern detection across locations. Covers safety, behavioral, and compliance incidents.',
    graphic: PatternGrid,
  },
  {
    category: 'INVESTIGATIONS & RISK',
    accent: '#f59e0b',
    title: 'Pre-Termination Intel',
    desc: '9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before any separation decision. Generates a narrative memo suitable for counsel review.',
    graphic: RadarChart,
  },
]



export default function Landing() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div className="relative bg-zinc-900 text-zinc-100 overflow-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <div className="relative z-10">
        {/* Nav */}
        <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center px-6 pt-5">
          <div
            className="flex items-center justify-between w-full max-w-6xl px-6 py-3 rounded-full border border-zinc-700/30"
            style={{
              background: 'rgba(24, 24, 27, 0.6)',
              backdropFilter: 'blur(16px) saturate(1.4)',
              WebkitBackdropFilter: 'blur(16px) saturate(1.4)',
              boxShadow: '0 0 20px rgba(0,0,0,0.3), inset 0 0.5px 0 rgba(255,255,255,0.05)',
            }}
          >
            <div className="flex items-center gap-2.5">
              <img src="/logo.svg" alt="Matcha" className="h-5 w-5" />
              <span className="text-sm font-[Orbitron] font-bold tracking-[0.25em] uppercase">
                Matcha
              </span>
            </div>
            <div className="hidden sm:flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              <span className="text-[10px] text-zinc-500 uppercase">
                Systems Online
              </span>
            </div>
            <div className="flex items-center gap-5">
              <span
                onClick={() => setIsPricingOpen(true)}
                className="hidden sm:inline text-[11px] text-zinc-400 uppercase hover:text-emerald-400 cursor-pointer transition-colors duration-300"
              >
                Pricing
              </span>
              <LinkButton
                to="/login"
                variant="ghost"
                size="sm"
                className="uppercase text-zinc-300 hover:text-emerald-400 border border-zinc-600/50 hover:border-emerald-500/40 rounded-full px-5 transition-all duration-300"
              >
                Login
              </LinkButton>
            </div>
          </div>
        </nav>

        {/* Hero */}
        <div className="relative pt-16">
          <AsciiHalftone />
        <section className="relative max-w-7xl mx-auto px-8 min-h-[90vh] flex items-center">
          {/* System tag */}
          <div className="absolute top-8 left-8 text-[11px] text-zinc-600 border border-zinc-700/40 px-3 py-1.5 rounded-sm">
            SYSTEM CORE // OFFLINE MODE
          </div>

          {/* Left content */}
          <div className="relative z-10 max-w-xl">
            <h1 className="font-[Orbitron] text-5xl sm:text-6xl lg:text-7xl font-black uppercase tracking-tight leading-[0.95]">
              Workforce
            </h1>
            <GlitchText
              text="Intelligence."
              cycleWords={["Compliance.", "Risk Assessment.", "Risk Management."]}
              className="block text-5xl sm:text-6xl lg:text-7xl italic font-light tracking-tight leading-[1.1] mt-1"
            />
            <p className="mt-8 text-lg sm:text-xl text-zinc-400 font-light">
              Increase your{' '}
              <span className="text-amber-500 font-normal">signal to noise ratio</span>.
            </p>
            <div className="mt-10">
              <LinkButton
                to="/login"
                variant="secondary"
                size="lg"
                className="uppercase border border-zinc-600 hover:border-zinc-400 px-10"
              >
                Initialize Account
              </LinkButton>
            </div>
          </div>

          {/* Particle Sphere */}
          <div className="absolute right-0 top-0 bottom-0 w-[60%] hidden lg:flex items-center justify-center">
            <Suspense
              fallback={
                <div className="text-zinc-600 text-[8px] uppercase animate-pulse">
                  Booting Neural Sphere...
                </div>
              }
            >
              <ParticleSphere className="w-full h-[70vh] opacity-80" />
            </Suspense>
          </div>

          {/* Scroll Down Chevron */}
          <button
            onClick={() => {
              document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })
            }}
            className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1 group cursor-pointer z-10"
            aria-label="Scroll down"
          >
            <span className="text-[9px] text-zinc-600 uppercase group-hover:text-zinc-400 transition-colors duration-300">
              Explore
            </span>
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              className="text-zinc-500 group-hover:text-emerald-400 transition-colors duration-300"
              style={{ animation: 'chevron-bounce 2s ease-in-out infinite' }}
            >
              <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </section>
        </div>

        {/* ── Global keyframes ──────────────────────────────────── */}
        <style>{`
          @keyframes ripple-expand {
            0% { transform: translate(-50%,-50%) scale(0.5); opacity: 0.3; }
            100% { transform: translate(-50%,-50%) scale(1.5); opacity: 0; }
          }
          @keyframes chevron-bounce {
            0%, 100% { transform: translateY(0); opacity: 0.6; }
            50% { transform: translateY(6px); opacity: 1; }
          }
        `}</style>

        {/* ── Feature Sections ─────────────────────────────────── */}
        {SECTIONS.map((section, idx) => (
          <FeatureSectionItem key={section.title} section={section} idx={idx} />
        ))}

        {/* ── Matcha Work CTA ──────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="relative border-t border-zinc-700/40 py-24 px-8 overflow-hidden"
        >
          <div
            className="absolute inset-0 opacity-[0.04]"
            style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
          />
          <div className="relative max-w-7xl mx-auto">
            <div className="text-center mb-10">
              <span className="text-xs tracking-[0.3em] text-emerald-500 uppercase flex items-center justify-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
                Agentic Workspace
              </span>
              <h2 className="text-4xl sm:text-5xl font-bold uppercase tracking-wide text-zinc-100 mt-4 flex items-center justify-center">
                <GlitchText text="Matcha Work" cycleWords={["Matcha Work", "System Active", "Terminal Ready"]} />
              </h2>
              <p className="text-zinc-500 text-sm sm:text-base mt-4 max-w-lg mx-auto leading-relaxed">
                Multi-threaded document workspace for compliance research, ER case analysis, regulatory reasoning chains, and cross-referencing organizational data.
              </p>
            </div>

            <motion.div
              whileHover={{ scale: 1.02 }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              style={{ boxShadow: "0 20px 40px -10px rgba(16, 185, 129, 0.15)" }}
              className="rounded-lg overflow-hidden max-w-2xl mx-auto border border-emerald-500/20"
            >
              <TerminalTyping />
            </motion.div>

            <div className="text-center mt-10">
              <LinkButton
                to="/login"
                variant="secondary"
                size="lg"
                className="uppercase border border-zinc-600 hover:border-zinc-400 px-10"
              >
                Launch Workspace
              </LinkButton>
            </div>
          </div>
        </motion.section>

        {/* Footer */}
        <footer className="border-t border-zinc-700/50 py-6 px-8">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <p className="text-[10px] text-zinc-600 uppercase">
              &copy; {new Date().getFullYear()} Matcha Systems Inc.
              {import.meta.env.VITE_LANDING_BUILD_VERSION ? (
                <span className="ml-2 text-zinc-700">build {import.meta.env.VITE_LANDING_BUILD_VERSION}</span>
              ) : null}
            </p>
            <div className="flex gap-6">
              {['Terms', 'Privacy', 'Status'].map((link) => (
                <span
                  key={link}
                  className="text-[10px] text-zinc-600 uppercase hover:text-zinc-400 cursor-pointer transition-colors"
                >
                  {link}
                </span>
              ))}
            </div>
          </div>
        </footer>
      </div>
    </div>
  )
}
