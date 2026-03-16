import type { ComponentProps } from 'react'

const variants = {
  success: 'bg-emerald-950 text-emerald-400 border-emerald-800',
  warning: 'bg-amber-950 text-amber-400 border-amber-800',
  danger: 'bg-red-950 text-red-400 border-red-800',
  neutral: 'bg-zinc-800 text-zinc-400 border-zinc-700',
} as const

export type BadgeVariant = keyof typeof variants

type BadgeProps = ComponentProps<'span'> & {
  variant?: BadgeVariant
}

export function Badge({ variant = 'neutral', className = '', ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${variants[variant]} ${className}`}
      {...props}
    />
  )
}
