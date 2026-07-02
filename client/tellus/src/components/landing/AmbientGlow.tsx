import { motion, useReducedMotion } from 'framer-motion'

// Two large blurred blobs drifting slowly behind hero/CTA content — ambient
// depth, not a focal effect. Frozen under reduced motion.
export function AmbientGlow() {
  const reduce = useReducedMotion()
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <motion.div
        className="absolute -left-24 top-[-10%] h-[26rem] w-[26rem] rounded-full bg-tu-accent/15 blur-3xl"
        animate={reduce ? undefined : { x: [0, 40, -10, 0], y: [0, -25, 15, 0] }}
        transition={{ duration: 17, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute right-[-10%] top-[15%] h-[22rem] w-[22rem] rounded-full bg-tu-text/[0.06] blur-3xl"
        animate={reduce ? undefined : { x: [0, -30, 15, 0], y: [0, 20, -15, 0] }}
        transition={{ duration: 14, repeat: Infinity, ease: 'easeInOut', delay: 1.5 }}
      />
    </div>
  )
}
