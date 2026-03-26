import type { ComponentProps } from 'react'

type InputProps = ComponentProps<'input'> & {
  label: string
}

export function Input({ label, id, className = '', ...props }: InputProps) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-zinc-300 mb-1.5">
        {label}
      </label>
      <input
        id={id}
        className={`w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors ${className}`}
        {...props}
      />
    </div>
  )
}
