import { Link } from 'react-router-dom'
import { ASH, BONE, LEAF, NOIR } from '../../home/theme'
import { CONTAINER, SECTION_Y_LG } from '../../home/layout'
import { Reveal } from '../../home/PageChrome'

export function CtaBand({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className={SECTION_Y_LG}>
      <Reveal className={`${CONTAINER} text-center`}>
        <h2
          className="tracking-[-0.02em]"
          style={{ fontFamily: "var(--font-lite)", fontWeight: 300, color: BONE, fontSize: 'clamp(2.5rem, 7vw, 5.5rem)', lineHeight: 1 }}
        >
          Give your team the daily layer.
        </h2>
        <p className="mt-6 mx-auto max-w-lg text-lg" style={{ color: ASH, lineHeight: 1.6 }}>
          Tell us your headcount and where you operate. We'll walk you through
          the rest.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-5">
          <Link
            to="/lite/signup"
            className="inline-flex items-center gap-2 px-8 rounded-full text-base font-medium transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_18px_44px_-16px_rgba(163,197,125,0.45)] active:translate-y-0 active:shadow-none"
            style={{ backgroundColor: LEAF, color: NOIR, height: 56 }}
          >
            Start now
          </Link>
          <button
            type="button"
            onClick={onContactClick}
            className="inline-flex items-center text-base transition-opacity hover:opacity-60 cursor-pointer"
            style={{ color: BONE }}
          >
            Talk to sales
          </button>
        </div>
      </Reveal>
    </section>
  )
}
