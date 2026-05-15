import type { ComponentProps } from 'react'

const variants = {
  // Generic semantic — colored text only, no chip styling
  success:  'text-emerald-400',
  warning:  'text-amber-400',
  danger:   'text-red-400',
  neutral:  'text-zinc-400',
  // Severity-specific (low → critical)
  low:      'text-amber-400',
  medium:   'text-orange-400',
  high:     'text-red-400',
  critical: 'text-red-300',
} as const

export type BadgeVariant = keyof typeof variants

type BadgeProps = ComponentProps<'span'> & {
  variant?: BadgeVariant
}

export function Badge({ variant = 'neutral', className = '', ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center text-[10px] uppercase tracking-[0.14em] font-medium ${variants[variant]} ${className}`}
      {...props}
    />
  )
}
