import type { LucideIcon } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
import { TicketPanel } from './Ticket'

export interface Stamp {
  icon: LucideIcon
  label: string
  punched: boolean
}

export function PunchCard({ stamps }: { stamps: Stamp[] }) {
  const reduce = useReducedMotion()

  return (
    <TicketPanel className="bg-tu-paper p-6 text-tu-ink shadow-[0_20px_45px_rgba(76,55,29,0.12)] sm:rounded-2xl sm:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b-2 border-tu-ink pb-4">
        <div>
          <p className="font-mono text-xs font-bold uppercase tracking-wider text-tu-ink/55">Loyalty card · 4/6 punched</p>
          <h3 className="mt-1 font-display text-2xl font-semibold">Keep showing up.</h3>
        </div>
        <span className="font-mono text-xs text-tu-ink/50">NO. 0048</span>
      </div>
      <div className="mb-6 mt-5 h-1 overflow-hidden rounded-full bg-tu-ink/10">
        <div className="h-full w-2/3 rounded-full bg-tu-accent" />
      </div>
      <div className="grid grid-cols-3 gap-4 sm:grid-cols-6 sm:gap-3">
        {stamps.map(({ icon: Icon, label, punched }, i) => (
          <motion.div
            key={label}
            initial={reduce ? false : { opacity: 0, scale: 0.65, rotate: -12 }}
            whileInView={{ opacity: 1, scale: 1, rotate: punched ? -2 : 0 }}
            viewport={{ once: true, margin: '-50px' }}
            transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 360, damping: 16, delay: i * 0.09 }}
            className="flex flex-col items-center gap-2 text-center"
          >
            <span className={`flex h-14 w-14 items-center justify-center rounded-full ${punched ? 'border border-tu-accent/60 bg-tu-accent text-black shadow-[inset_0_2px_3px_rgba(255,255,255,0.35),0_4px_0_#8f4d0c]' : 'border-2 border-dashed border-tu-ink/35 text-tu-ink/35'}`}>
              <Icon className="h-6 w-6" />
            </span>
            <span className="text-xs font-semibold leading-tight">{label}</span>
          </motion.div>
        ))}
      </div>
    </TicketPanel>
  )
}
