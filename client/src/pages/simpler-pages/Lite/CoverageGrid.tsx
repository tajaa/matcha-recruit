import { motion } from 'framer-motion'
import { ShieldAlert, Users, Brain, ClipboardList, FileText } from 'lucide-react'

import { BG, DISPLAY, GREEN, INK, LINE, MUTED } from './constants'

// ── Coverage recap ─────────────────────────────────────────────────────────

function GlyphBars() {
  return (
    <div className="flex items-end gap-1 h-6">
      {[10, 16, 12, 22, 14].map((h, i) => (
        <span key={i} className="w-[3px] rounded-full" style={{ height: h, backgroundColor: i === 3 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphPeople() {
  return (
    <div className="flex -space-x-1.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="rounded-full border"
          style={{ width: 10, height: 10, backgroundColor: i === 1 ? GREEN : BG, borderColor: i === 1 ? GREEN : LINE }}
        />
      ))}
    </div>
  )
}
function GlyphBrain() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[0, 1, 2].map((i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="rounded-full" style={{ width: 4, height: 4, backgroundColor: i === 0 ? GREEN : MUTED }} />
          <span className="h-[2px] rounded-full" style={{ width: i === 0 ? 16 : 12, backgroundColor: LINE }} />
        </span>
      ))}
    </div>
  )
}
function GlyphLog() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[16, 13, 16, 10].map((w, i) => (
        <span key={i} className="h-[2px] rounded-full" style={{ width: w, backgroundColor: i === 0 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphStack() {
  return (
    <div className="relative w-5 h-6">
      {[0, 1, 2].map((i) => (
        <span key={i} className="absolute rounded-sm border" style={{ width: 14, height: 16, left: i * 3, top: i * 2, borderColor: i === 0 ? GREEN : LINE, backgroundColor: BG }} />
      ))}
    </div>
  )
}

const COVERAGE: { id: string; icon: typeof ShieldAlert; title: string; caption: string; glyph: () => React.ReactElement }[] = [
  {
    id: 'incidents',
    icon: ShieldAlert,
    title: 'Incident reporting',
    caption: 'A link anyone can file into in seconds, so nothing goes unreported — and every record holds up later.',
    glyph: GlyphBars,
  },
  {
    id: 'hris',
    icon: Users,
    title: 'HRIS/CSV import',
    caption: 'Connect Gusto, Rippling, BambooHR, ADP — or drop in a CSV. One roster, everywhere it’s needed.',
    glyph: GlyphPeople,
  },
  {
    id: 'analysis',
    icon: Brain,
    title: 'IR analysis',
    caption: 'The repeat problems no single manager would catch, surfaced early enough to act on.',
    glyph: GlyphBrain,
  },
  {
    id: 'osha',
    icon: ClipboardList,
    title: 'OSHA logs',
    caption: 'The recordkeeping an audit asks for, kept current on its own and ready whenever you need it.',
    glyph: GlyphLog,
  },
  {
    id: 'resources',
    icon: FileText,
    title: 'HR resource hub',
    caption: 'The everyday HR documents your team reaches for, ready to use — no starting from a blank page.',
    glyph: GlyphStack,
  },
]

export function CoverageGrid() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-12 sm:mb-16">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-3 sm:mb-4" style={{ color: MUTED }}>
            The whole bundle
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            Everyday HR risk, covered.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Five tools, one bundle. Each stands on its own; together they cover
            the everyday HR risk surface for a small team without a dedicated
            compliance function.
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
