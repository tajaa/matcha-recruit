import type { ComponentProps } from 'react'

const variants = {
  // Generic semantic
  success:  'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  warning:  'bg-amber-500/10 text-amber-400 border-amber-500/20',
  danger:   'bg-red-500/10 text-red-400 border-red-500/20',
  neutral:  'bg-zinc-800/60 text-zinc-400 border-white/10',
  // Severity-specific (low → critical)
  low:      'bg-amber-500/10 text-amber-400 border-amber-500/20',
  medium:   'bg-orange-500/10 text-orange-400 border-orange-500/20',
  high:     'bg-red-500/10 text-red-400 border-red-500/20',
  critical: 'bg-red-500/15 text-red-300 border-red-500/30',
} as const

export type BadgeVariant = keyof typeof variants

type BadgeProps = ComponentProps<'span'> & {
  variant?: BadgeVariant
}

export function Badge({ variant = 'neutral', className = '', ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-sm border px-1.5 py-[1px] text-[9px] uppercase tracking-[0.12em] font-light ${variants[variant]} ${className}`}
      {...props}
    />
  )
}
