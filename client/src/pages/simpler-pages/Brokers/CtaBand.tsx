import { ASH, BONE, DISPLAY, LEAF, NOIR } from '../../home/theme'
import { CONTAINER, SECTION_Y_LG } from '../../home/layout'
import { Reveal } from '../../home/PageChrome'

// Sales-led, no self-serve path here — broker relationships are set up by
// hand, unlike Compliance/Lite's Stripe checkout. One CTA, re-tokened.
export function CtaBand({ onBookClick }: { onBookClick: () => void }) {
  return (
    <section className={SECTION_Y_LG}>
      <Reveal className={`${CONTAINER} text-center`}>
        <h2
          className="tracking-[-0.02em]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, color: BONE, fontSize: 'clamp(2.5rem, 7vw, 5.5rem)', lineHeight: 1 }}
        >
          Put your book on Matcha.
        </h2>
        <p className="mt-6 mx-auto max-w-lg text-lg" style={{ color: ASH, lineHeight: 1.6 }}>
          Tell us how many accounts you manage and how you want to deploy.
          We'll walk you through the rest.
        </p>
        <div className="mt-10 flex justify-center">
          <button
            type="button"
            onClick={onBookClick}
            className="inline-flex items-center px-8 rounded-full text-base font-medium cursor-pointer transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_18px_44px_-16px_rgba(163,197,125,0.45)] active:translate-y-0 active:shadow-none"
            style={{ backgroundColor: LEAF, color: NOIR, height: 56 }}
          >
            Book a Walkthrough
          </button>
        </div>
      </Reveal>
    </section>
  )
}
