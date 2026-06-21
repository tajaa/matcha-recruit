import { HelpCircle } from 'lucide-react'

/**
 * Small hover "(?)" hint — explains what a broker surface does + how it helps.
 * Shared across the broker dashboard + sidebar widgets.
 */
export function HelpHint({ text }: { text: string }) {
  return (
    <span className="relative group/help inline-flex align-middle">
      <HelpCircle className="w-3.5 h-3.5 text-zinc-500 hover:text-zinc-300 transition-colors cursor-help" />
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 px-3 py-2 text-[10px] leading-relaxed text-zinc-300 bg-zinc-900 border border-white/10 rounded-lg shadow-xl opacity-0 group-hover/help:opacity-100 transition-opacity z-50 text-left normal-case tracking-normal font-normal">
        {text}
      </span>
    </span>
  )
}
