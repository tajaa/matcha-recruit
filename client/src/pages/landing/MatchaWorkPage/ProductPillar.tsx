import { INK, BG, MUTED, LINE, DISPLAY } from './constants'
import type { Pillar } from './data'
import { PillarVisual } from './PillarVisual'

// ---------------------------------------------------------------------------
// Product pillar section
// ---------------------------------------------------------------------------

export function ProductPillar({ pillar, reverse }: { pillar: Pillar; reverse: boolean }) {
  return (
    <section className="py-16 sm:py-24 md:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div
          className={`grid md:grid-cols-2 gap-10 md:gap-16 items-center ${
            reverse ? 'md:[&>*:first-child]:order-2' : ''
          }`}
        >
          <div className="max-w-xl">
            <div
              className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4"
              style={{ color: MUTED }}
            >
              {pillar.id === 'interviews' ? '01 · Interviews' : '02 · Workspace'}
            </div>
            <h2
              className="tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: 'clamp(1.875rem, 5vw, 3.5rem)',
                lineHeight: 1.05,
              }}
            >
              {pillar.title}
            </h2>
            <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
              {pillar.caption}
            </p>

            <div className="mt-6 sm:mt-8 grid grid-cols-3 gap-px rounded-lg overflow-hidden" style={{ backgroundColor: LINE }}>
              {pillar.stats.map((s) => (
                <div
                  key={s.label}
                  className="flex flex-col items-start p-3 sm:p-4"
                  style={{ backgroundColor: BG }}
                >
                  <span className="text-[9px] sm:text-[10px] uppercase tracking-wider" style={{ color: MUTED }}>
                    {s.label}
                  </span>
                  <span
                    className="text-xl sm:text-3xl font-light font-mono tabular-nums mt-1"
                    style={{ color: INK }}
                  >
                    {s.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="relative rounded-lg sm:rounded-xl overflow-hidden ring-1 shadow-2xl"
            style={{
              backgroundColor: '#0e0d0b',
              boxShadow: '0 30px 60px -20px rgba(31, 29, 26, 0.25)',
              borderColor: 'rgba(0,0,0,0.08)',
            }}
          >
            <div className="aspect-[16/10] w-full">
              <PillarVisual pillar={pillar} />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
