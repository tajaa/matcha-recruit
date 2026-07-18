import { motion } from 'framer-motion'
import type { DecisionState, Palette } from './types'

export function ConnectorSvg({ rootVisible, states, p }: { rootVisible: boolean; states: DecisionState[]; p: Palette }) {
  // 5 columns, root above. SVG sits over the tree area.
  const cols = 5
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      style={{ top: 18, height: 60 }}
      preserveAspectRatio="none"
    >
      {Array.from({ length: cols }).map((_, i) => {
        const xPct = ((i + 0.5) / cols) * 100
        const isActive = states[i].phase !== 'pending'
        return (
          <motion.line
            key={i}
            x1="50%"
            y1="6"
            x2={`${xPct}%`}
            y2="50"
            stroke={isActive ? p.amber : 'rgba(255,255,255,0.1)'}
            strokeWidth={isActive ? 1 : 0.7}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: rootVisible ? 1 : 0, opacity: rootVisible ? 1 : 0 }}
            transition={{ duration: 0.5, delay: i * 0.08 }}
            style={{
              filter: isActive ? `drop-shadow(0 0 3px ${p.amber}55)` : 'none',
              transition: 'stroke 240ms, filter 240ms',
            }}
          />
        )
      })}
    </svg>
  )
}
