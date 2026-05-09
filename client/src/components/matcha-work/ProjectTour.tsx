import { useEffect, useState, useCallback } from 'react'
import { X, ChevronRight, ChevronLeft } from 'lucide-react'

export interface TourStep {
  /** CSS selector (typically `[data-tour="<id>"]`) for the spotlight target. */
  target: string
  title: string
  description: string
  /** Preferred tooltip placement relative to the target. */
  side?: 'top' | 'bottom' | 'left' | 'right'
}

interface Props {
  steps: TourStep[]
  onComplete: (dismissed: boolean) => void
}

/** Padding (px) added around the target rect when drawing the spotlight cutout. */
const SPOTLIGHT_PADDING = 6
const TOOLTIP_GAP = 12
const TOOLTIP_WIDTH = 320

interface Rect { left: number; top: number; width: number; height: number }

/**
 * Inline tour with a spotlight on real DOM targets. Each step looks up its
 * target via querySelector, draws an SVG-mask cutout around it, and renders
 * a tooltip nearby with title + description + Back/Next/Skip buttons.
 *
 * If a target isn't on screen (e.g. the user is on a sub-tab where it
 * doesn't render), the step auto-skips forward. Skipping or finishing
 * fires `onComplete(dismissed=true)` — callers decide whether to set the
 * "don't show again" flag or just hide for this session.
 *
 * Resilient to layout changes: rect re-measured on resize + every 250ms
 * during the tour (cheap, only while open).
 */
export default function ProjectTour({ steps, onComplete }: Props) {
  const [stepIdx, setStepIdx] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const step = steps[stepIdx]

  // Measure the current step's target. If the element isn't found, treat as
  // null and the render path advances the step or hides the spotlight.
  const measure = useCallback(() => {
    if (!step) return
    const el = document.querySelector(step.target) as HTMLElement | null
    if (!el) {
      setRect(null)
      return
    }
    const r = el.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) {
      setRect(null)
      return
    }
    setRect({ left: r.left, top: r.top, width: r.width, height: r.height })
  }, [step])

  // Re-measure on step change, on resize, and on a slow poll so the
  // spotlight follows when the user scrolls or the layout shifts.
  useEffect(() => {
    measure()
    const onResize = () => measure()
    window.addEventListener('resize', onResize)
    window.addEventListener('scroll', onResize, true)
    const interval = setInterval(measure, 250)
    return () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onResize, true)
      clearInterval(interval)
    }
  }, [measure])

  // If a step's target isn't on screen for several measurement cycles,
  // auto-advance so the tour doesn't stall. Without this, hiding a feature
  // (e.g. recruiting layout has no Sections panel) would freeze the tour.
  useEffect(() => {
    if (rect) return
    const t = setTimeout(() => {
      if (stepIdx < steps.length - 1) {
        setStepIdx((i) => i + 1)
      }
    }, 800)
    return () => clearTimeout(t)
  }, [rect, stepIdx, steps.length])

  if (!step) {
    onComplete(false)
    return null
  }

  function next() {
    if (stepIdx >= steps.length - 1) {
      onComplete(false)
    } else {
      setStepIdx((i) => i + 1)
    }
  }

  function back() {
    if (stepIdx > 0) setStepIdx((i) => i - 1)
  }

  function skip() {
    onComplete(true)
  }

  // Compute tooltip placement. Default to "right" of the target; flip when
  // there's no room. Falls back to centered overlay if no rect.
  const placement = computeTooltipPosition(rect, step.side ?? 'right')

  return (
    <>
      {/* Spotlight backdrop — full-screen dim with a rounded-rect cutout
          around the target. SVG mask handles the hole cleanly. */}
      <svg
        style={{
          position: 'fixed',
          inset: 0,
          width: '100vw',
          height: '100vh',
          zIndex: 9000,
          pointerEvents: 'none',
        }}
      >
        <defs>
          <mask id="mw-tour-spotlight">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            {rect && (
              <rect
                x={rect.left - SPOTLIGHT_PADDING}
                y={rect.top - SPOTLIGHT_PADDING}
                width={rect.width + SPOTLIGHT_PADDING * 2}
                height={rect.height + SPOTLIGHT_PADDING * 2}
                rx="6"
                ry="6"
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="rgba(0,0,0,0.65)"
          mask="url(#mw-tour-spotlight)"
        />
        {rect && (
          <rect
            x={rect.left - SPOTLIGHT_PADDING}
            y={rect.top - SPOTLIGHT_PADDING}
            width={rect.width + SPOTLIGHT_PADDING * 2}
            height={rect.height + SPOTLIGHT_PADDING * 2}
            rx="6"
            ry="6"
            fill="none"
            stroke="#ce9178"
            strokeWidth="2"
          />
        )}
      </svg>

      {/* Tooltip card */}
      <div
        style={{
          position: 'fixed',
          left: placement.left,
          top: placement.top,
          width: TOOLTIP_WIDTH,
          background: '#1e1e1e',
          border: '1px solid #ce9178',
          borderRadius: 6,
          padding: 14,
          zIndex: 9001,
          boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
          color: '#d4d4d4',
        }}
      >
        <div className="flex items-start justify-between mb-2">
          <div style={{ fontSize: 9, color: '#ce9178', fontWeight: 600, letterSpacing: 0.5, textTransform: 'uppercase' }}>
            Tour · {stepIdx + 1} / {steps.length}
          </div>
          <button
            onClick={skip}
            style={{ color: '#6a737d', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
            aria-label="Skip tour"
            title="Skip tour"
          >
            <X size={14} />
          </button>
        </div>

        <div style={{ fontSize: 13, fontWeight: 600, color: '#e8e8e8', marginBottom: 6 }}>
          {step.title}
        </div>
        <div style={{ fontSize: 11, color: '#b5b5b5', lineHeight: 1.5, marginBottom: 12 }}>
          {step.description}
        </div>

        <div className="flex items-center justify-between">
          <button
            onClick={skip}
            style={{
              fontSize: 10,
              color: '#6a737d',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 0',
            }}
          >
            Skip tour
          </button>
          <div className="flex items-center gap-1">
            {stepIdx > 0 && (
              <button
                onClick={back}
                style={{
                  fontSize: 10,
                  fontWeight: 500,
                  color: '#d4d4d4',
                  background: '#2a2d2e',
                  border: 'none',
                  borderRadius: 4,
                  padding: '5px 8px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 3,
                }}
              >
                <ChevronLeft size={11} /> Back
              </button>
            )}
            <button
              onClick={next}
              style={{
                fontSize: 10,
                fontWeight: 600,
                color: '#000',
                background: '#ce9178',
                border: 'none',
                borderRadius: 4,
                padding: '5px 10px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 3,
              }}
            >
              {stepIdx >= steps.length - 1 ? 'Done' : 'Next'}
              {stepIdx < steps.length - 1 && <ChevronRight size={11} />}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

function computeTooltipPosition(
  rect: Rect | null,
  preferredSide: 'top' | 'bottom' | 'left' | 'right',
): { left: number; top: number } {
  // No target → center the tooltip on screen.
  if (!rect) {
    return {
      left: Math.max(20, window.innerWidth / 2 - TOOLTIP_WIDTH / 2),
      top: Math.max(20, window.innerHeight / 2 - 100),
    }
  }
  const tooltipHeight = 180  // approximate; tooltip content is short
  const margin = 20
  // Bind rect to a non-null local so the nested `place` closure has a
  // narrowed type — TS doesn't propagate the early-return narrowing into
  // nested function scopes, which produced TS18047 errors before.
  const r = rect

  function place(side: 'top' | 'bottom' | 'left' | 'right'): { left: number; top: number } {
    switch (side) {
      case 'right':
        return {
          left: r.left + r.width + TOOLTIP_GAP,
          top: r.top + r.height / 2 - tooltipHeight / 2,
        }
      case 'left':
        return {
          left: r.left - TOOLTIP_WIDTH - TOOLTIP_GAP,
          top: r.top + r.height / 2 - tooltipHeight / 2,
        }
      case 'bottom':
        return {
          left: r.left + r.width / 2 - TOOLTIP_WIDTH / 2,
          top: r.top + r.height + TOOLTIP_GAP,
        }
      case 'top':
        return {
          left: r.left + r.width / 2 - TOOLTIP_WIDTH / 2,
          top: r.top - tooltipHeight - TOOLTIP_GAP,
        }
    }
  }

  // Try preferred side; fall back through the others if it would overflow.
  const order: Array<'top' | 'bottom' | 'left' | 'right'> = [
    preferredSide,
    ...(['right', 'left', 'bottom', 'top'] as const).filter((s) => s !== preferredSide),
  ]
  for (const side of order) {
    const p = place(side)
    if (
      p.left >= margin &&
      p.left + TOOLTIP_WIDTH <= window.innerWidth - margin &&
      p.top >= margin &&
      p.top + tooltipHeight <= window.innerHeight - margin
    ) {
      return p
    }
  }
  // Nothing fit — clamp the preferred placement into bounds.
  const p = place(preferredSide)
  return {
    left: Math.max(margin, Math.min(p.left, window.innerWidth - TOOLTIP_WIDTH - margin)),
    top: Math.max(margin, Math.min(p.top, window.innerHeight - tooltipHeight - margin)),
  }
}
