import { lazy, Suspense, useState } from "react";

import { LinkButton } from "../components/ui";
import LandingNav from "./landing/LandingNav";
import { AsciiHalftone } from "../components/AsciiHalftone";
import { GlitchText } from "../components/GlitchText";
import { PricingContactModal } from "../components/PricingContactModal";
import { JurisdictionCascade } from "../components/landing/JurisdictionCascade";
import { SignalMonitor as _SignalMonitor } from "../components/landing/SignalMonitor";
import { MatchaWorkMockup } from "../components/landing/MatchaWorkMockup";
import { MonteCarloDistribution } from "../components/landing/MonteCarloDistribution";
import { TimelineConstructor } from "../components/landing/TimelineConstructor";
import { PatternGrid } from "../components/landing/PatternGrid";
import { RadarChart } from "../components/landing/RadarChart";

import { FeatureSectionItem } from "../components/landing/FeatureSectionItem";
import { ComplianceTicker } from "../components/landing/ComplianceTicker";

const ParticleSphere = lazy(() => import("../components/ParticleSphere"));

/* ── Feature Section Data ─────────────────────────────────────── */
const SECTIONS = [
  {
    category: "COMPLIANCE & LEGAL",
    accent: "#10b981",
    title: "Compliance Engine",
    desc: "Agentic jurisdiction research across federal, state, and local regulatory frameworks. The system walks through regulatory logic step by step — citing sources, applying preemption rules, and surfacing gaps before they become audit findings or enforcement actions.",
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
    category: "COMPLIANCE & LEGAL",
    accent: "#10b981",
    title: "Risk Assessment",
    desc: "5-dimension live scoring with Monte Carlo simulation across 10,000 iterations. Statistical anomaly detection on time-series metrics with NAICS-benchmarked peer comparison — so you know exactly where you stand relative to your industry before regulators tell you.",
    graphic: MonteCarloDistribution,
  },
  {
    category: "INVESTIGATIONS & RISK",
    accent: "#f59e0b",
    title: "ER Copilot",
    desc: "Employment relations case management that catches discrepancies human reviewers miss. Automated timeline construction, document analysis, and encrypted PDF reports ready for counsel — turning weeks of investigation prep into hours.",
    graphic: TimelineConstructor,
  },
  {
    category: "INVESTIGATIONS & RISK",
    accent: "#f59e0b",
    title: "Incident Reports",
    desc: "OSHA 300/300A auto-generation, anonymous reporting, and cross-location pattern detection. Surface systemic issues before they become pattern-or-practice investigations — the kind that led to DOJ settlements at companies like National Mentor Holdings.",
    graphic: PatternGrid,
  },
  {
    category: "INVESTIGATIONS & RISK",
    accent: "#f59e0b",
    title: "Pre-Termination Intel",
    desc: "9-dimension risk assessment scanning legal, compliance, and organizational factors before any separation. The system connects protected activity, pending complaints, and regulatory exposure that decision-makers typically can't see — generating a counsel-ready memo before the decision is made, not after the filing.",
    graphic: RadarChart,
  },
  {
    category: "COLLABORATION",
    accent: "#10b981",
    title: "Matcha Work",
    desc: "Secure internal collaboration where HR, legal, compliance, and operations share context in real time. Threaded channels, direct messaging, and document sharing — so the cross-functional decisions that create or prevent liability happen with full visibility, not in disconnected email chains.",
    graphic: MatchaWorkMockup,
  },
];

export default function Landing() {
  const [isPricingOpen, setIsPricingOpen] = useState(false);

  return (
    <div className="relative bg-zinc-900 text-zinc-100 overflow-x-hidden md:snap-y md:snap-proximity md:h-screen md:overflow-y-auto">
      <PricingContactModal
        isOpen={isPricingOpen}
        onClose={() => setIsPricingOpen(false)}
      />
      <div className="relative z-10">
        {/* Nav */}
        <LandingNav onPricingClick={() => setIsPricingOpen(true)} />

        {/* Compliance Ticker */}
        <ComplianceTicker />

        {/* Hero */}
        <div className="relative pt-[90px] sm:pt-[96px] md:snap-start min-h-[100svh]">
          <AsciiHalftone />
          <section className="relative max-w-7xl mx-auto px-4 sm:px-8 min-h-[100svh] flex items-center py-20 sm:py-0">
            {/* System tag */}
            <div className="absolute top-8 left-8 text-[11px] text-zinc-600 border border-zinc-700/40 px-3 py-1.5 rounded-sm">
              SYSTEM CORE // OFFLINE MODE
            </div>

            {/* Left content */}
            <div className="relative z-10 max-w-xl">
              <h1 className="font-[Orbitron] text-4xl sm:text-5xl lg:text-7xl font-black uppercase tracking-tight leading-[0.95]">
                Agentic
              </h1>
              <GlitchText
                text="Intelligence."
                cycleWords={[
                  "Compliance.",
                  "Risk Assessment.",
                  "Risk Management.",
                ]}
                className="block text-4xl sm:text-5xl lg:text-7xl italic font-light tracking-tight leading-[1.1] mt-1"
              />
              <p className="mt-8 text-lg sm:text-xl text-zinc-400 font-light">
                Increase your{" "}
                <span className="text-amber-500 font-normal">
                  signal to noise ratio
                </span>
                .
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
                document
                  .getElementById("features")
                  ?.scrollIntoView({ behavior: "smooth" });
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
                style={{ animation: "chevron-bounce 2s ease-in-out infinite" }}
              >
                <path
                  d="M6 9l6 6 6-6"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
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

        {/* ── About / Elevator Pitch ───────────────────────────── */}
        <section
          id="about"
          className="relative min-h-[100svh] md:min-h-screen flex items-center md:snap-start border-t border-zinc-700/40 px-4 sm:px-8 py-20 sm:py-24"
        >
          <div className="max-w-4xl mx-auto" style={{ fontFamily: "'Inter', sans-serif" }}>
            <p className="text-xs font-medium tracking-[0.3em] uppercase text-zinc-500 mb-8">
              At The Core
            </p>
            <h2 className="text-2xl sm:text-3xl lg:text-5xl font-semibold text-zinc-100 leading-[1.2] mb-8 sm:mb-10">
              Regulated companies don't fail from one bad decision — they
              collapse under{" "}
              <span className="text-amber-500">disconnected gaps</span> that
              compound into unsurvivable events.
            </h2>
            <div className="space-y-5 mb-10 sm:mb-12">
              <p className="text-base sm:text-lg text-zinc-400 leading-relaxed">
                Compliance data, investigation records, credential tracking, and
                HR decisions all live in separate systems. The people making
                termination decisions can't see protected activity. The people
                tracking credentials can't see compliance implications. Every one
                of these gaps is a future claim nobody knows exists yet.
              </p>
              <p className="text-base sm:text-lg text-zinc-400 leading-relaxed">
                Matcha closes every one of those gaps. One system where compliance
                obligations, investigations, credentials, policies, and workforce
                decisions are connected — so when someone is about to make a
                decision that creates liability, the system catches it before it
                becomes a filing.
              </p>
            </div>
            <div className="h-px w-32 bg-gradient-to-r from-amber-500/60 to-transparent mb-10" />
            <p className="text-sm text-zinc-500 max-w-2xl leading-relaxed mb-12" style={{ fontStyle: 'italic' }}>
              The companies that survive in regulated industries aren't the ones
              with the best lawyers. They're the ones whose systems make
              catastrophic mistakes structurally improbable.
            </p>
            <a
              href="/login"
              className="inline-block uppercase text-sm font-medium tracking-[0.15em] px-10 py-3 border border-zinc-600 hover:border-zinc-400 text-zinc-300 hover:text-zinc-100 transition-colors duration-300 rounded-sm"
            >
              Initialize Account
            </a>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t border-zinc-700/50 py-6 px-8 md:snap-start">
          <div className="flex items-center justify-between max-w-7xl mx-auto">
            <p className="text-[10px] text-zinc-600 uppercase">
              &copy; {new Date().getFullYear()} Matcha Systems Inc.
              {import.meta.env.VITE_LANDING_BUILD_VERSION ? (
                <span className="ml-2 text-zinc-700">
                  build {import.meta.env.VITE_LANDING_BUILD_VERSION}
                </span>
              ) : null}
            </p>
            <div className="flex gap-6">
              {["Terms", "Privacy", "Status"].map((link) => (
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
  );
}
