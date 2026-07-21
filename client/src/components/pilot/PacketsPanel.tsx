import { type ReactNode } from 'react'
import { HelpHint } from '../ui/HelpHint'
import { LABEL } from '../ui'

/** Shared "Work product" packet-list shell for Broker Pilot and Legal Pilot.
 *
 *  The two pilots' packet ROWS diverge structurally and are deliberately kept
 *  per-pilot (passed as `children`): Broker renders each packet as a single
 *  whole-row download <button> captioned by filename; Legal renders a card with
 *  a kind header, separate Download / Send-to-counsel buttons, a chain-of-custody
 *  line, and latest-per-kind pinning. What IS shared — and all this shell owns —
 *  is the empty-guard, the outer wrapper, and the "Work product" + HelpHint
 *  header. The header has two skins (`variant`): Broker's LABEL-primitive caption
 *  with a right-aligned count, and Legal's inline uppercase caption with none. */
export function PacketsPanel({ empty, className, variant, helpText, count, children }: {
  empty: boolean
  className: string
  variant: 'label' | 'inline'
  helpText: string
  count?: number
  children: ReactNode
}) {
  if (empty) return null
  return (
    <div className={className}>
      {variant === 'label' ? (
        <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
          <span className="inline-flex items-center gap-1.5">
            <span className={LABEL}>Work product</span>
            <HelpHint text={helpText} />
          </span>
          {count != null && (
            <span className="font-mono text-[11px] tabular-nums text-zinc-500">{count}</span>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-1.5 px-4 pb-1 pt-3 text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">
          Work product
          <HelpHint text={helpText} />
        </div>
      )}
      {children}
    </div>
  )
}
