/** Huume's avatar for channel system messages (`message_type === 'system'`).
 *
 *  Those rows have no `sender_id` — the backend writes them with the column
 *  null (migration `ems01`) — so there is no profile image to fall back on
 *  and the initial-letter circle every human row uses would render "?".
 *  An ASCII face instead: it needs no asset, no network fetch, and no
 *  theme-specific artwork, and it reads as the agent rather than a user.
 *
 *  Deliberately three fixed lines of box-drawing characters at a fixed size
 *  rather than an SVG — the pieces are all monospace-safe glyphs, so it
 *  renders identically wherever the work app's font stack lands.
 */
export function HuumeAvatar({ className = '' }: { className?: string }) {
  return (
    <div
      title="Huume"
      aria-label="Huume"
      className={`w-8 h-8 shrink-0 mt-0.5 rounded-lg bg-w-surface2 border border-w-line flex flex-col items-center justify-center font-mono text-w-accent leading-[1.05] select-none ${className}`}
    >
      <span className="text-[6px]">╔═══╗</span>
      <span className="text-[6px]">║◉◡◉║</span>
      <span className="text-[6px]">╚═══╝</span>
    </div>
  )
}
