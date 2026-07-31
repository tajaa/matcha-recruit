/** Huume's glyph — a compact geometric "agent" face used everywhere Huume
 *  needs an avatar (channel system-message pills, thread replies). Inline
 *  SVG on purpose: no asset request, no theme-specific artwork, and it
 *  scales crisp at any chip size, unlike the fixed-px ASCII face it
 *  replaces. `currentColor` throughout — the caller's text color classes
 *  drive the whole glyph, so light/dark and the orange Huume identity stay
 *  callsite concerns, not baked into this file.
 */
export function HuumeMark({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      role="img"
      aria-label="Huume"
    >
      {/* Antenna */}
      <line x1="12" y1="2.5" x2="12" y2="5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="12" cy="2" r="1.15" fill="currentColor" />
      {/* Head */}
      <rect x="4" y="5" width="16" height="14" rx="4" stroke="currentColor" strokeWidth="1.4" />
      {/* Circuit ticks off the head's corners */}
      <path
        d="M4 9.5H2M4 14.5H2M20 9.5h2M20 14.5h2"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      {/* Eyes */}
      <circle cx="9" cy="12" r="1.6" fill="currentColor" />
      <circle cx="15" cy="12" r="1.6" fill="currentColor" />
      {/* Mouth */}
      <line x1="9" y1="15.5" x2="15" y2="15.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}
