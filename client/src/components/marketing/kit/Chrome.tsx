import type { ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { mono } from './styles'
import { AMBER, BOARD, GRAIN, INK, INK_SOFT, PAPER, SERIF, STAMP, hexA } from './theme'

/* Shared marketing kit: the pieces the /matcha-scheduling landing introduced
   and the home page now uses too. Page-specific chrome stays with its page. */

export function PrimaryButton({ onClick, children, tone = 'ink' }: { onClick: () => void; children: ReactNode; tone?: 'ink' | 'paper' }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group sched-btn sched-btn-${tone} sched-focus inline-flex h-12 items-center gap-2 rounded-full px-6 text-[15px] font-medium`}
    >
      {children}
      <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
    </button>
  )
}

/** The one italic serif word in a headline, in matcha green — lifted on dark. */
export function Accent({ children, dark }: { children: ReactNode; dark?: boolean }) {
  return (
    <em style={{ fontFamily: SERIF, fontStyle: 'italic', fontWeight: 400, letterSpacing: '-0.01em', color: dark ? BOARD.STAMP : STAMP }}>{children}</em>
  )
}

/** Two soft glows — matcha and amber — for frosted glass to catch. Positions
 *  are kept inside the box so they fade out before its edge. */
export function Glows({ green, amber, className = '' }: { green: string; amber: string; className?: string }) {
  return (
    <div
      aria-hidden
      className={`pointer-events-none absolute inset-0 ${className}`}
      style={{
        background: [
          `radial-gradient(30% 40% at ${green}, ${hexA(STAMP, 0.16)}, transparent 70%)`,
          `radial-gradient(28% 36% at ${amber}, ${hexA(AMBER, 0.14)}, transparent 70%)`,
        ].join(', '),
      }}
    />
  )
}

/** A grid cell's label: "01 —— Sales". Shared by every hairline grid. */
export function CellLabel({ n, children, dark }: { n: string; children: ReactNode; dark?: boolean }) {
  const ink = dark ? PAPER : INK
  return (
    <div className="flex items-center gap-3" style={mono('10px', { color: dark ? hexA(PAPER, 0.55) : INK_SOFT })}>
      <span style={{ color: ink }}>{n}</span>
      <span aria-hidden className="h-px w-6" style={{ backgroundColor: hexA(ink, 0.25) }} />
      {children}
    </div>
  )
}

export function Grain() {
  return <div aria-hidden className="pointer-events-none fixed inset-0 z-[60]" style={{ backgroundImage: GRAIN, opacity: 0.08, mixBlendMode: 'multiply' }} />
}

/** Page-agnostic CSS for the kit: reveal, buttons, links, focus, fades. Mount
 *  once inside a `.sched-root`. */
export function KitStyles() {
  return (
    <style>{`
      .sched-root { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
      .sched-root ::selection { background: ${hexA(STAMP, 0.25)}; color: ${INK}; }
      html:has(.sched-root) { scroll-behavior: smooth; scroll-padding-top: 80px; }
      .cut-fade { animation: schedFade .8s ease var(--d, 0ms) both; }
      @keyframes schedFade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
      .cut-fade-fast { animation-duration: .42s; }
      .sr { opacity: 0; transform: translateY(22px); transition: opacity .8s cubic-bezier(.2,.7,.2,1) var(--d, 0ms), transform .9s cubic-bezier(.2,.7,.2,1) var(--d, 0ms); }
      .sr.is-in { opacity: 1; transform: none; }
      .pen-draw { stroke-dasharray: 1; stroke-dashoffset: 1; transition: stroke-dashoffset 1.1s cubic-bezier(.6,.05,.25,1) var(--d, 0ms); }
      .is-in .pen-draw { stroke-dashoffset: 0; }
      .sched-btn { transition: background-size .45s cubic-bezier(.6,.05,.25,1), color .25s, transform .25s; background-repeat: no-repeat; background-position: 0 0; background-size: 0% 100%; }
      .sched-btn:hover { background-size: 100% 100%; }
      .sched-btn:active { transform: translateY(1px); }
      /* hover wipes in matcha green, left to right */
      .sched-btn-ink { background-image: linear-gradient(${STAMP}, ${STAMP}); background-color: ${INK}; color: ${PAPER}; }
      .sched-btn-paper { background-image: linear-gradient(${BOARD.STAMP}, ${BOARD.STAMP}); background-color: ${PAPER}; color: ${INK}; }
      .sched-link { background-image: linear-gradient(currentColor, currentColor); background-repeat: no-repeat; background-position: 0 100%; background-size: 0% 1.5px; transition: background-size .35s cubic-bezier(.6,.05,.25,1); padding-bottom: 2px; }
      .sched-link:hover { background-size: 100% 1.5px; }
      .sched-focus:focus-visible { outline: 2px solid ${INK}; outline-offset: 3px; }
      .sched-dark .sched-focus:focus-visible, footer .sched-focus:focus-visible { outline-color: ${PAPER}; }
      .grow-bar { transform-box: fill-box; transform-origin: 50% 100%; transform: scaleY(0); transition: transform .8s cubic-bezier(.2,.7,.2,1) var(--d, 0ms); }
      .is-in .grow-bar { transform: scaleY(1); }
      .grow-x { transform-origin: 0 50%; transform: scaleX(0); transition: transform 1.1s cubic-bezier(.6,.05,.25,1) var(--d, 0ms); }
      .is-in .grow-x { transform: scaleX(1); }
      .sched-root a, .sched-root button, .sched-root input, .sched-root summary { -webkit-tap-highlight-color: transparent; }

      @media (prefers-reduced-motion: reduce) {
        html:has(.sched-root) { scroll-behavior: auto; }
        .sr, .sr.is-in { opacity: 1; transform: none; transition: none; }
        .pen-draw { stroke-dashoffset: 0; transition: none; }
        .cut-fade { animation: none; }
        .grow-bar, .grow-x { transform: none; transition: none; }
        .sched-btn { transition: none; }
      }
    `}</style>
  )
}
