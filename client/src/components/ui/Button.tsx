import { Link } from 'react-router-dom'
import type { ComponentProps } from 'react'

const base =
  'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none'

const variants = {
  primary: 'bg-zinc-700 text-white hover:bg-zinc-600',
  secondary: 'bg-zinc-800 text-zinc-100 hover:bg-zinc-700',
  ghost: 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900',
  // Destructive and affirmative actions were being hand-rolled at call sites
  // (each a divergent copy of the class string, so Apply and Reject rendered at
  // different heights). Their outline is an inset RING, not a border: a border
  // adds 2px the other variants don't have, which is the mismatch all over again.
  danger: 'ring-1 ring-inset ring-red-500/25 text-red-300 hover:bg-red-500/[0.06]',
  success: 'ring-1 ring-inset ring-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/[0.16]',
} as const

const sizes = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-5 py-2.5',
  lg: 'px-6 py-3',
} as const

type Variant = keyof typeof variants
type Size = keyof typeof sizes

type ButtonProps = ComponentProps<'button'> & {
  variant?: Variant
  size?: Size
}

type LinkButtonProps = ComponentProps<typeof Link> & {
  variant?: Variant
  size?: Size
}

export function Button({ variant = 'primary', size = 'md', className = '', ...props }: ButtonProps) {
  return (
    <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props} />
  )
}

export function LinkButton({ variant = 'primary', size = 'md', className = '', ...props }: LinkButtonProps) {
  return (
    <Link className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props} />
  )
}
