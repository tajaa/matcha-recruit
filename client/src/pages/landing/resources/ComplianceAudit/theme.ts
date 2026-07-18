const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

export type Step = 'intro' | 'context' | 'questions' | 'results'

export function mkT(embedded?: boolean) {
  return embedded ? {
    ink: '#e4e4e7', bg: 'transparent', muted: '#71717a',
    line: '#3f3f46', display: 'inherit',
    cardBg: '#18181b',
    progressBg: '#27272a',
    btnPrimary: { backgroundColor: '#15803d', color: '#fff' } as React.CSSProperties,
    btnSecondary: { border: '1px solid #3f3f46', color: '#e4e4e7' } as React.CSSProperties,
    selectedBtn: { backgroundColor: '#15803d', color: '#fff', border: '1px solid #15803d' } as React.CSSProperties,
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    cardBg: 'rgba(15,15,15,0.03)',
    progressBg: 'rgba(15,15,15,0.08)',
    btnPrimary: { backgroundColor: INK, color: BG } as React.CSSProperties,
    btnSecondary: { border: `1px solid ${LINE}`, color: INK } as React.CSSProperties,
    selectedBtn: { backgroundColor: INK, color: BG, border: `1px solid ${INK}` } as React.CSSProperties,
  }
}

export type Theme = ReturnType<typeof mkT>
