import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { AMBER, ASH, BONE, DISPLAY, LEAF, LINE_D } from '../../home/theme'
import { CONTAINER } from '../../home/layout'
import { BookInstrument } from './BookInstrument'

/**
 * Left-aligned editorial, matching Compliance/Platform/Lite's recipe exactly:
 * same CONTAINER, same top-padding math (nav is 64px), headline static/opaque
 * at first paint. Replaces the old skeuomorphic "Book Risk Console" hero —
 * that console lived in its own charcoal material system and needed a
 * non-wrapping ~700px module rack, so it never fit this column and read as a
 * different product from the rest of the (already noir) page below it.
 */
export function Hero({ onBookClick }: { onBookClick: () => void }) {
  return (
    <section className="home-hero relative w-full flex flex-col">
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute"
          style={{
            left: '-12%',
            top: '-18%',
            width: '62%',
            height: '72%',
            background:
              'radial-gradient(50% 50% at 50% 50%, rgba(245,181,69,0.055) 0%, transparent 70%)',
          }}
        />
        <div
          className="absolute"
          style={{
            right: '-14%',
            bottom: '-22%',
            width: '58%',
            height: '68%',
            background:
              'radial-gradient(50% 50% at 50% 50%, rgba(163,197,125,0.05) 0%, transparent 70%)',
          }}
        />
      </div>

      <div
        className={`home-hero-body relative ${CONTAINER} flex-1 flex flex-col justify-center pt-[88px] sm:pt-[96px] pb-10`}
      >
        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-10 lg:gap-14 items-center">
          <div>
            <div
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6"
              style={{ border: `1px solid ${LINE_D}`, color: ASH }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: LEAF }} />
              <span className="text-[10px] sm:text-[11px] font-mk-mono uppercase tracking-[0.18em]">
                For P&amp;C brokers
              </span>
            </div>

            <h1
              className="tracking-[-0.02em] text-[clamp(2.1rem,4.4vw,3.6rem)]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.08, color: BONE }}
            >
              The <span style={{ color: LEAF, fontStyle: 'italic' }}>intelligence</span> layer for
              your whole <span style={{ color: AMBER, fontStyle: 'italic' }}>book</span>.
            </h1>

            <p
              className="home-fade-fast mt-6 max-w-lg text-[1.05rem] sm:text-[1.2rem] tracking-[-0.011em]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.45, color: ASH }}
            >
              Your clients run live safety and compliance intake. You get the book back as one
              ranked view — which accounts are deteriorating, who needs the loss-control call, and
              a submission packet already built when renewal comes.
            </p>

            <div className="home-fade-fast mt-9 flex flex-wrap items-center gap-3 sm:gap-5" style={{ animationDelay: '80ms' }}>
              <button
                type="button"
                onClick={onBookClick}
                className="inline-flex items-center justify-center gap-2 px-6 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
                style={{ backgroundColor: LEAF, color: '#14210B' }}
              >
                Book a walkthrough
                <ArrowRight className="w-4 h-4" />
              </button>
              <Link
                to="/matcha-platform"
                className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
                style={{ color: BONE }}
              >
                See the platform →
              </Link>
            </div>
          </div>

          <div className="home-fade-fast" style={{ animationDelay: '160ms' }}>
            <BookInstrument />
          </div>
        </div>
      </div>

      <div aria-hidden style={{ height: 1, backgroundColor: LINE_D }} />
    </section>
  )
}
