import type { ComponentProps, ReactNode } from 'react'

const itemClass = 'admin-tab inline-flex shrink-0 items-center justify-center gap-2 rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 disabled:pointer-events-none disabled:opacity-50'
const selection = (active: boolean) => active ? 'bg-zinc-700/60 text-zinc-100 shadow-sm' : 'text-zinc-400 hover:text-zinc-200'

type Option<T extends string> = { value: T; label: ReactNode; disabled?: boolean }

export function AdminTabBar({ className = '', ...props }: ComponentProps<'div'>) {
  return <div className={`admin-tabbar mb-3 flex w-fit max-w-full flex-wrap items-center gap-0.5 rounded-lg border border-zinc-800 bg-zinc-900/50 p-0.5 ${className}`} {...props} />
}

export function AdminTab({ active, className = '', ...props }: ComponentProps<'button'> & { active: boolean }) {
  return <button type="button" aria-pressed={active} className={`${itemClass} ${selection(active)} ${className}`} {...props} />
}

export function AdminTabs<T extends string>({ options, value, onChange, className = '', label = 'Views' }: {
  options: readonly Option<T>[]
  value: T
  onChange: (value: T) => void
  className?: string
  label?: string
  size?: 'sm' | 'md'
}) {
  return (
    <AdminTabBar role="group" aria-label={label} className={className}>
      {options.map((option) => <AdminTab key={option.value} active={value === option.value} disabled={option.disabled} onClick={() => onChange(option.value)}>{option.label}</AdminTab>)}
    </AdminTabBar>
  )
}
