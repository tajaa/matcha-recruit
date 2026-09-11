import { useId } from 'react'
import type { ComponentProps } from 'react'

type InputProps = ComponentProps<'input'> & {
  label?: string
}

export function Input({ label, id, className = '', ...props }: InputProps) {
  // A label with no `htmlFor` target is a caption: clicking it does nothing and
  // a screen reader reads the field as unlabeled. Nearly every call site omits
  // `id`, so generate one rather than ask 200 of them to remember.
  const generated = useId()
  const inputId = id || generated  // `||`: an empty-string id associates nothing either
  return (
    <div>
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-zinc-300 mb-1.5">
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors ${className}`}
        {...props}
      />
    </div>
  )
}
