import { useEffect, useState, type ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Reveal } from '../motion'
import { STEPS, WRAP, display, mono, type StepId } from '../styles'
import { BOARD, GRAIN, INK, INK_SOFT, PAPER, SERIF, STAMP, hexA } from '../theme'

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

/** Section opener: the step's Sunday timestamp, then the headline. `split`
 *  puts the copy (and `aside`) in a right-hand column level with the
 *  headline's last line, like the hero, instead of stacking it underneath. */
export function StepHead({
  step,
  title,
  children,
  aside,
  dark,
  split,
}: {
  step: StepId
  title: ReactNode
  children?: ReactNode
  aside?: ReactNode
  dark?: boolean
  split?: boolean
}) {
  const s = STEPS.find((x) => x.id === step)!
  const head = (
    <>
      <Reveal>
        <div className="flex items-center gap-3" style={mono('11px', { color: dark ? PAPER : INK, fontWeight: 500 })}>
          <span>Sun {s.time} PM</span>
          <span aria-hidden className="h-px w-8" style={{ backgroundColor: dark ? hexA(PAPER, 0.3) : hexA(INK, 0.25) }} />
          <span style={{ color: dark ? hexA(PAPER, 0.6) : INK_SOFT }}>{s.label}</span>
        </div>
      </Reveal>
      <Reveal delay={80}>
        <h2 className="mt-6 max-w-[16ch]" style={{ ...display, fontSize: 'clamp(2.4rem, 5vw, 4.4rem)' }}>
          {title}
        </h2>
      </Reveal>
    </>
  )
  const copy = (children || aside) && (
    <Reveal delay={160}>
      {children && (
        <p className={`max-w-[34rem] text-[1.075rem] leading-[1.65] ${split ? '' : 'mt-6'}`} style={{ color: dark ? hexA(PAPER, 0.72) : INK_SOFT }}>
          {children}
        </p>
      )}
      {aside}
    </Reveal>
  )
  if (!split) {
    return (
      <div>
        {head}
        {copy}
      </div>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:items-end lg:gap-10">
      <div className="lg:col-span-7">{head}</div>
      <div className="lg:col-span-5 lg:pb-2">{copy}</div>
    </div>
  )
}

export function TopBar({ onContact }: { onContact: () => void }) {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8)
    on()
    window.addEventListener('scroll', on, { passive: true })
    return () => window.removeEventListener('scroll', on)
  }, [])
  return (
    <div
      className="sticky top-0 z-50 transition-[background-color,box-shadow,color] duration-300"
      style={{
        color: scrolled ? INK : PAPER,
        backgroundColor: scrolled ? hexA(PAPER, 0.84) : 'transparent',
        backdropFilter: scrolled ? 'blur(14px) saturate(1.3)' : 'none',
        WebkitBackdropFilter: scrolled ? 'blur(14px) saturate(1.3)' : 'none',
        boxShadow: scrolled ? `0 1px 0 ${hexA(INK, 0.1)}` : 'none',
      }}
    >
      <div className={`${WRAP} flex h-16 items-center justify-between gap-6`}>
        <Link to="/" className="sched-focus flex items-baseline gap-2 rounded" aria-label="Matcha home">
          <span style={{ ...display, fontWeight: 600, fontSize: 21, letterSpacing: '-0.03em' }}>Matcha</span>
          <span style={mono('10.5px', { color: scrolled ? INK_SOFT : hexA(PAPER, 0.6) })}>/ Scheduling</span>
        </Link>
        <nav aria-label="Page sections" className="hidden items-center gap-7 lg:flex">
          {STEPS.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="sched-link sched-focus rounded" style={mono('10.5px', { color: 'inherit' })}>
              {s.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-5">
          <Link to="/login" className="sched-link sched-focus rounded text-[14px] font-medium">
            Log in
          </Link>
          <button
            type="button"
            onClick={onContact}
            className={`sched-btn ${scrolled ? 'sched-btn-ink' : 'sched-btn-paper'} sched-focus hidden h-10 items-center rounded-full px-4 text-[14px] font-semibold sm:inline-flex`}
          >
            Book a walkthrough
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Margin clock for wide screens: which step of Sunday afternoon you're
 * reading. Only shown between the first and last step, and only where the
 * left gutter is wide enough to hold it without touching the content.
 */
export function TimelineRail() {
  const [active, setActive] = useState<StepId | null>(null)
  useEffect(() => {
    let raf = 0
    const measure = () => {
      raf = 0
      const line = window.innerHeight * 0.45
      let current: StepId | null = null
      for (const s of STEPS) {
        const el = document.getElementById(s.id)
        if (el && el.getBoundingClientRect().top <= line) current = s.id
      }
      const last = document.getElementById(STEPS[STEPS.length - 1].id)
      if (last && last.getBoundingClientRect().bottom < window.innerHeight * 0.3) current = null
      setActive(current)
    }
    const on = () => {
      if (!raf) raf = requestAnimationFrame(measure)
    }
    measure()
    window.addEventListener('scroll', on, { passive: true })
    window.addEventListener('resize', on)
    return () => {
      window.removeEventListener('scroll', on)
      window.removeEventListener('resize', on)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [])
  const activeIndex = STEPS.findIndex((s) => s.id === active)
  // No card: a bare mono list in the gutter. It floats over the dark Cost
  // section too, so its ink follows whichever section is under it.
  const dark = active === 'cost'
  const ink = dark ? PAPER : INK
  const soft = dark ? hexA(PAPER, 0.6) : INK_SOFT
  const green = dark ? BOARD.STAMP : STAMP
  return (
    <nav
      aria-label="Sunday timeline"
      className="fixed left-6 top-1/2 z-40 hidden -translate-y-1/2 transition-opacity duration-500 min-[1560px]:block"
      style={{ opacity: active ? 1 : 0, pointerEvents: active ? 'auto' : 'none' }}
    >
      <div className="transition-colors duration-300" style={mono('9.5px', { color: soft, lineHeight: 1.5 })}>
        Sun
        <br />
        Oct 4
      </div>
      <ol className="relative mt-4 space-y-5 pl-4 transition-colors duration-300" style={{ borderLeft: `1px solid ${hexA(ink, 0.2)}` }}>
        {STEPS.map((s, i) => {
          const state = i === activeIndex ? 'now' : i < activeIndex ? 'past' : 'next'
          return (
            <li key={s.id} className="relative">
              <span
                aria-hidden
                className="absolute top-[4px] h-[7px] w-[7px] rounded-full transition-colors duration-300"
                style={{
                  left: -20,
                  backgroundColor: state === 'now' ? green : state === 'past' ? ink : dark ? BOARD.PAPER : PAPER,
                  boxShadow: state === 'next' ? `inset 0 0 0 1px ${hexA(ink, 0.3)}` : undefined,
                }}
              />
              <a href={`#${s.id}`} className="sched-focus block rounded" aria-current={state === 'now' ? 'step' : undefined}>
                <span className="block transition-colors duration-300" style={mono('11px', { color: state === 'next' ? hexA(ink, 0.35) : ink, fontWeight: 500, letterSpacing: '0.04em' })}>
                  {s.time}
                </span>
                <span className="block transition-colors duration-300" style={mono('9px', { color: state === 'next' ? hexA(ink, 0.35) : soft })}>
                  {s.label}
                </span>
              </a>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export function Footer() {
  return (
    <footer style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
      <div className={`${WRAP} grid gap-10 py-14 md:grid-cols-12 md:items-end`}>
        <div className="md:col-span-7">
          <div style={{ ...display, fontSize: 'clamp(3rem, 8vw, 6rem)', lineHeight: 0.9 }}>Matcha</div>
          <p className="mt-4 max-w-md text-[0.95rem] leading-[1.6]" style={{ color: hexA(PAPER, 0.62) }}>
            Scheduling is part of{' '}
            <Link to="/matcha-ops" className="sched-link sched-focus rounded" style={{ color: PAPER }}>
              Matcha Ops
            </Link>{' '}
            — events, inventory, and team channels for every location.
          </p>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-7 gap-y-3 md:col-span-5 md:justify-end" style={mono('10.5px')}>
          <Link className="sched-link sched-focus rounded" to="/">hey-matcha.com</Link>
          <Link className="sched-link sched-focus rounded" to="/privacy">Privacy</Link>
          <Link className="sched-link sched-focus rounded" to="/terms">Terms</Link>
          <span style={{ opacity: 0.5 }}>© {new Date().getFullYear()} Matcha</span>
        </nav>
      </div>
    </footer>
  )
}

export function Grain() {
  return <div aria-hidden className="pointer-events-none fixed inset-0 z-[60]" style={{ backgroundImage: GRAIN, opacity: 0.08, mixBlendMode: 'multiply' }} />
}

export function LandingStyles() {
  return (
    <style>{`
      .sched-root { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
      .sched-root ::selection { background: ${hexA(STAMP, 0.25)}; color: ${INK}; }
      html:has(.sched-root) { scroll-behavior: smooth; scroll-padding-top: 80px; }

      .cut-fade { animation: schedFade .8s ease var(--d, 0ms) both; }
      @keyframes schedFade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }

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

      .sent-in { opacity: 0; transform: translateY(10px); transition: opacity .7s cubic-bezier(.2,.7,.2,1) .4s, transform .8s cubic-bezier(.2,.7,.2,1) .4s; }
      .is-in .sent-in { opacity: 1; transform: none; }
      .sent-dot { background-color: ${hexA(INK, 0.08)}; color: ${INK_SOFT}; transition: background-color .3s ease var(--d, 0ms), color .3s ease var(--d, 0ms); }
      .is-in .sent-dot { background-color: ${STAMP}; color: ${PAPER}; }

      /* check report: each result dot fills in its outcome colour as its row lands */
      .check-dot { background-color: ${hexA(INK, 0.15)}; transition: background-color .3s ease var(--d, 0ms); }
      .is-in .check-dot { background-color: var(--dot); }

      .toast-in { opacity: 0; transform: translateY(-12px) scale(.97); transition: opacity .6s ease .7s, transform .7s cubic-bezier(.2,.9,.3,1.2) .7s; }
      .is-in .toast-in { opacity: 1; transform: none; }

      @media (prefers-reduced-motion: reduce) {
        html:has(.sched-root) { scroll-behavior: auto; }
        .sr, .sr.is-in { opacity: 1; transform: none; transition: none; }
        .pen-draw { stroke-dashoffset: 0; transition: none; }
        .cut-fade { animation: none; }
        .grow-bar, .grow-x { transform: none; transition: none; }
        .sent-in, .is-in .sent-in { opacity: 1; transform: none; transition: none; }
        .sent-dot { transition: none; }
        .check-dot { transition: none; }
        .toast-in { opacity: 1; transform: none; transition: none; }
        .sched-btn { transition: none; }
      }
    `}</style>
  )
}
