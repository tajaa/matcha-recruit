import { Reveal } from '../motion'
import Stage from '../Stage'
import { WRAP, mono } from '../styles'
import { INK, INK_SOFT, hexA } from '../theme'
import { CHAT_DURATION, CHAT_SIZES, CHAT_STILL } from '../timeline'
import { Accent, StepHead } from './Chrome'

const loadChat = () => import('../ChatComposition')

// Phrasings the schedule chat actually parses: reassign, swap, add, retime.
const SAYINGS = ['give Dev’s Monday to Sam', 'swap the opener and the closer Friday', 'add an opener Tuesday', 'move Sam’s close to 4pm']

const RULE = hexA(INK, 0.1)

function Sayings() {
  return (
    <ul className="mt-8" style={{ borderTop: `1px solid ${RULE}` }}>
      {SAYINGS.map((s) => (
        <li key={s} className="py-2.5" style={{ ...mono('10.5px', { color: INK, letterSpacing: '0.04em', textTransform: 'none' }), borderBottom: `1px solid ${RULE}` }}>
          <span style={{ color: INK_SOFT }}>@huume</span> {s}
        </li>
      ))}
    </ul>
  )
}

export function Change() {
  return (
    <section id="change" className={`${WRAP} py-28 sm:py-44`}>
      <StepHead
        split
        step="change"
        title={
          <>
            Change it in a <Accent>sentence.</Accent>
          </>
        }
        aside={<Sayings />}
      >
        Type it the way you’d tell a shift lead. Huume drafts the edit, shows who moves and what it does to their hours, and waits. Nothing changes
        until you confirm.
      </StepHead>
      <Reveal delay={120} className="mt-16 pt-4" style={{ borderTop: `1px solid ${RULE}` }}>
        <Stage
          load={loadChat}
          sizes={CHAT_SIZES}
          durationInFrames={CHAT_DURATION}
          stillFrame={CHAT_STILL}
          label="Animated example: a manager asks Huume to give Dev's Tuesday open to Jonah; Huume proposes the change with Jonah going from 32 to 40 hours and no overtime, the manager confirms, and the Tuesday schedule updates."
          // pulled out by the composition's own padding (34/1320 wide, 36.4/720
          // narrow) so the chat window lines up with the headline, as in the hero
          mediaClassName="-mx-[5.62%] sm:-mx-[2.72%]"
          caption={<span style={mono('10.5px', { color: INK_SOFT })}>Illustrative · Huume proposes, you confirm</span>}
        />
      </Reveal>
    </section>
  )
}
