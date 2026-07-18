import { motion, AnimatePresence } from 'framer-motion'
import type { Decision, DecisionState, Palette } from './types'

export function DecisionColumn({ decision, state, index, p }: { decision: Decision; state: DecisionState; index: number; p: Palette }) {
  const isPending = state.phase === 'pending'
  const isWeighing = state.phase === 'weighing'
  const isCommitted = state.phase === 'committed' || state.phase === 'remediated'
  const showRemediation = state.phase === 'remediated'

  const accentColor = decision.result === 'GAP' ? p.red : p.emerald

  return (
    <div className="relative flex flex-col items-center gap-1.5">
      {/* Weighing strip — candidate § citations cycling */}
      <div className="h-4 flex items-center justify-center w-full">
        <AnimatePresence>
          {isWeighing && (
            <motion.div
              key="weighing"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="font-mono text-[8px] tabular-nums"
              style={{ color: p.amber, animation: 'weigh-pulse 0.6s ease-in-out infinite' }}
            >
              {decision.weighing[state.weighIdx]}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Decision node */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{
          opacity: isPending ? 0.3 : 1,
          y: 0,
          scale: isWeighing ? 1.04 : 1,
        }}
        transition={{ duration: 0.35, delay: index * 0.06 }}
        className="rounded-md w-full px-2.5 py-2 text-center"
        style={{
          backgroundColor: 'rgba(20,20,16,0.85)',
          backdropFilter: 'blur(6px)',
          border: `1px solid ${
            isCommitted ? `${accentColor}40` : isWeighing ? `${p.amber}40` : 'rgba(255,255,255,0.07)'
          }`,
          boxShadow: isWeighing
            ? `0 0 8px ${p.amber}16`
            : isCommitted
              ? `0 0 8px ${accentColor}16`
              : 'none',
          transition: 'border-color 220ms, box-shadow 220ms',
        }}
      >
        <div className="font-mono text-[9px] uppercase tracking-wider" style={{ color: '#cbd5e1' }}>
          {decision.label}
        </div>
        {isCommitted && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
            className="font-mono text-[8.5px] mt-0.5"
            style={{ color: accentColor }}
          >
            {decision.cite}
          </motion.div>
        )}
      </motion.div>

      {/* Result badge */}
      <AnimatePresence>
        {isCommitted && (
          <motion.div
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 22 }}
            className="rounded-full px-2 py-[2px] font-mono text-[9px] font-bold tracking-wider uppercase flex items-center gap-1"
            style={{
              color: accentColor,
              backgroundColor: `${accentColor}10`,
              border: `1px solid ${accentColor}2a`,
            }}
          >
            <span>{decision.result === 'GAP' ? '✗' : '✓'}</span>
            <span>{decision.result}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Question (only shown briefly during commit) */}
      <AnimatePresence>
        {isCommitted && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            transition={{ duration: 0.3 }}
            className="font-mono text-[8px] italic text-center px-1"
            style={{ color: '#6a737d' }}
          >
            "{decision.question}"
          </motion.div>
        )}
      </AnimatePresence>

      {/* Remediation sprout */}
      <AnimatePresence>
        {showRemediation && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.32, ease: 'easeOut' }}
            className="rounded-md w-full px-2.5 py-2 text-center mt-1"
            style={{
              backgroundColor: 'rgba(255,255,255,0.02)',
              border: `1px solid ${p.emerald}24`,
              boxShadow: `0 0 6px ${p.emerald}0e`,
            }}
          >
            <div className="font-mono text-[7.5px] uppercase tracking-wider mb-0.5" style={{ color: p.emerald }}>
              Suggested fix
            </div>
            <div className="font-mono text-[9px] leading-tight" style={{ color: '#cbd5e1' }}>
              {decision.remediation}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
