import type { ComponentProps } from 'react'

type SelectProps = Omit<ComponentProps<'select'>, 'children'> & {
  label: string
  options: { value: string; label: string }[]
  placeholder?: string
}

export function Select({ label, options, placeholder, id, className = '', ...props }: SelectProps) {
  return (
    <div>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-zinc-300 mb-1.5">
          {label}
        </label>
      )}
      <select
        id={id}
        className={`w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors ${className}`}
        {...props}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}
