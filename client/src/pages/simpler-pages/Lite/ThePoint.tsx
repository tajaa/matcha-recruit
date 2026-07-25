import { ASH, BONE, DISPLAY, LEAF, LINE_D } from '../../home/theme'
import { CONTAINER, EYEBROW, SECTION_Y } from '../../home/layout'
import { Reveal } from '../../home/PageChrome'

// The point — a hard editorial cut before the close. Copy kept verbatim.
export function ThePoint() {
  return (
    <section className={`${SECTION_Y} border-t`} style={{ borderColor: LINE_D }}>
      <Reveal className={CONTAINER}>
        <span className={EYEBROW} style={{ color: ASH }}>
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, color: BONE, lineHeight: 1.1, fontSize: 'clamp(2rem, 5vw, 4.25rem)' }}
        >
          Compliance shouldn't live in a binder nobody opens. Matcha Lite
          makes it something your team{' '}
          <span style={{ color: LEAF, fontStyle: 'italic' }}>uses</span>, every
          day, without thinking about it.
        </p>
      </Reveal>
    </section>
  )
}
