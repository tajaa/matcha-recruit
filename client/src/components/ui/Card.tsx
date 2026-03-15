import type { ComponentProps } from 'react'

type CardProps = ComponentProps<'div'>

export function Card({ className = '', ...props }: CardProps) {
  return (
    <div
      className={`rounded-xl border border-zinc-800 bg-zinc-900/50 p-8 ${className}`}
      {...props}
    />
  )
}
