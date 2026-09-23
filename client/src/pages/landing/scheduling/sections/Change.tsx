import { PenMark, Reveal } from '../motion'
import Stage from '../Stage'
import { WRAP, mono } from '../styles'
import { INK, INK_SOFT, hexA } from '../theme'
import { CHAT_DURATION, CHAT_SIZES, CHAT_STILL } from '../timeline'
import { StepHead } from './Chrome'

const loadChat = () => import('../ChatComposition')

// Phrasings the schedule chat actually parses: reassign, swap, add, retime.
const SAYINGS = ['give Dev’s Monday to Sam', 'swap the opener and the closer Friday', 'add an opener Tuesday', 'move Sam’s close to 4pm']

export function Change() {
  return (
    <section id="change" className={`${WRAP} grid grid-cols-1 gap-14 py-24 sm:py-36 lg:grid-cols-12 lg:items-center lg:gap-12`}>
      <div className="lg:col-span-5">
        <StepHead
          step="change"
          title={
            <>
              Change it in a <PenMark kind="underline">sentence.</PenMark>
            </>
          }
        >
          Type it the way you’d tell a shift lead. Huume drafts the edit, shows who moves and what it does to their hours, and waits. Nothing
          changes until you confirm.
        </StepHead>
        <Reveal delay={240}>
          <ul className="mt-10 flex flex-wrap gap-2">
            {SAYINGS.map((s) => (
              <li key={s} className="rounded-full px-3 py-1.5" style={{ ...mono('10.5px', { color: INK, letterSpacing: '0.04em', textTransform: 'none' }), border: `1px solid ${hexA(INK, 0.22)}` }}>
                <span style={{ color: INK_SOFT }}>@huume</span> {s}
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
      <Reveal delay={120} className="lg:col-span-7">
        <Stage
          load={loadChat}
          sizes={CHAT_SIZES}
          durationInFrames={CHAT_DURATION}
          stillFrame={CHAT_STILL}
          label="Animated example: a manager asks Huume to give Dev's Tuesday open to Jonah; Huume proposes the change with Jonah going from 32 to 40 hours and no overtime, the manager confirms, and the Tuesday schedule updates."
          mediaClassName="rounded-[3px]"
          mediaStyle={{ border: `1.5px solid ${INK}` }}
          caption={<span style={mono('10.5px', { color: INK_SOFT })}>Illustrative · Huume proposes, you confirm</span>}
        />
      </Reveal>
    </section>
  )
}
