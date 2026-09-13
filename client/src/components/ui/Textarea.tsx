import { useId } from 'react'
import type { ComponentProps } from 'react'

type TextareaProps = ComponentProps<'textarea'> & {
  label: string
}

export function Textarea({ label, id, className = '', ...props }: TextareaProps) {
  // See Input: an unassociated label is a caption, not a label.
  const generated = useId()
  const textareaId = id || generated  // `||`: an empty-string id associates nothing either
  return (
    <div>
      {label && (
        <label htmlFor={textareaId} className="block text-sm font-medium text-zinc-300 mb-1.5">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        className={`w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors resize-y min-h-[80px] ${className}`}
        {...props}
      />
    </div>
  )
}
