import type { ComponentProps } from 'react'

const variants = {
  success: 'bg-zinc-800 text-zinc-300 border-zinc-700',
  warning: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  danger: 'bg-zinc-800 text-zinc-500 border-zinc-600',
  neutral: 'bg-zinc-800/60 text-zinc-500 border-zinc-700',
} as const

export type BadgeVariant = keyof typeof variants

type BadgeProps = ComponentProps<'span'> & {
  variant?: BadgeVariant
}

export function Badge({ variant = 'neutral', className = '', ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${variants[variant]} ${className}`}
      {...props}
    />
  )
}
