import type { ComponentProps } from 'react'

type CardProps = ComponentProps<'div'>

export function Card({ className = '', ...props }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-zinc-800 bg-zinc-900/50 shadow-sm shadow-black/20 p-5 ${className}`}
      {...props}
    />
  )
}
