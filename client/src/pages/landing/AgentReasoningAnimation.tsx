import { motion, AnimatePresence } from 'framer-motion'
import { GitBranch, AlertTriangle } from 'lucide-react'
import { DECISIONS, SCENARIO, ZINC_LINE, GOLD, MONO } from './AgentReasoningAnimation/data'
import { useReasoningLoop } from './AgentReasoningAnimation/useReasoningLoop'
import { RootNode } from './AgentReasoningAnimation/RootNode'
import { DecisionColumn } from './AgentReasoningAnimation/DecisionColumn'
import { ConnectorSvg } from './AgentReasoningAnimation/ConnectorSvg'
import { SynthesisCard } from './AgentReasoningAnimation/SynthesisCard'
import { ParticleField } from './AgentReasoningAnimation/ParticleField'

// ───────────────────────────────────────────────────────────────────────────
// Real CA scenario: SB 553 Workplace Violence Prevention.
// Effective Jul 2024 — every CA employer must have a written plan, training,
// log, hazard assessment, and annual review cadence. Most companies don't.
// Cal/OSHA penalties stack per-location — risk reads as catastrophic.
// This is assistive analysis: it screens each requirement against the relevant
// sub-rules, flags gaps, and DRAFTS a remediation plan for a human to review and
// act on. It surfaces and suggests — it does not decide or execute on its own.
// ───────────────────────────────────────────────────────────────────────────

export default function AgentReasoningAnimation({ mono = false }: { mono?: boolean } = {}) {
  const P = mono ? MONO : GOLD
  const {
    containerRef,
    scenarioVisible,
    rootVisible,
    states,
    synthesisVisible,
    phase,
    hudStatus,
    gapCount,
  } = useReasoningLoop()

  return (
    <div
      ref={containerRef}
      className="relative w-full max-w-[1060px] rounded-xl overflow-hidden mx-auto flex flex-col"
      style={{
        backgroundColor: '#0a0a08',
        color: '#d4d4d4',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 40px 80px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04) inset',
      }}
    >
      {/* Header */}
      <div
        className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: ZINC_LINE }}
      >
        <div className="flex items-center gap-2">
          <GitBranch className="w-3.5 h-3.5" style={{ color: '#9a8a70' }} />
          <span className="text-[10px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
            Compliance Analysis · CA Audit
          </span>
          <span
            className="text-[7.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono"
            style={{ color: P.amber, border: `1px solid ${P.amber}55` }}
          >
            SB 553 · LIVE
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[8.5px]">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ backgroundColor: P.live }} />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5" style={{ backgroundColor: P.live }} />
          </span>
          <span style={{ color: '#9a8a70' }}>Live Engine · Cal/OSHA</span>
        </div>
      </div>

      {/* Body */}
      <div
        className="relative overflow-hidden"
        style={{
          height: 520,
          transition: 'opacity 600ms ease',
          opacity: phase === 'reset' ? 0.15 : 1,
        }}
      >
        {/* Scan-line bg */}
        <div
          className="absolute inset-0 pointer-events-none opacity-[0.06]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />

        {/* Floating particles for ambient feel */}
        <ParticleField p={P} />

        {/* Tree */}
        <div className="relative w-full h-full px-4 py-4 flex flex-col">
          {/* SCENARIO CARD */}
          <AnimatePresence>
            {scenarioVisible && !synthesisVisible && (
              <motion.div
                key="scenario"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.4 }}
                className="relative mx-auto"
                style={{ width: 540 }}
              >
                <div
                  className="rounded-lg px-5 py-3.5 flex items-start gap-3"
                  style={{
                    backgroundColor: mono ? 'rgba(245,158,11,0.04)' : 'rgba(248,113,113,0.05)',
                    border: `1px solid ${P.red}20`,
                    boxShadow: `0 0 12px ${P.red}0d`,
                  }}
                >
                  <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: P.red }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-[12px] font-semibold" style={{ color: P.red }}>
                        {SCENARIO.bill}
                      </span>
                      <span className="font-mono text-[8.5px] uppercase tracking-wider" style={{ color: '#9a8a70' }}>
                        {SCENARIO.effective}
                      </span>
                    </div>
                    <div className="font-mono text-[10px] mt-1" style={{ color: '#cbd5e1' }}>
                      {SCENARIO.facts}
                    </div>
                    <div className="font-mono text-[10px] mt-1.5 flex items-baseline gap-2">
                      <span style={{ color: '#6a737d' }}>Exposure</span>
                      <span className="font-semibold tabular-nums text-[13px]" style={{ color: P.red }}>
                        {SCENARIO.exposure}
                      </span>
                      <span className="text-[8.5px]" style={{ color: '#6a737d' }}>
                        {SCENARIO.exposureSubtext}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>
                      Gaps
                    </div>
                    <div className="font-mono tabular-nums text-[20px] font-bold" style={{ color: gapCount > 0 ? P.red : '#3f3f46' }}>
                      {gapCount}/5
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ROOT + TREE — only visible during audit phase */}
          {!synthesisVisible && (
            <div className="relative flex-1 mt-4">
              {/* SVG connector layer */}
              <ConnectorSvg rootVisible={rootVisible} states={states} p={P} />

              {/* Root node */}
              <AnimatePresence>
                {rootVisible && (
                  <motion.div
                    key="root"
                    initial={{ opacity: 0, scale: 0.92 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.35 }}
                    className="absolute"
                    style={{ top: 0, left: '50%', transform: 'translateX(-50%)' }}
                  >
                    <RootNode p={P} />
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Decision columns */}
              <div
                className="absolute inset-x-0 grid grid-cols-5 gap-3 px-3"
                style={{ top: 72 }}
              >
                {DECISIONS.map((d, i) => (
                  <DecisionColumn key={d.id} decision={d} state={states[i]} index={i} p={P} />
                ))}
              </div>
            </div>
          )}

          {/* SYNTHESIS CARD — centered both axes when shown alone */}
          <div className="absolute inset-0 flex items-center justify-center px-4 pointer-events-none">
            <AnimatePresence>
              {synthesisVisible && (
                <motion.div
                  key="synthesis"
                  initial={{ opacity: 0, y: 30, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.5, ease: 'easeOut' }}
                  className="pointer-events-auto"
                  style={{ width: 820, maxWidth: '100%' }}
                >
                  <SynthesisCard p={P} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* Footer HUD */}
      <div
        className="relative px-4 py-2 border-t flex items-center justify-between shrink-0 font-mono text-[7.5px]"
        style={{ borderColor: ZINC_LINE, backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span style={{ color: '#6a737d' }}>Status</span>
          <span
            className="truncate"
            style={{ color: phase === 'synthesized' ? P.live : P.amber }}
          >
            {hudStatus}
          </span>
          <span style={{ color: P.amber, animation: 'reasoning-cursor 0.9s steps(1) infinite' }}>▎</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span style={{ color: '#6a737d' }}>Jurisdiction</span>
          <span style={{ color: '#9a8a70' }}>CA</span>
          <span style={{ color: '#3f3f46' }}>·</span>
          <span style={{ color: '#9a8a70' }}>Cal/OSHA</span>
        </div>
      </div>

      <style>{`
        @keyframes reasoning-cursor {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
        @keyframes weigh-pulse {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
