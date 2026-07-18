import { motion } from 'framer-motion'
import { Scale, Bell, FileText, Library, BadgeCheck, ListChecks } from 'lucide-react'

import { PulseDot } from './PulseDot'
import { BG, DISPLAY, GREEN, INK, LINE, MUTED } from './theme'

// ---------------------------------------------------------------------------
// Coverage recap — a hairline feature grid summarizing everything the product
// covers at a glance, after the four detailed pillar rows. Icon tile + serif
// heading + caption, with a tiny grayscale corner glyph carrying one green
// mark (the same "resolves to one node" motif as the pillar instruments).
// ---------------------------------------------------------------------------

function GlyphStack() {
  return (
    <div className="flex flex-col items-end gap-1">
      {[16, 12, 9].map((w, i) => (
        <span key={w} className="h-[3px] rounded-full" style={{ width: w, backgroundColor: i === 2 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphPulse() {
  return <PulseDot size={7} />
}
function GlyphDoc() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[18, 14, 18, 11].map((w, i) => (
        <span key={i} className="h-[2px] rounded-full" style={{ width: w, backgroundColor: i === 1 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphLifecycle() {
  return (
    <div className="flex items-center gap-1.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="rounded-full"
          style={{ width: 6, height: 6, backgroundColor: i === 1 ? GREEN : 'transparent', border: i === 1 ? 'none' : `1px solid ${LINE}` }}
        />
      ))}
    </div>
  )
}
function GlyphCountdown() {
  return (
    <div className="flex items-center gap-1">
      {[9, 7, 5].map((w, i) => (
        <span key={i} className="rounded-full" style={{ width: w, height: w, backgroundColor: i === 2 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphChecks() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[0, 1, 2].map((i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="h-[2px] rounded-full" style={{ width: 12, backgroundColor: LINE }} />
          <span className="rounded-full" style={{ width: 4, height: 4, backgroundColor: i === 0 ? GREEN : MUTED }} />
        </span>
      ))}
    </div>
  )
}

const COVERAGE: { id: string; icon: typeof Scale; title: string; caption: string; glyph: () => React.ReactElement }[] = [
  {
    id: 'jurisdiction',
    icon: Scale,
    title: 'Jurisdiction stack',
    caption: 'Everything that applies where you operate, in one place and always current.',
    glyph: GlyphStack,
  },
  {
    id: 'change',
    icon: Bell,
    title: 'Change alerts',
    caption: 'The law moves before you do — so you hear about it before it becomes a problem.',
    glyph: GlyphPulse,
  },
  {
    id: 'handbook',
    icon: FileText,
    title: 'Handbook audit',
    caption: 'See exactly where your handbook falls short of your state, in a report you can hand to counsel.',
    glyph: GlyphDoc,
  },
  {
    id: 'policy',
    icon: Library,
    title: 'Policy library',
    caption: 'Every policy kept current in one place, so nothing quietly goes out of date.',
    glyph: GlyphLifecycle,
  },
  {
    id: 'credential',
    icon: BadgeCheck,
    title: 'Credentialing',
    caption: 'The right credentials tracked to the date, flagged long before anything lapses.',
    glyph: GlyphCountdown,
  },
  {
    id: 'actions',
    icon: ListChecks,
    title: 'Owned actions',
    caption: 'Every gap becomes someone’s job with a due date — nothing sits unresolved.',
    glyph: GlyphChecks,
  },
]

export function CoverageGrid() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-12 sm:mb-16">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-3 sm:mb-4" style={{ color: MUTED }}>
            The whole stack
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            Everything compliance, in one place.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Six capabilities, one system. Each stands on its own; together they
            cover the compliance surface a growing team can’t afford to miss.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
          {COVERAGE.map((f, i) => {
            const Icon = f.icon
            const Glyph = f.glyph
            return (
              <motion.div
                key={f.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.5, delay: (i % 3) * 0.08, ease: 'easeOut' }}
                className="p-6 sm:p-8 flex flex-col"
                style={{ backgroundColor: BG }}
              >
                <div className="flex items-start justify-between mb-5">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: 'rgba(31,29,26,0.06)' }}>
                    <Icon className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  <div className="h-10 flex items-center">
                    <Glyph />
                  </div>
                </div>
                <h3 className="text-lg sm:text-xl mb-2" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
                  {f.title}
                </h3>
                <p className="text-sm" style={{ color: MUTED, lineHeight: 1.6 }}>
                  {f.caption}
                </p>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
