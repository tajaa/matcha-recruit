import type { ComponentProps } from 'react'

type CardProps = ComponentProps<'div'>

export function Card({ className = '', ...props }: CardProps) {
  return (
    <div
      className={`rounded-xl bg-zinc-900 p-4 ${className}`}
      {...props}
    />
  )
}
