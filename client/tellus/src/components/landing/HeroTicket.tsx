import { useEffect } from 'react'
import { motion, useReducedMotion, useMotionValue, useTransform, animate } from 'framer-motion'
import { Camera, Flame, Star, Store } from 'lucide-react'

function usePointCounter(target: number, reduce: boolean, delay = 0.55) {
  const value = useMotionValue(reduce ? target : 0)
  const rounded = useTransform(value, (v) => Math.round(v))
  useEffect(() => {
    if (reduce) return
    const controls = animate(value, target, { duration: 0.7, delay, ease: 'easeOut' })
    return controls.stop
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduce, target])
  return rounded
}

const chipVariants = {
  hidden: { opacity: 0, y: 8 },
  shown: (i: number) => ({ opacity: 1, y: 0, transition: { duration: 0.3, delay: 0.55 + i * 0.08 } }),
}

// Signature hero visual — feedback "prints" as a ticket, then its own
// contents settle in (chips stagger, reward bar shines, icons idle) so the
// card keeps reading as "alive" instead of a static screenshot. Paper-toned,
// so every color class is remapped to tu-ink/tu-paper — the dark-panel
// tu-dim/tu-faint tokens used elsewhere would be invisible here.
export function HeroTicket() {
  const reduce = useReducedMotion()
  const points = usePointCounter(185, !!reduce)
  const chips = [
    <span key="sentiment" className="rounded-sm bg-tu-paper-dim px-2.5 py-1">😊 Positive</span>,
    <span key="category" className="rounded-sm bg-tu-paper-dim px-2.5 py-1">Service</span>,
    <span key="photo" className="flex items-center gap-1 rounded-sm bg-tu-paper-dim px-2.5 py-1"><Camera className="h-3 w-3" /> Photo</span>,
  ]

  return (
    <div className="relative mx-auto w-full max-w-sm">
      <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-tu-accent/10 blur-2xl" />

      {/* Stacked ticket peeking out behind — depth + "there's more than one" */}
      <motion.div
        aria-hidden
        initial={reduce ? false : { y: -40, opacity: 0, rotate: -3 }}
        animate={{ y: 10, opacity: 1, rotate: -6 }}
        transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 260, damping: 20, delay: 0.05 }}
        className="tu-tear-edge absolute inset-x-3 top-2 -z-[1] rounded-sm bg-tu-paper-dim/80"
        style={{ height: '92%' }}
      />

      <motion.div
        initial={reduce ? false : { y: -48, opacity: 0, rotate: -3 }}
        animate={{ y: 0, opacity: 1, rotate: -1 }}
        transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 300, damping: 18, mass: 1 }}
        className="tu-tear-edge rounded-sm bg-tu-paper p-5 pb-7 text-tu-ink drop-shadow-2xl"
      >
        <motion.div
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.35, duration: 0.3 }}
          className="flex items-center justify-between border-b border-tu-ink/15 pb-3"
        >
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-tu-ink/10 text-tu-ink"><Store className="h-4 w-4" /></span>
            <span className="text-sm font-semibold">Corner Coffee Co.</span>
          </div>
          <span className="rounded-sm bg-tu-good/15 px-2 py-0.5 text-[11px] font-mono font-semibold uppercase text-tu-good">Approved</span>
        </motion.div>

        <div className="mt-3 flex gap-2 text-xs text-tu-ink/60">
          {chips.map((chip, i) => (
            <motion.span key={i} custom={i} initial={reduce ? false : 'hidden'} animate="shown" variants={chipVariants}>
              {chip}
            </motion.span>
          ))}
        </div>

        <motion.p
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.85, duration: 0.35 }}
          className="mt-3 text-sm leading-relaxed text-tu-ink/70"
        >
          "Staff remembered my order and the new oat latte is great — fix the sticky door though!"
        </motion.p>

        <motion.div
          initial={reduce ? false : { opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 1.05, duration: 0.3 }}
          className="relative mt-4 flex items-center justify-between overflow-hidden rounded-sm bg-tu-paper-dim px-4 py-3"
        >
          <span aria-hidden className="tu-shimmer-sweep pointer-events-none absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-white/40 to-transparent" />
          <span className="font-mono text-xs font-medium uppercase tracking-wide text-tu-ink/60">Reward credited</span>
          <span className="flex items-center gap-1 font-mono text-lg font-black text-tu-accent">
            <motion.span
              animate={reduce ? undefined : { scale: [1, 1.1, 1] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Star className="h-4 w-4 fill-tu-accent" />
            </motion.span>
            +<motion.span>{points}</motion.span> pts
          </span>
        </motion.div>
      </motion.div>

      <motion.div
        initial={reduce ? false : { opacity: 0, scale: 0.8, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 300, damping: 16, delay: 1.1 }}
        className="absolute -bottom-4 -right-4 flex items-center gap-1.5 rounded-sm border border-tu-border bg-tu-panel px-3 py-1.5 text-xs font-mono font-semibold shadow-lg"
      >
        <motion.span
          animate={reduce ? undefined : { rotate: [-6, 6, -6] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Flame className="h-3.5 w-3.5 text-tu-accent" />
        </motion.span>
        4-day streak
      </motion.div>
    </div>
  )
}
