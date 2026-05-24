import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

// ---------------------------------------------------------------------------
// Vox-style stop-motion paper collage intro.
// Each enforcement headline assembles as layered cut-paper pieces:
//   halftoned cut shape (backdrop) → newsprint clipping → rubber stamp →
//   fine w/ hand-drawn marker circle → torn descriptor strip → tape + scraps.
// Everything jitters frame-by-frame (steps() timing) for the hand-photographed
// stop-motion wobble. Pieces slap down one at a time. Hard cuts + film flash.
//
// Layout: a fixed DESIGN_W×DESIGN_H canvas, uniformly transform-scaled to fit
// any viewport (one JS resize listener). Composition is identical everywhere,
// just smaller on phones — so all sizes are fixed px, not vw.
// ---------------------------------------------------------------------------

const DESIGN_W = 820
const DESIGN_H = 470

const BOARD = '#0c0a09'
const CREAM = '#f1e7d2'
const INK = '#1a1712'
const RED = '#cf3a2c'
const AMBER = '#d7ba7d'

const HEADLINE_FONT = '"Arial Narrow", "Helvetica Neue", Arial, sans-serif'
const SERIF = 'Georgia, "Times New Roman", serif'
const MONO = '"SF Mono", "Roboto Mono", ui-monospace, monospace'
const DISPLAY = 'var(--font-display)'

// grayscale fractal-noise tile — paper fiber grain (shared by paper + board)
const NOISE =
  "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='160'%20height='160'%3E%3Cfilter%20id='n'%3E%3CfeTurbulence%20type='fractalNoise'%20baseFrequency='0.8'%20numOctaves='2'%20stitchTiles='stitch'/%3E%3CfeColorMatrix%20type='saturate'%20values='0'/%3E%3C/filter%3E%3Crect%20width='160'%20height='160'%20filter='url(%23n)'/%3E%3C/svg%3E"

type Kind = 'box' | 'cup' | 'cart'

interface Frame {
  agency: string
  company: string
  stat: string
  desc: string
  dateline: string
  ticker: string
  kind: Kind
  cut: string
  dots: string
  scrap: string
}

const FRAMES: Frame[] = [
  {
    agency: 'OSHA', company: 'AMAZON', stat: '$5.9M', desc: 'warehouse safety violations',
    dateline: 'FEDERAL CITATION', ticker: 'AMZN', kind: 'box', cut: '#c9a86a', dots: '#6f5320', scrap: '#cf3a2c',
  },
  {
    agency: 'NLRB', company: 'STARBUCKS', stat: '200+ violations', desc: 'union-busting, nationwide',
    dateline: 'LABOR BOARD COMPLAINT', ticker: 'SBUX', kind: 'cup', cut: '#4f7d6e', dots: '#21443a', scrap: '#d7ba7d',
  },
  {
    agency: 'EEOC', company: 'WALMART', stat: '$60M', desc: 'pregnancy discrimination',
    dateline: 'EEOC SETTLEMENT', ticker: 'WMT', kind: 'cart', cut: '#5a6b9e', dots: '#2c365c', scrap: '#cf3a2c',
  },
]

export default function LandingIntro({ onDone }: { onDone: () => void }) {
  const [frameIndex, setFrameIndex] = useState(0) // 0-2 headlines, 3 tagline
  const [flashKey, setFlashKey] = useState(0)
  const [isExiting, setIsExiting] = useState(false)
  const [showSkip, setShowSkip] = useState(false)
  const [scale, setScale] = useState(1)
  const reduced = useRef(false)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  const handleDone = useCallback(() => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setIsExiting(true)
    timers.current.push(setTimeout(() => onDoneRef.current(), 500))
  }, [])

  const cut = useCallback((next: number) => {
    setFrameIndex(next)
    setFlashKey(k => k + 1)
  }, [])

  // fit the fixed canvas to the viewport
  useEffect(() => {
    const compute = () => {
      const s = Math.min((window.innerWidth * 0.94) / DESIGN_W, (window.innerHeight * 0.82) / DESIGN_H, 1.2)
      setScale(s)
    }
    compute()
    window.addEventListener('resize', compute)
    window.addEventListener('orientationchange', compute)
    return () => {
      window.removeEventListener('resize', compute)
      window.removeEventListener('orientationchange', compute)
    }
  }, [])

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  useEffect(() => {
    reduced.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced.current) {
      setFrameIndex(3)
      timers.current.push(setTimeout(handleDone, 1200))
      return () => timers.current.forEach(clearTimeout)
    }
    timers.current.push(
      setTimeout(() => cut(1), 1350),
      setTimeout(() => cut(2), 2700),
      setTimeout(() => cut(3), 4050),
      setTimeout(handleDone, 5800),
      setTimeout(() => setShowSkip(true), 700),
    )
    return () => timers.current.forEach(clearTimeout)
  }, [handleDone, cut])

  return (
    <motion.div
      className="fixed inset-0 z-[200] flex items-center justify-center overflow-hidden"
      style={{
        backgroundColor: BOARD,
        backgroundImage:
          'radial-gradient(ellipse 120% 100% at 50% 40%, rgba(42,35,24,0.55) 0%, rgba(0,0,0,0) 55%), ' +
          'repeating-linear-gradient(0deg, transparent, transparent 38px, rgba(255,255,255,0.014) 38px, rgba(255,255,255,0.014) 39px)',
      }}
      animate={{ opacity: isExiting ? 0 : 1 }}
      transition={{ duration: 0.5 }}
    >
      <IntroStyles />

      {/* board grain — cardboard/cork fiber */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ zIndex: 0, opacity: 0.5, mixBlendMode: 'overlay', backgroundImage: `url("${NOISE}")`, backgroundSize: '190px 190px' }}
      />

      {/* film-cut flash on each cut */}
      <AnimatePresence>
        <motion.div
          key={`flash-${flashKey}`}
          className="absolute inset-0 pointer-events-none"
          style={{ backgroundColor: 'rgba(255,250,240,0.16)', zIndex: 60 }}
          initial={{ opacity: 1 }}
          animate={{ opacity: 0 }}
          transition={{ duration: 0.1, ease: 'linear' }}
        />
      </AnimatePresence>

      {/* frame counter */}
      <AnimatePresence mode="wait">
        {frameIndex < 3 && (
          <motion.div
            key={`counter-${frameIndex}`}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0 }}
            className="absolute top-6 left-8 text-[10px] tracking-[0.3em] select-none"
            style={{ color: 'rgba(241,231,210,0.4)', fontFamily: MONO, zIndex: 50 }}
          >
            {String(frameIndex + 1).padStart(2, '0')} — 03
          </motion.div>
        )}
      </AnimatePresence>

      {/* skip */}
      <AnimatePresence>
        {showSkip && !isExiting && (
          <motion.button
            key="skip" type="button"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}
            onClick={handleDone}
            className="fixed top-5 right-7 px-2 py-1 text-[10px] tracking-[0.25em] uppercase hover:opacity-100 transition-opacity cursor-pointer"
            style={{ color: 'rgba(241,231,210,0.45)', fontFamily: MONO, zIndex: 201 }}
            aria-label="Skip intro"
          >
            skip ×
          </motion.button>
        )}
      </AnimatePresence>

      {/* fixed-size canvas, scaled to fit */}
      <div className="relative" style={{ width: DESIGN_W, height: DESIGN_H, transform: `scale(${scale})`, transformOrigin: 'center' }}>
        <AnimatePresence mode="wait">
          {frameIndex < 3 ? (
            <CollageFrame key={frameIndex} frame={FRAMES[frameIndex]} reduced={reduced.current} />
          ) : (
            <TaglineCollage key="tagline" reduced={reduced.current} />
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Piece — positions + spring "slap" entrance + continuous stop-motion jitter
// ---------------------------------------------------------------------------

interface PieceProps {
  x: number; y: number; z?: number; rot?: number; delay?: number
  jx?: number; jy?: number; jr?: number; dur?: number; jdelay?: number
  reduced?: boolean; children: ReactNode; style?: CSSProperties
}

function Piece({
  x, y, z = 3, rot = 0, delay = 0,
  jx = 1.6, jy = -1.4, jr = 0.8, dur = 480, jdelay = 0,
  reduced, children, style,
}: PieceProps) {
  const inner: CSSProperties = {
    transform: `rotate(${rot}deg)`,
    ['--rot' as string]: `${rot}deg`,
    ['--jx' as string]: `${jx}px`,
    ['--jy' as string]: `${jy}px`,
    ['--jr' as string]: `${jr}deg`,
    ...style,
  }
  if (!reduced) inner.animation = `smJitter ${dur}ms steps(3) ${jdelay}ms infinite alternate`

  return (
    <div style={{ position: 'absolute', left: `${x}%`, top: `${y}%`, zIndex: z }}>
      <motion.div
        initial={reduced ? false : { scale: 0.58, opacity: 0, rotate: rot * 1.7 }}
        animate={{ scale: 1, opacity: 1, rotate: 0 }}
        transition={reduced ? { duration: 0 } : { type: 'spring', stiffness: 560, damping: 15, delay }}
        style={{ transformOrigin: 'center' }}
      >
        <div style={inner}>{children}</div>
      </motion.div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CollageFrame — one enforcement headline, assembled from layered scraps
// ---------------------------------------------------------------------------

function CollageFrame({ frame, reduced }: { frame: Frame; reduced: boolean }) {
  return (
    <motion.div className="absolute inset-0" exit={{ opacity: 0 }} transition={{ duration: 0 }}>

      {/* backdrop cut shape (halftoned) */}
      <Piece x={4} y={6} z={1} rot={-6} delay={0} dur={540} jdelay={0} jx={1.8} jy={-1.5} jr={0.6} reduced={reduced}
        style={{ width: 300 }}>
        <CutShape kind={frame.kind} color={frame.cut} dots={frame.dots} uid={frame.ticker} />
      </Piece>

      {/* colored paper scrap behind */}
      <Piece x={70} y={62} z={2} rot={-15} delay={0.06} dur={430} jdelay={120} jx={-1.3} jy={1.6} jr={1.1} reduced={reduced}>
        <div className="paper" style={{ width: 80, height: 80, backgroundColor: frame.scrap, boxShadow: '3px 4px 0 rgba(0,0,0,0.45)' }} />
      </Piece>

      {/* headline newsprint clipping */}
      <Piece x={11} y={30} z={4} rot={-2.5} delay={0.12} dur={500} jdelay={60} jx={1.4} jy={-1.2} jr={0.6} reduced={reduced}>
        <Clipping>
          <div style={{ fontFamily: SERIF, fontSize: 12, letterSpacing: '0.18em', color: RED, fontWeight: 700, textTransform: 'uppercase', marginBottom: 4 }}>
            {frame.dateline}
          </div>
          <div style={{ fontFamily: HEADLINE_FONT, fontWeight: 800, color: INK, fontSize: 84, lineHeight: 0.84, letterSpacing: '-0.02em' }}>
            {frame.company}
          </div>
        </Clipping>
      </Piece>

      {/* tape over clipping corners */}
      <Tape x={10} y={27} rot={-32} reduced={reduced} />
      <Tape x={43} y={50} rot={16} reduced={reduced} w={66} />

      {/* rubber stamp — agency */}
      <Piece x={60} y={11} z={6} rot={9} delay={0.22} dur={460} jdelay={200} jx={-1.5} jy={1.2} jr={1.3} reduced={reduced}>
        <Stamp>{frame.agency}</Stamp>
      </Piece>

      {/* the fine, circled in red marker */}
      <Piece x={52} y={60} z={5} rot={-3} delay={0.32} dur={520} jdelay={300} jx={1.2} jy={1.5} jr={0.9} reduced={reduced}>
        <div style={{ position: 'relative', padding: '6px 26px' }}>
          <div style={{ fontFamily: HEADLINE_FONT, fontWeight: 800, color: CREAM, fontSize: 40, letterSpacing: '-0.01em' }}>
            {frame.stat}
          </div>
          <MarkerCircle reduced={reduced} />
        </div>
      </Piece>

      {/* torn descriptor strip */}
      <Piece x={9} y={77} z={4} rot={2} delay={0.28} dur={470} jdelay={150} jx={1.4} jy={-1.3} jr={0.7} reduced={reduced}>
        <div className="paper" style={{
          backgroundColor: CREAM, color: INK, fontFamily: SERIF, fontStyle: 'italic',
          fontSize: 16, padding: '6px 16px',
          filter: 'drop-shadow(3px 4px 1px rgba(0,0,0,0.45))',
          clipPath: 'polygon(0 0,100% 0,99% 100%,0 96%)',
        }}>
          {frame.desc}
        </div>
      </Piece>
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Tagline — the punchline collage: falling ticker + MATCHA stamp
// ---------------------------------------------------------------------------

function TaglineCollage({ reduced }: { reduced: boolean }) {
  return (
    <motion.div className="absolute inset-0" exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>

      {/* falling stock-ticker strip behind */}
      <div style={{
        position: 'absolute', left: '-10%', right: '-10%', top: '20%', zIndex: 1,
        backgroundColor: '#15110c', borderTop: '1px solid rgba(207,58,44,0.4)', borderBottom: '1px solid rgba(207,58,44,0.4)',
        padding: '8px 0', overflow: 'hidden', transform: 'rotate(-1.5deg)',
      }}>
        <div style={{
          whiteSpace: 'nowrap', fontFamily: MONO, fontSize: 16, color: RED,
          animation: reduced ? undefined : 'tickerSlide 9s linear infinite',
        }}>
          {Array(4).fill('▾ AMZN −12%   ▾ SBUX −8%   ▾ WMT −15%   ').join('')}
        </div>
      </div>

      {/* headline clipping: OFF THE TICKER */}
      <Piece x={9} y={32} z={4} rot={-2} delay={reduced ? 0 : 0.1} dur={520} jdelay={40} reduced={reduced}>
        <Clipping>
          <div style={{ fontFamily: SERIF, fontSize: 16, color: INK, fontStyle: 'italic', marginBottom: 2 }}>
            Matcha helps keep you
          </div>
          <div style={{ fontFamily: HEADLINE_FONT, fontWeight: 800, color: INK, fontSize: 88, lineHeight: 0.85, letterSpacing: '-0.02em' }}>
            OFF THE
          </div>
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <span style={{ fontFamily: HEADLINE_FONT, fontWeight: 800, color: INK, fontSize: 88, lineHeight: 0.85, letterSpacing: '-0.02em' }}>
              TICKER.
            </span>
            <UnderlineMark reduced={reduced} />
          </div>
        </Clipping>
      </Piece>

      <Tape x={8} y={29} rot={-28} reduced={reduced} />

      {/* MATCHA stamp slaps on */}
      <Piece x={58} y={68} z={6} rot={-7} delay={reduced ? 0 : 0.45} dur={500} jdelay={220} jx={-1.4} jy={1.3} jr={1.1} reduced={reduced}>
        <div style={{
          fontFamily: DISPLAY, fontWeight: 500, color: AMBER, fontSize: 44,
          letterSpacing: '0.04em', border: `3px solid ${AMBER}`, padding: '6px 20px', borderRadius: 2,
          textTransform: 'uppercase',
        }}>
          Matcha
        </div>
      </Piece>
    </motion.div>
  )
}

// ---------------------------------------------------------------------------
// Shared scrap primitives
// ---------------------------------------------------------------------------

function Clipping({ children }: { children: ReactNode }) {
  return (
    <div className="paper" style={{
      backgroundColor: CREAM,
      // halftone print dots + warm aged mottling
      backgroundImage:
        'radial-gradient(rgba(0,0,0,0.05) 1px, transparent 1.5px), ' +
        'radial-gradient(ellipse at 26% 16%, rgba(150,120,70,0.14), transparent 60%), ' +
        'radial-gradient(ellipse at 80% 84%, rgba(110,80,40,0.12), transparent 55%)',
      backgroundSize: '6px 6px, cover, cover',
      backgroundBlendMode: 'multiply, multiply, multiply',
      padding: '20px 30px',
      // filter (not box-shadow) — clip-path would clip a box-shadow away
      filter: 'drop-shadow(5px 7px 2px rgba(0,0,0,0.55))',
      // torn bottom edge
      clipPath: 'polygon(0 0,100% 0,100% 90%,95% 100%,87% 93%,78% 100%,69% 94%,60% 100%,51% 94%,42% 100%,33% 94%,24% 100%,15% 95%,7% 100%,0 95%)',
    }}>
      {children}
    </div>
  )
}

function Stamp({ children }: { children: ReactNode }) {
  return (
    <div style={{
      fontFamily: HEADLINE_FONT, fontWeight: 800, color: RED, fontSize: 28,
      letterSpacing: '0.14em', border: `3px solid ${RED}`, padding: '5px 14px',
      opacity: 0.95,
      boxShadow: 'inset 0 0 0 1px rgba(207,58,44,0.4), 0 0 0 1px rgba(207,58,44,0.15)',
      textShadow: '0.5px 0.5px 0 rgba(0,0,0,0.45)',
    }}>
      {children}
    </div>
  )
}

function Tape({ x, y, rot, w = 58, reduced }: { x: number; y: number; rot: number; w?: number; reduced?: boolean }) {
  return (
    <div style={{ position: 'absolute', left: `${x}%`, top: `${y}%`, zIndex: 7 }}>
      <motion.div
        initial={reduced ? false : { opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={reduced ? { duration: 0 } : { duration: 0.2, delay: 0.18 }}
        style={{
          width: w, height: 22, transform: `rotate(${rot}deg)`,
          background: 'linear-gradient(105deg, rgba(238,232,214,0.22), rgba(238,232,214,0.34) 50%, rgba(238,232,214,0.18))',
          borderLeft: '1px solid rgba(255,255,255,0.12)', borderRight: '1px solid rgba(255,255,255,0.12)',
          backdropFilter: 'blur(0.5px)',
        }}
      />
    </div>
  )
}

function MarkerCircle({ reduced }: { reduced: boolean }) {
  return (
    <svg viewBox="0 0 210 110" preserveAspectRatio="none"
      style={{ position: 'absolute', left: '-12%', top: '-22%', width: '124%', height: '150%', overflow: 'visible', pointerEvents: 'none' }}>
      <motion.path
        d="M30 62 C 18 24, 178 14, 188 52 C 196 88, 70 104, 24 74 C 12 60, 16 42, 34 38"
        fill="none" stroke={RED} strokeWidth={5} strokeLinecap="round"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={reduced ? { duration: 0 } : { duration: 0.5, delay: 0.28, ease: 'easeInOut' }}
      />
    </svg>
  )
}

function UnderlineMark({ reduced }: { reduced: boolean }) {
  return (
    <svg viewBox="0 0 220 24" preserveAspectRatio="none"
      style={{ position: 'absolute', left: 0, bottom: '-10px', width: '100%', height: 18, overflow: 'visible' }}>
      <motion.path
        d="M4 14 C 60 6, 150 20, 216 8"
        fill="none" stroke={RED} strokeWidth={5} strokeLinecap="round"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={reduced ? { duration: 0 } : { duration: 0.45, delay: 0.55, ease: 'easeOut' }}
      />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Cut shapes — halftoned generic silhouettes (box / cup / cart) + fiber grain
// ---------------------------------------------------------------------------

function CutShape({ kind, color, dots, uid }: { kind: Kind; color: string; dots: string; uid: string }) {
  const htId = `ht-${uid}`
  const clipId = `clip-${uid}`
  const pnId = `pn-${uid}`
  const shadow = { filter: 'drop-shadow(5px 7px 0 rgba(0,0,0,0.45))' }

  // halftone dots + paper-fiber noise, both clipped to the silhouette
  const texture = (
    <>
      <rect x="0" y="0" width="220" height="210" fill={`url(#${htId})`} clipPath={`url(#${clipId})`} opacity={0.5} />
      <rect x="0" y="0" width="220" height="210" filter={`url(#${pnId})`} clipPath={`url(#${clipId})`} opacity={0.16} style={{ mixBlendMode: 'multiply' }} />
    </>
  )
  const defs = (
    <defs>
      <pattern id={htId} width="9" height="9" patternUnits="userSpaceOnUse"><circle cx="4.5" cy="4.5" r="2" fill={dots} /></pattern>
      <filter id={pnId}><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" /><feColorMatrix type="saturate" values="0" /></filter>
      <clipPath id={clipId}>{CLIP_PATHS[kind]}</clipPath>
    </defs>
  )

  if (kind === 'box') {
    return (
      <svg viewBox="0 0 220 210" style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible', ...shadow }}>
        {defs}
        <path d="M55 90 L135 90 L135 172 L55 172 Z" fill={color} />
        <path d="M55 90 L82 62 L162 62 L135 90 Z" fill={color} opacity={0.82} />
        <path d="M135 90 L162 62 L162 144 L135 172 Z" fill={color} opacity={0.6} />
        {texture}
        <line x1="95" y1="90" x2="95" y2="172" stroke={dots} strokeWidth="7" opacity={0.45} />
        <line x1="55" y1="118" x2="135" y2="118" stroke={dots} strokeWidth="5" opacity={0.4} />
      </svg>
    )
  }

  if (kind === 'cup') {
    return (
      <svg viewBox="0 0 220 210" style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible', ...shadow }}>
        {defs}
        <path d="M70 80 L150 80 L140 176 L80 176 Z" fill={color} />
        <path d="M62 64 L158 64 L150 80 L70 80 Z" fill={color} opacity={0.9} />
        <path d="M73 64 Q110 40 147 64 Z" fill={color} opacity={0.95} />
        {texture}
        <path d="M78 116 L142 116 L140 140 L80 140 Z" fill={dots} opacity={0.5} />
        <path d="M96 34 q8 -10 0 -20" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" opacity={0.7} />
        <path d="M118 34 q8 -10 0 -20" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" opacity={0.7} />
      </svg>
    )
  }

  // cart
  return (
    <svg viewBox="0 0 220 210" style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible', ...shadow }}>
      {defs}
      <path d="M70 84 L172 84 L154 134 L86 134 Z" fill={color} />
      <circle cx="96" cy="166" r="13" fill={color} />
      <circle cx="150" cy="166" r="13" fill={color} />
      {texture}
      <path d="M70 84 L52 60 L40 60" fill="none" stroke={color} strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M88 134 L96 153 M150 134 L150 153" stroke={color} strokeWidth="6" strokeLinecap="round" />
      <path d="M92 108 L150 108 M112 84 L106 134 M134 84 L130 134" stroke={dots} strokeWidth="3.5" opacity={0.45} />
    </svg>
  )
}

const CLIP_PATHS: Record<Kind, ReactNode> = {
  box: (
    <>
      <path d="M55 90 L135 90 L135 172 L55 172 Z" />
      <path d="M55 90 L82 62 L162 62 L135 90 Z" />
      <path d="M135 90 L162 62 L162 144 L135 172 Z" />
    </>
  ),
  cup: (
    <>
      <path d="M70 80 L150 80 L140 176 L80 176 Z" />
      <path d="M62 64 L158 64 L150 80 L70 80 Z" />
      <path d="M73 64 Q110 40 147 64 Z" />
    </>
  ),
  cart: (
    <>
      <path d="M70 84 L172 84 L154 134 L86 134 Z" />
      <circle cx="96" cy="166" r="13" />
      <circle cx="150" cy="166" r="13" />
    </>
  ),
}

// ---------------------------------------------------------------------------
// keyframes — stop-motion jitter (steps) + ticker slide + paper grain overlay
// ---------------------------------------------------------------------------

function IntroStyles() {
  return (
    <style>{`
      @keyframes smJitter {
        0%   { transform: translate(0px, 0px) rotate(var(--rot, 0deg)); }
        100% { transform: translate(var(--jx, 1px), var(--jy, -1px)) rotate(calc(var(--rot, 0deg) + var(--jr, 0.6deg))); }
      }
      @keyframes tickerSlide {
        0%   { transform: translateX(0); }
        100% { transform: translateX(-25%); }
      }
      .paper { position: relative; }
      .paper::after {
        content: ''; position: absolute; inset: 0; pointer-events: none;
        background-image: url("${NOISE}");
        background-size: 130px 130px;
        mix-blend-mode: multiply;
        opacity: 0.5;
      }
      @media (prefers-reduced-motion: reduce) {
        @keyframes smJitter { 0%,100% { transform: rotate(var(--rot, 0deg)); } }
      }
    `}</style>
  )
}
