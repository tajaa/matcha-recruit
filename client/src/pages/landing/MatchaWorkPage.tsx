import { useState } from 'react'
import { motion } from 'framer-motion'
import { LinkButton } from '../../components/ui'
import { GlitchText } from '../../components/GlitchText'
import { MatchaWorkMockup } from '../../components/landing/MatchaWorkMockup'
import { DOT_GRID_BG } from '../../components/landing/shared'
import { PricingContactModal } from '../../components/PricingContactModal'
import LandingNav from './LandingNav'

export default function MatchaWorkPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <LandingNav onPricingClick={() => setIsPricingOpen(true)} />

      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="relative pt-32 pb-24 px-4 sm:px-8 overflow-x-hidden"
      >
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{ backgroundImage: DOT_GRID_BG, backgroundSize: '24px 24px' }}
        />
        <div className="relative max-w-7xl mx-auto">
          <div className="text-center mb-10 relative">
            <span className="text-xs tracking-[0.3em] text-emerald-500 uppercase flex items-center justify-center gap-2 mb-4">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
              Agentic Workspace
            </span>
            <div className="flex justify-center items-center gap-4 mt-4">
              <h1 className="text-4xl sm:text-5xl font-bold uppercase tracking-wide text-zinc-100 flex items-center justify-center">
                <GlitchText text="Matcha Work" cycleWords={["Matcha Work", "System Active", "Terminal Ready"]} />
              </h1>
              <span className="px-2 py-1 bg-amber-500/10 text-amber-500 border border-amber-500/30 rounded text-[10px] font-[Orbitron] font-bold tracking-widest uppercase">
                Beta
              </span>
            </div>
            <p className="text-zinc-500 text-sm sm:text-base mt-4 max-w-lg mx-auto leading-relaxed">
              AI-powered recruiting pipeline, voice interviews, and document workspace. Post roles, upload resumes, let AI rank candidates and conduct interviews — all in one workspace.
            </p>
          </div>

          <motion.div
            whileHover={{ scale: 1.02 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
            style={{ boxShadow: "0 20px 40px -10px rgba(16, 185, 129, 0.15)" }}
            className="rounded-lg overflow-hidden max-w-2xl mx-auto border border-emerald-500/20"
          >
            <MatchaWorkMockup />
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

          {/* Feature highlights */}
          <div className="grid sm:grid-cols-3 gap-6 mt-20 max-w-4xl mx-auto">
            {[
              { title: 'AI Recruiting Pipeline', desc: 'Post roles, upload resumes, AI ranks candidates by match score. Full pipeline from posting to offer letter.' },
              { title: 'Voice Interviews', desc: 'Gemini-powered voice interviews with real-time transcription, error analysis, and CEFR-level scoring.' },
              { title: 'Document Workspace', desc: 'Multi-threaded projects with compliance research, regulatory reasoning chains, and PDF/DOCX export.' },
            ].map(f => (
              <div key={f.title} className="rounded-xl border border-zinc-700/50 p-6" style={{ background: 'rgba(24,24,27,0.6)' }}>
                <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wide mb-2">{f.title}</h3>
                <p className="text-xs text-zinc-500 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </motion.section>

      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
    </div>
  )
}
