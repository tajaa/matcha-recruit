import { motion, type HTMLMotionProps } from 'framer-motion'

// Shared ticket-stub shape: a rectangular paper panel with a perforated tear
// edge along the bottom (see .tu-tear-edge in index.css), the connective
// motif reused across the hero ticket and the step stubs.
export function TicketPanel({ className = '', children, ...props }: HTMLMotionProps<'div'>) {
  return (
    <motion.div
      // Hover gets its own inline transition so a caller-supplied `transition`
      // prop (e.g. a whileInView reveal's duration/delay) governs the
      // entrance only, not the hover spring.
      whileHover={{ y: -4, rotate: -0.75, transition: { type: 'spring', stiffness: 400, damping: 25 } }}
      className={`tu-tear-edge rounded-sm ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  )
}
