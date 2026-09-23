import { useEffect, useState, type ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Reveal } from '../motion'
import { tornClip } from '../torn'
import { STEPS, WRAP, display, mono, type StepId } from '../styles'
import { DISPLAY, GRAIN, HILITE, INK, INK_SOFT, PAPER, hexA } from '../theme'

export function PrimaryButton({
  onClick,
  children,
  tone = 'ink',
  torn,
}: {
  onClick: () => void
  children: ReactNode
  tone?: 'ink' | 'paper'
  /** Seed for a torn-paper edge instead of a pill. */
  torn?: number
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group sched-btn sched-btn-${tone} sched-focus inline-flex items-center gap-2 text-[15px] font-semibold ${torn === undefined ? 'h-12 rounded-full px-6' : 'sched-btn-torn h-14 px-7'}`}
      style={torn === undefined ? undefined : { clipPath: tornClip(torn, { tear: 10, cut: 1.5, steps: 16 }) }}
    >
      {children}
      <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
    </button>
  )
}

/** Section opener: the step's Sunday timestamp, then the headline. */
export function StepHead({
  step,
  title,
  children,
  dark,
}: {
  step: StepId
  title: ReactNode
  children?: ReactNode
  dark?: boolean
}) {
  const s = STEPS.find((x) => x.id === step)!
  return (
    <div>
      <Reveal>
        <div className="flex items-center gap-3" style={mono('11px', { color: dark ? PAPER : INK, fontWeight: 700 })}>
          <span className="rounded-sm px-1.5 py-0.5" style={{ backgroundColor: HILITE, color: INK }}>
            Sun {s.time} PM
          </span>
          <span style={{ color: dark ? hexA(PAPER, 0.6) : INK_SOFT, fontWeight: 400 }}>— {s.label}</span>
        </div>
      </Reveal>
      <Reveal delay={80}>
        <h2 className="mt-6" style={{ ...display, fontSize: 'clamp(2.7rem, 6.4vw, 5.6rem)' }}>
          {title}
        </h2>
      </Reveal>
      {children && (
        <Reveal delay={160}>
          <p className="mt-6 max-w-[34rem] text-[1.075rem] leading-[1.65]" style={{ color: dark ? hexA(PAPER, 0.72) : INK_SOFT }}>
            {children}
          </p>
        </Reveal>
      )}
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
      className="sticky top-0 z-50 transition-[background-color,box-shadow] duration-300"
      style={{
        backgroundColor: scrolled ? hexA(PAPER, 0.84) : 'transparent',
        backdropFilter: scrolled ? 'blur(14px) saturate(1.3)' : 'none',
        WebkitBackdropFilter: scrolled ? 'blur(14px) saturate(1.3)' : 'none',
        boxShadow: scrolled ? `0 1px 0 ${hexA(INK, 0.1)}` : 'none',
      }}
    >
      <div className={`${WRAP} flex h-16 items-center justify-between gap-6`}>
        <Link to="/" className="sched-focus flex items-baseline gap-2 rounded" aria-label="Matcha home">
          <span style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 25, letterSpacing: '0.01em' }}>MATCHA</span>
          <span style={mono('10.5px', { color: INK_SOFT })}>/ Scheduling</span>
        </Link>
        <nav aria-label="Page sections" className="hidden items-center gap-7 lg:flex">
          {STEPS.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="sched-link sched-focus rounded" style={mono('10.5px', { color: INK })}>
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
            className="sched-btn sched-btn-ink sched-focus hidden h-10 items-center rounded-full px-4 text-[14px] font-semibold sm:inline-flex"
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
  return (
    <nav
      aria-label="Sunday timeline"
      className="fixed left-4 top-1/2 z-40 hidden -translate-y-1/2 rounded-xl px-3.5 py-3 transition-opacity duration-500 min-[1560px]:block"
      style={{
        opacity: active ? 1 : 0,
        pointerEvents: active ? 'auto' : 'none',
        // Floats over full-bleed sections, including the dark one.
        backgroundColor: hexA(PAPER, 0.92),
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        boxShadow: `0 0 0 1px ${hexA(INK, 0.1)}, 0 12px 30px -18px ${hexA(INK, 0.5)}`,
      }}
    >
      <div style={mono('9.5px', { color: INK_SOFT, lineHeight: 1.5 })}>
        Sun
        <br />
        Oct 4
      </div>
      <ol className="relative mt-4 space-y-5 pl-4" style={{ borderLeft: `1px solid ${hexA(INK, 0.2)}` }}>
        {STEPS.map((s, i) => {
          const state = i === activeIndex ? 'now' : i < activeIndex ? 'past' : 'next'
          return (
            <li key={s.id} className="relative">
              <span
                aria-hidden
                className="absolute top-[3px] h-[9px] w-[9px] rounded-full transition-colors duration-300"
                style={{
                  left: -21,
                  backgroundColor: state === 'now' ? HILITE : state === 'past' ? INK : PAPER,
                  border: `1.5px solid ${state === 'next' ? hexA(INK, 0.3) : INK}`,
                }}
              />
              <a href={`#${s.id}`} className="sched-focus block rounded" aria-current={state === 'now' ? 'step' : undefined}>
                <span className="block transition-colors duration-300" style={mono('11px', { color: state === 'next' ? hexA(INK, 0.35) : INK, fontWeight: 700, letterSpacing: '0.04em' })}>
                  {s.time}
                </span>
                <span className="block transition-colors duration-300" style={mono('9px', { color: state === 'next' ? hexA(INK, 0.35) : INK_SOFT })}>
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
    <footer style={{ backgroundColor: INK, color: PAPER }}>
      <div className={`${WRAP} grid gap-10 py-14 md:grid-cols-12 md:items-end`}>
        <div className="md:col-span-7">
          <div style={{ fontFamily: DISPLAY, fontWeight: 800, fontSize: 'clamp(3rem, 8vw, 6rem)', lineHeight: 0.85 }}>MATCHA</div>
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
  return <div aria-hidden className="pointer-events-none fixed inset-0 z-[60]" style={{ backgroundImage: GRAIN, opacity: 0.16, mixBlendMode: 'multiply' }} />
}

export function LandingStyles() {
  return (
    <style>{`
      .sched-root { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
      .sched-root ::selection { background: ${HILITE}; color: ${INK}; }
      html:has(.sched-root) { scroll-behavior: smooth; scroll-padding-top: 80px; }

      /* a word slip pasted onto the page: drops in tilted, lands, settles */
      .cut-in { animation: schedCutIn .75s cubic-bezier(.2,1.25,.35,1) var(--d, 0ms) both; transform-origin: 50% 80%; }
      @keyframes schedCutIn {
        0% { opacity: 0; transform: translateY(-0.35em) rotate(var(--r0)) scale(1.12); }
        45% { opacity: 1; }
        100% { opacity: 1; transform: rotate(var(--r1)); }
      }
      .cut-fade { animation: schedFade .8s ease var(--d, 0ms) both; }
      @keyframes schedFade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }

      .sr { opacity: 0; transform: translateY(22px); transition: opacity .8s cubic-bezier(.2,.7,.2,1) var(--d, 0ms), transform .9s cubic-bezier(.2,.7,.2,1) var(--d, 0ms); }
      .sr.is-in { opacity: 1; transform: none; }

      .pen-mark path { stroke-dasharray: 1; stroke-dashoffset: 1; transition: stroke-dashoffset .9s cubic-bezier(.6,.05,.25,1) var(--d, 0ms); }
      .pen-mark.is-in path { stroke-dashoffset: 0; }
      .pen-draw { stroke-dasharray: 1; stroke-dashoffset: 1; transition: stroke-dashoffset 1.1s cubic-bezier(.6,.05,.25,1) var(--d, 0ms); }
      .is-in .pen-draw { stroke-dashoffset: 0; }

      .sched-hilite {
        background-image: linear-gradient(${HILITE}, ${HILITE});
        background-repeat: no-repeat; background-position: 0 68%; background-size: 100% 30%;
        padding: 0 .06em; margin: 0 -.06em;
        -webkit-box-decoration-break: clone; box-decoration-break: clone;
      }
      .sr .sched-hilite-scroll { background-size: 0% 30%; transition: background-size 1s cubic-bezier(.2,.7,.2,1) .45s; }
      .sr.is-in .sched-hilite-scroll { background-size: 100% 30%; }

      .sched-btn { transition: background-size .45s cubic-bezier(.6,.05,.25,1), color .25s, transform .25s; background-repeat: no-repeat; background-position: 0 0; background-size: 0% 100%; }
      .sched-btn:hover { background-size: 100% 100%; }
      .sched-btn:active { transform: translateY(1px); }
      .sched-btn-ink { background-image: linear-gradient(${HILITE}, ${HILITE}); background-color: ${INK}; color: ${PAPER}; }
      .sched-btn-ink:hover { color: ${INK}; }
      .sched-btn-paper { background-image: linear-gradient(${HILITE}, ${HILITE}); background-color: ${PAPER}; color: ${INK}; }

      .sched-link { background-image: linear-gradient(currentColor, currentColor); background-repeat: no-repeat; background-position: 0 100%; background-size: 0% 1.5px; transition: background-size .35s cubic-bezier(.6,.05,.25,1); padding-bottom: 2px; }
      .sched-link:hover { background-size: 100% 1.5px; }

      .sched-focus:focus-visible { outline: 2px solid ${INK}; outline-offset: 3px; }
      /* clip-path would cut an outside ring off, so torn buttons ring inside */
      .sched-btn-torn.sched-focus:focus-visible { outline: 2px solid ${HILITE}; outline-offset: -6px; }
      .sched-dark .sched-focus:focus-visible, footer .sched-focus:focus-visible { outline-color: ${PAPER}; }

      .grow-bar { transform-box: fill-box; transform-origin: 50% 100%; transform: scaleY(0); transition: transform .8s cubic-bezier(.2,.7,.2,1) var(--d, 0ms); }
      .is-in .grow-bar { transform: scaleY(1); }
      .grow-x { transform-origin: 0 50%; transform: scaleX(0); transition: transform 1.1s cubic-bezier(.6,.05,.25,1) var(--d, 0ms); }
      .is-in .grow-x { transform: scaleX(1); }
      .sun-rays { transform-box: fill-box; transform-origin: center; animation: schedSpin 48s linear infinite; }
      @keyframes schedSpin { to { transform: rotate(360deg); } }

      .stamp-in { opacity: 0; transform: rotate(-9deg) scale(1.8); }
      .is-in .stamp-in { animation: schedStamp .55s cubic-bezier(.3,1.5,.5,1) .5s forwards; }
      @keyframes schedStamp { 0% { opacity: 0; transform: rotate(-9deg) scale(1.8); } 55% { opacity: 1; } 100% { opacity: .94; transform: rotate(-9deg) scale(1); } }

      .toast-in { opacity: 0; transform: translateY(-12px) scale(.97); transition: opacity .6s ease .7s, transform .7s cubic-bezier(.2,.9,.3,1.2) .7s; }
      .is-in .toast-in { opacity: 1; transform: none; }

      @media (prefers-reduced-motion: reduce) {
        html:has(.sched-root) { scroll-behavior: auto; }
        .sr, .sr.is-in { opacity: 1; transform: none; transition: none; }
        .pen-mark path, .pen-draw { stroke-dashoffset: 0; transition: none; }
        .cut-in { animation: none; transform: rotate(var(--r1)); }
        .cut-fade { animation: none; }
        .sr .sched-hilite-scroll { background-size: 100% 30%; transition: none; }
        .grow-bar, .grow-x { transform: none; transition: none; }
        .sun-rays { animation: none; }
        .stamp-in, .is-in .stamp-in { opacity: .94; transform: rotate(-9deg); animation: none; }
        .toast-in { opacity: 1; transform: none; transition: none; }
        .sched-btn { transition: none; }
      }
    `}</style>
  )
}
