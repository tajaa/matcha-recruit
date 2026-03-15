import { Link } from 'react-router-dom'
import type { ComponentProps } from 'react'

const base =
  'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none'

const variants = {
  primary: 'bg-emerald-600 text-white hover:bg-emerald-500',
  secondary: 'bg-zinc-800 text-zinc-100 hover:bg-zinc-700',
  ghost: 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900',
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
