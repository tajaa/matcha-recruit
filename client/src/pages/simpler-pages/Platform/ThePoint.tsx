import { ASH, BONE } from '../../home/theme'
import { CONTAINER, EYEBROW, SECTION_Y } from '../../home/layout'
import { Reveal } from '../../home/PageChrome'

// The point — a hard editorial cut before the close. Copy kept verbatim.
export function ThePoint() {
  return (
    <section className={SECTION_Y}>
      <Reveal className={CONTAINER}>
        <span className={EYEBROW} style={{ color: ASH }}>
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{ fontFamily: "var(--font-lite)", fontWeight: 300, color: BONE, lineHeight: 1.1, fontSize: 'clamp(2rem, 5vw, 4.25rem)' }}
        >
          We don't hand you another dashboard. We run the whole risk and
          people function — safety, compliance, and the{' '}
          <span style={{ fontStyle: 'italic' }}>human</span> calls
          — on one brain.
        </p>
      </Reveal>
    </section>
  )
}
