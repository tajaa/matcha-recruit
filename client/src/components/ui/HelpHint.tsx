import { HelpCircle } from 'lucide-react'

/**
 * Small hover "(?)" hint — explains what a control or concept on the page means.
 * Generic, shared across features (Pilot consoles, dashboards, forms, etc.).
 *
 * Tooltip drops BELOW the icon (so it never clips against the top of the page)
 * and anchors to the icon's left edge by default; pass align="right" for hints
 * sitting near the right edge (e.g. right-aligned table-column headers).
 */
export function HelpHint({ text, align = 'left' }: { text: string; align?: 'left' | 'right' }) {
  return (
    <span className="relative group/help inline-flex align-middle">
      <HelpCircle className="w-3.5 h-3.5 text-zinc-500 hover:text-zinc-200 transition-colors cursor-help" />
      <span
        className={`pointer-events-none absolute top-full ${align === 'right' ? 'right-0' : 'left-0'} mt-2 w-64 px-3 py-2 text-[11px] leading-relaxed text-zinc-100 bg-zinc-950 border border-white/15 rounded-lg shadow-2xl opacity-0 group-hover/help:opacity-100 transition-opacity z-50 text-left normal-case tracking-normal font-normal`}
      >
        {text}
      </span>
    </span>
  )
}
