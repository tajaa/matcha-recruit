import { useRef, useState, useEffect } from 'react'
import { motion, useInView, AnimatePresence } from 'framer-motion'
import { SCAN_LINE_BG } from './shared'

const STEPS = [
  { 
    title: 'Incident Logged', 
    doc: 'HR_TICKET_492.eml',
    type: 'verified',
    desc: 'Employee filed complaint.'
  },
  { 
    title: 'Statements Cross-Referenced', 
    doc: 'witness_A.docx, witness_B.docx',
    type: 'verified',
    desc: 'NLP extraction of key events.'
  },
  { 
    title: 'Timeline Contradiction', 
    doc: 'Timestamp mismatch detected',
    type: 'alert',
    desc: 'Witness statement conflicts with system logs.'
  },
  { 
    title: 'Draft Memo Generated', 
    doc: 'investigation_summary.pdf',
    type: 'pending',
    desc: 'Ready for legal counsel review.'
  },
]

/* ── Timeline Constructor (ER Copilot) ────────────────────────── */
export function TimelineConstructor() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-80px' })
  const [currentStep, setCurrentStep] = useState(0)

  useEffect(() => {
    if (!inView) {
      setCurrentStep(0)
      return
    }
    const interval = setInterval(() => {
      setCurrentStep(s => (s + 1) % 6)
    }, 3000)
    return () => clearInterval(interval)
  }, [inView])

  return (
    <div ref={ref} className="relative h-80 lg:h-96 overflow-hidden bg-zinc-950 flex flex-col items-center justify-center p-6" style={{ backgroundImage: SCAN_LINE_BG }}>
      
      {/* Background Grid */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-amber-900/10 via-zinc-950 to-zinc-950 pointer-events-none" />

      {/* Connection Line */}
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
              
              {/* Top Document/Data Node */}
              <motion.div 
                className={`absolute bottom-10 w-full max-w-[120px] border p-2 bg-zinc-950/90 rounded backdrop-blur-md ${
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

      {/* Terminal Overlay for Discrepancy */}
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
              Agent Alert: Temporal Anomaly
            </div>
            <div className="text-xs font-mono text-amber-100/90 leading-relaxed bg-black/40 p-2.5 rounded border border-amber-500/20">
              <span className="text-amber-500 font-bold">Witness A:</span> "Incident occurred at 4:15 PM."<br/>
              <span className="text-amber-500 font-bold">Badge Log:</span> Subject exited building at 3:42 PM.<br/>
              <motion.div 
                className="mt-2 text-amber-300 font-bold"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.8 }}
              >
                &gt; Suggests witness statement inconsistency. Flagging for review.
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* HUD */}
      <div className="absolute top-4 left-4 flex flex-col gap-1 z-30">
        <div className="text-xs text-zinc-500 uppercase tracking-widest font-bold">ER Copilot Engine</div>
        <div className="text-xs text-amber-500 font-mono flex items-center gap-2">
          <span>STATUS: {currentStep === 0 ? 'AWAITING DOCS' : currentStep >= 4 ? 'MEMO READY' : 'ANALYZING...'}</span>
          {currentStep > 0 && currentStep < 4 && <span className="animate-pulse">▊</span>}
        </div>
      </div>
      
      <div className="absolute top-4 right-4 flex items-center gap-2 z-30">
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${currentStep === 3 ? 'bg-amber-400' : 'bg-zinc-500'}`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${currentStep === 3 ? 'bg-amber-500' : 'bg-zinc-600'}`} />
        </span>
        <span className="text-xs uppercase font-bold tracking-widest text-zinc-500">
          Auto-Investigator
        </span>
      </div>

    </div>
  )
}
