import type { CSSProperties, ReactNode } from 'react'
import { slipTilt, tornClip } from '../torn'
import { GRAIN, HILITE, INK, PAPER, hexA } from '../theme'

export type SlipTone = 'paper' | 'hilite' | 'ink'

const TONES: Record<SlipTone, { bg: string; fg: string; rim?: string }> = {
  paper: { bg: '#FBFCF9', fg: INK },
  hilite: { bg: HILITE, fg: INK, rim: '#FBFCF9' },
  ink: { bg: INK, fg: PAPER },
}

/**
 * One word cut out of paper and pasted onto the page. The outer span carries
 * the paste-in animation and a drop shadow (a filter, so it follows the torn
 * clip); the inner span is the torn paper itself. Text stays real text.
 */
export function Slip({ children, seed, tone = 'paper', delay = 0, style }: { children: ReactNode; seed: number; tone?: SlipTone; delay?: number; style?: CSSProperties }) {
  const t = TONES[tone]
  const r1 = slipTilt(seed)
  const r0 = slipTilt(seed + 3, 9)
  const paper: CSSProperties = {
    display: 'inline-block',
    backgroundColor: t.bg,
    // a light wash of paper tooth, not a grey cast
    backgroundImage: `linear-gradient(${hexA(t.bg, 0.9)}, ${hexA(t.bg, 0.9)}), ${GRAIN}`,
    color: t.fg,
    clipPath: tornClip(seed),
    padding: '0.1em 0.12em 0.04em',
  }
  return (
    <span
      className="cut-in"
      style={{
        display: 'inline-block',
        filter: `drop-shadow(0 0.06em 0.05em ${hexA(INK, 0.22)}) drop-shadow(0 0.01em 0 ${hexA(INK, 0.12)})`,
        ['--r0' as string]: `${r0}deg`,
        ['--r1' as string]: `${r1}deg`,
        ['--d' as string]: `${delay}ms`,
        ...style,
      }}
    >
      {t.rim ? (
        <span style={{ display: 'inline-block', backgroundColor: t.rim, clipPath: tornClip(seed + 97, { tear: 9 }), padding: '0.05em 0.05em' }}>
          <span style={paper}>{children}</span>
        </span>
      ) : (
        <span style={paper}>{children}</span>
      )}
    </span>
  )
}
