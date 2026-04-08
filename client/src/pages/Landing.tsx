import { lazy, Suspense, useState } from 'react'

import { LinkButton } from '../components/ui'
import LandingNav from './landing/LandingNav'
import { AsciiHalftone } from '../components/AsciiHalftone'
import { GlitchText } from '../components/GlitchText'
import { PricingContactModal } from '../components/PricingContactModal'
import { JurisdictionCascade } from '../components/landing/JurisdictionCascade'
import { SignalMonitor as _SignalMonitor } from '../components/landing/SignalMonitor'
import { MatchaWorkMockup } from '../components/landing/MatchaWorkMockup'
import { MonteCarloDistribution } from '../components/landing/MonteCarloDistribution'
import { TimelineConstructor } from '../components/landing/TimelineConstructor'
import { PatternGrid } from '../components/landing/PatternGrid'
import { RadarChart } from '../components/landing/RadarChart'

import { FeatureSectionItem } from '../components/landing/FeatureSectionItem'


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
  // Legislative Tracker — muted for now
  // {
  //   category: 'COMPLIANCE & LEGAL',
  //   accent: '#f59e0b',
  //   title: 'Legislative Tracker',
  //   desc: 'Continuous monitoring of regulatory changes with pattern detection for coordinated legislative activity across jurisdictions. Real-time signal processing flags relevant changes before they become compliance gaps.',
  //   graphic: _SignalMonitor,
  // },
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
  {
    category: 'COLLABORATION',
    accent: '#10b981',
    title: 'Matcha Work',
    desc: 'Internal collaboration hub with real-time channels, direct messaging, and team workspaces. Threaded conversations keep context organized across departments — HR, legal, compliance, and operations all in one secure platform.',
    graphic: MatchaWorkMockup,
  },
]



export default function Landing() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div className="relative bg-zinc-900 text-zinc-100 overflow-x-hidden snap-y snap-proximity h-screen overflow-y-auto">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <div className="relative z-10">
        {/* Nav */}
        <LandingNav onPricingClick={() => setIsPricingOpen(true)} />

        {/* Hero */}
        <div className="relative pt-16 snap-start min-h-screen">
          <AsciiHalftone />
        <section className="relative max-w-7xl mx-auto px-4 sm:px-8 min-h-screen flex items-center py-12 sm:py-0">
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
          <FeatureSectionItem key={section.title} section={section} idx={idx} isLast={idx === SECTIONS.length - 1} />
        ))}

        {/* Footer */}
        <footer className="border-t border-zinc-700/50 py-6 px-8 snap-start">
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
