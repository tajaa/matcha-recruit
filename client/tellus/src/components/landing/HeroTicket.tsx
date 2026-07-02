import { useEffect } from 'react'
import { motion, useReducedMotion, useMotionValue, useTransform, animate } from 'framer-motion'
import { Camera, Flame, Star, Store } from 'lucide-react'

function usePointCounter(target: number, reduce: boolean, delay = 0.45) {
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

// Signature hero visual — feedback "prints" as a ticket. Paper-toned, so
// every color class below is remapped to tu-ink/tu-paper (NOT the dark-panel
// tu-dim/tu-faint tokens used elsewhere, which would be invisible here).
export function HeroTicket() {
  const reduce = useReducedMotion()
  const points = usePointCounter(185, !!reduce)

  return (
    <div className="relative mx-auto w-full max-w-sm">
      <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-tu-accent/10 blur-2xl" />
      <motion.div
        initial={reduce ? false : { y: -48, opacity: 0, rotate: -3 }}
        animate={{ y: 0, opacity: 1, rotate: -1 }}
        transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 300, damping: 18, mass: 1 }}
        className="tu-tear-edge rounded-sm bg-tu-paper p-5 pb-7 text-tu-ink drop-shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-tu-ink/15 pb-3">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-tu-ink/10 text-tu-ink"><Store className="h-4 w-4" /></span>
            <span className="text-sm font-semibold">Corner Coffee Co.</span>
          </div>
          <span className="rounded-sm bg-tu-good/15 px-2 py-0.5 text-[11px] font-mono font-semibold uppercase text-tu-good">Approved</span>
        </div>
        <div className="mt-3 flex gap-2 text-xs text-tu-ink/60">
          <span className="rounded-sm bg-tu-paper-dim px-2.5 py-1">😊 Positive</span>
          <span className="rounded-sm bg-tu-paper-dim px-2.5 py-1">Service</span>
          <span className="flex items-center gap-1 rounded-sm bg-tu-paper-dim px-2.5 py-1"><Camera className="h-3 w-3" /> Photo</span>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-tu-ink/70">"Staff remembered my order and the new oat latte is great — fix the sticky door though!"</p>
        <div className="mt-4 flex items-center justify-between rounded-sm bg-tu-paper-dim px-4 py-3">
          <span className="font-mono text-xs font-medium uppercase tracking-wide text-tu-ink/60">Reward credited</span>
          <span className="flex items-center gap-1 font-mono text-lg font-black text-tu-accent">
            <Star className="h-4 w-4 fill-tu-accent" /> +<motion.span>{points}</motion.span> pts
          </span>
        </div>
      </motion.div>
      <div className="absolute -bottom-4 -right-4 flex items-center gap-1.5 rounded-sm border border-tu-border bg-tu-panel px-3 py-1.5 text-xs font-mono font-semibold shadow-lg">
        <Flame className="h-3.5 w-3.5 text-tu-accent" /> 4-day streak
      </div>
    </div>
  )
}
