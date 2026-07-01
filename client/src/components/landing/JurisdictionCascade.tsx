import { useRef, useState, useEffect } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'
import { SCAN_LINE_BG } from './shared'

// Illustrative — mirrors TimelineConstructor's visual vocabulary (same page,
// ER Copilot section) so the two "engine" graphics read as one family.
const STEPS = [
  {
    title: 'Federal Baseline Checked',
    doc: 'FLSA, OSHA, FMLA',
    type: 'verified',
    desc: 'Federal floor established.',
  },
  {
    title: 'State Rules Layered',
    doc: 'CA FEHA, WA PFML',
    type: 'verified',
    desc: 'State requirements applied.',
  },
  {
    title: 'Local Ordinance Conflict',
    doc: 'LA MWO vs. CA minimum wage',
    type: 'alert',
    desc: 'Local rate exceeds state floor.',
  },
  {
    title: 'Compliance Matrix Updated',
    doc: 'jurisdiction_matrix.pdf',
    type: 'pending',
    desc: 'Highest-obligation rule applied.',
  },
]

/* ── Jurisdiction Cascade (Compliance Engine) ─────────────────── */
export function JurisdictionCascade() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const [currentStep, setCurrentStep] = useState(0)

  useEffect(() => {
    if (!inView) {
      setCurrentStep(0)
      return
    }
    setCurrentStep(1)
    const interval = setInterval(() => {
      setCurrentStep(s => s >= 4 ? 1 : s + 1)
    }, 2000)
    return () => clearInterval(interval)
  }, [inView])

  return (
    <div ref={ref} className="relative h-[400px] lg:h-[460px] overflow-hidden bg-zinc-950 flex flex-col items-center justify-center p-6" style={{ backgroundImage: SCAN_LINE_BG }}>

      {/* Background Grid */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-amber-900/10 via-zinc-950 to-zinc-950 pointer-events-none" />

      {/* Connection Line — cascades from Federal (broadest) to Local (most specific) */}
      <div className="absolute left-10 right-10 top-1/2 h-px bg-zinc-800" />
      <motion.div
        className="absolute left-10 h-[2px] bg-amber-500 shadow-[0_0_10px_#f59e0b]"
        initial={{ width: '0%' }}
        animate={{ width: currentStep === 0 ? '0%' : currentStep === 1 ? '16%' : currentStep === 2 ? '42%' : currentStep === 3 ? '68%' : '94%' }}
        transition={{ duration: 1.5, ease: 'easeInOut' }}
        style={{ top: 'calc(50% - 0.5px)', maxWidth: 'calc(100% - 5rem)' }}
      />

      <div className="relative w-full h-full flex justify-between items-center z-10 px-4 sm:px-8">
        {STEPS.map((step, idx) => {
          const isActive = currentStep >= idx + 1
          const isCurrent = currentStep === idx + 1
          const isAlert = step.type === 'alert'

          return (
            <div key={idx} className="relative flex flex-col items-center justify-center w-1/4">

              {/* Top Source Node */}
              <motion.div
                className={`absolute bottom-10 w-full max-w-[130px] border p-2 bg-zinc-950/90 rounded backdrop-blur-md ${
                  isActive ? (isAlert ? 'border-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.2)]' : 'border-amber-500/30') : 'border-zinc-800 opacity-20'
                }`}
                initial={{ y: 20, opacity: 0 }}
                animate={isActive ? { y: 0, opacity: 1 } : { y: 20, opacity: 0 }}
                transition={{ duration: 0.5, delay: 0.2 }}
              >
                <div className="text-[11px] text-zinc-500 uppercase tracking-widest mb-1.5 text-center">Source</div>
                <div className={`text-xs sm:text-[11px] font-mono text-center break-words ${isAlert ? 'text-amber-400' : 'text-zinc-300'}`}>
                  {step.doc}
                </div>
              </motion.div>

              {/* Connecting Line to Node */}
              <motion.div
                className={`absolute bottom-4 w-px h-6 ${isActive ? (isAlert ? 'bg-amber-500' : 'bg-amber-500/50') : 'bg-transparent'}`}
                initial={{ scaleY: 0 }}
                animate={isActive ? { scaleY: 1 } : { scaleY: 0 }}
                style={{ originY: 1 }}
                transition={{ duration: 0.3 }}
              />

              {/* Central Node */}
              <motion.div
                className={`relative w-4 h-4 rounded-full border-2 flex items-center justify-center bg-zinc-950 z-20 ${
                  isActive
                    ? (isAlert ? 'border-amber-400' : 'border-amber-500')
                    : 'border-zinc-700'
                }`}
                animate={isCurrent && isAlert ? { scale: [1, 1.3, 1] } : { scale: 1 }}
                transition={{ duration: 1, repeat: isCurrent && isAlert ? Infinity : 0 }}
              >
                {isActive && (
                  <div className={`w-1.5 h-1.5 rounded-full ${isAlert ? 'bg-amber-400' : 'bg-amber-500'}`} />
                )}
                {isCurrent && isAlert && (
                  <motion.div
                    className="absolute inset-0 rounded-full border border-amber-400"
                    initial={{ scale: 1, opacity: 1 }}
                    animate={{ scale: 2.5, opacity: 0 }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                )}
              </motion.div>

              {/* Connecting Line to Bottom */}
              <motion.div
                className={`absolute top-4 w-px h-6 ${isActive ? (isAlert ? 'bg-amber-500' : 'bg-amber-500/50') : 'bg-transparent'}`}
                initial={{ scaleY: 0 }}
                animate={isActive ? { scaleY: 1 } : { scaleY: 0 }}
                style={{ originY: 0 }}
                transition={{ duration: 0.3 }}
              />

              {/* Bottom Info Node */}
              <motion.div
                className={`absolute top-10 flex flex-col items-center text-center w-full px-1 ${isActive ? 'opacity-100' : 'opacity-20'}`}
                initial={{ y: -10, opacity: 0 }}
                animate={isActive ? { y: 0, opacity: 1 } : { y: -10, opacity: 0 }}
                transition={{ duration: 0.5, delay: 0.4 }}
              >
                <div className={`text-xs sm:text-[11px] font-[Orbitron] font-bold tracking-widest uppercase mb-1.5 ${isAlert ? 'text-amber-400' : 'text-zinc-200'}`}>
                  {step.title}
                </div>
                <div className="text-xs text-zinc-500 leading-tight">
                  {step.desc}
                </div>
              </motion.div>

            </div>
          )
        })}
      </div>

      {/* Terminal Overlay for Conflict */}
      <AnimatePresence>
        {(currentStep === 3 || currentStep === 4) && (
          <motion.div
            className="absolute bottom-6 left-1/2 -translate-x-1/2 w-[85%] max-w-sm border border-amber-500/40 bg-amber-950/60 backdrop-blur-md p-4 rounded z-30 shadow-[0_10px_30px_-10px_rgba(245,158,11,0.3)]"
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            transition={{ duration: 0.4, type: 'spring' }}
          >
            <div className="text-[11px] text-amber-400 uppercase tracking-widest mb-2.5 flex items-center gap-2 font-bold">
              <span className="w-2 h-2 bg-amber-500 rounded-full animate-pulse shadow-[0_0_8px_#f59e0b]" />
              Agent Alert: Rate Conflict
            </div>
            <div className="text-xs font-mono text-amber-100/90 leading-relaxed bg-black/40 p-2.5 rounded border border-amber-500/20">
              <span className="text-amber-500 font-bold">State:</span> CA minimum wage is $16.50/hr.<br />
              <span className="text-amber-500 font-bold">Local:</span> LA MWO sets $17.87/hr.<br />
              <motion.div
                className="mt-2 text-amber-300 font-bold"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.8 }}
              >
                &gt; No preemption — higher local rate applies. Flagging for payroll.
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* HUD */}
      <div className="absolute top-4 left-4 flex flex-col gap-1 z-30">
        <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold">Jurisdiction Engine</div>
        <div className="text-xs text-amber-500 font-mono flex items-center gap-2">
          <span>STATUS: {currentStep === 0 ? 'AWAITING SCAN' : currentStep >= 4 ? 'MATRIX READY' : 'MAPPING...'}</span>
          {currentStep > 0 && currentStep < 4 && <span className="animate-pulse">▊</span>}
        </div>
      </div>

      <div className="absolute top-4 right-4 flex items-center gap-2 z-30">
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${currentStep === 3 ? 'bg-amber-400' : 'bg-zinc-500'}`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${currentStep === 3 ? 'bg-amber-500' : 'bg-zinc-600'}`} />
        </span>
        <span className="text-xs uppercase font-bold tracking-widest text-zinc-500">
          Auto-Mapper
        </span>
      </div>

    </div>
  )
}
