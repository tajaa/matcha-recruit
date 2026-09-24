import type { LucideIcon } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight, CalendarDays, Gift, Megaphone, Pin, Store } from 'lucide-react'
import { Link } from 'react-router-dom'
import { StudioBoardIllustration } from './LandingArtwork'

interface Note {
  kind: 'deal' | 'event' | 'update' | 'promo'
  title: string
  place: string
  rotate: number
}

const NOTE_META: Record<Note['kind'], { icon: LucideIcon; label: string; color: string }> = {
  deal: { icon: Gift, label: 'Deal', color: 'bg-[#f5d79b]' },
  event: { icon: CalendarDays, label: 'Event', color: 'bg-[#c9dfd1]' },
  update: { icon: Megaphone, label: 'Update', color: 'bg-[#f3c4a9]' },
  promo: { icon: Store, label: 'Promo', color: 'bg-[#d5c8e8]' },
}

export function RegularsBoard({ notes }: { notes: Note[] }) {
  const reduce = useReducedMotion()

  return (
    <div className="tu-cork tu-tear-edge relative overflow-hidden rounded-2xl p-5 sm:p-8">
      <Pin className="absolute left-5 top-5 h-5 w-5 rotate-12 text-[#d8b27b] drop-shadow sm:left-8 sm:top-8" aria-hidden />
      <StudioBoardIllustration className="pointer-events-none absolute -right-5 -top-2 w-40 opacity-20 sm:right-8 sm:top-5" />
      <div className="relative z-10 mx-auto grid max-w-5xl gap-8 lg:grid-cols-[0.8fr_1.2fr] lg:items-center">
        <div className="text-[#f7ead0]">
          <div className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-[#f3c47d]"><Megaphone className="h-4 w-4" /> Regulars board</div>
          <h3 className="mt-3 font-display text-3xl font-semibold leading-tight sm:text-4xl">Good spots have a board.</h3>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-[#ead7ba]">Join the board your favorite spots run themselves — first look at drops, pop-ups, and freebies, straight from the people behind the counter. Brands love it because it&apos;s never a stranger&apos;s spam.</p>
          <ul className="mt-5 space-y-2 text-sm text-[#f7ead0]">
            {['Ask in, no spam out.', 'Hear it first.', 'Run by real staff.'].map((item) => <li key={item} className="flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-tu-accent" />{item}</li>)}
          </ul>
          <Link to="/places" className="mt-6 inline-flex items-center gap-1.5 rounded-lg bg-tu-accent px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-tu-accent-soft">Find a regulars board <ArrowRight className="h-4 w-4" /></Link>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {notes.map((note, i) => {
            const meta = NOTE_META[note.kind]
            const Icon = meta.icon
            return (
              <motion.div
                key={`${note.place}-${note.title}`}
                initial={reduce ? false : { opacity: 0, y: 18, rotate: note.rotate - 4 }}
                whileInView={{ opacity: 1, y: 0, rotate: note.rotate }}
                whileHover={reduce ? undefined : { y: -5, rotate: 0, transition: { type: 'spring', stiffness: 350, damping: 18 } }}
                viewport={{ once: true, margin: '-40px' }}
                transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 300, damping: 20, delay: i * 0.1 }}
                className={`tu-pushpin relative min-h-36 rounded-md ${meta.color} p-5 pt-7 text-tu-ink shadow-[0_14px_20px_rgba(34,18,8,0.18)]`}
              >
                <div className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-tu-ink/55"><Icon className="h-3.5 w-3.5" /> {meta.label}</div>
                <p className="mt-2 font-display text-lg font-semibold leading-tight">{note.title}</p>
                <p className="mt-3 text-xs font-semibold text-tu-ink/60">{note.place}</p>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
