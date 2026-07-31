import { HuumeMark } from '../HuumeMark'

/** Huume's avatar for channel system messages (`message_type === 'system'`).
 *
 *  Those rows have no `sender_id` — the backend writes them with the column
 *  null (migration `ems01`) — so there is no profile image to fall back on
 *  and the initial-letter circle every human row uses would render "?".
 *  `<HuumeMark>` instead: no asset, no network fetch, and it reads as the
 *  agent rather than a user.
 */
export function HuumeAvatar({ className = '' }: { className?: string }) {
  return (
    <div
      title="Huume"
      aria-label="Huume"
      className={`w-8 h-8 shrink-0 mt-0.5 rounded-lg bg-w-surface2 border border-w-line flex items-center justify-center text-w-accent select-none ${className}`}
    >
      <HuumeMark className="w-5 h-5" />
    </div>
  )
}
