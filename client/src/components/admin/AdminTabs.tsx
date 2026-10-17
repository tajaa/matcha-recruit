import type { ComponentProps, ReactNode } from 'react'
import { Link } from 'react-router-dom'

const itemClass = 'inline-flex shrink-0 items-center justify-center gap-2 border-b-2 px-1 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:pointer-events-none disabled:opacity-50'
const selection = (active: boolean) => active ? 'border-emerald-500 text-zinc-100' : 'border-transparent text-zinc-500 hover:border-zinc-600 hover:text-zinc-200'

type Option<T extends string> = { value: T; label: ReactNode; disabled?: boolean }

export function AdminTabBar({ className = '', ...props }: ComponentProps<'div'>) {
  return <div className={`mb-6 flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-zinc-800 ${className}`} {...props} />
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

export function AdminRouteTabs({ links, activeTo, label }: {
  links: readonly { to: string; label: string }[]
  activeTo: string
  label: string
}) {
  return (
    <nav aria-label={label}>
      <AdminTabBar>
        {links.map((link) => <Link key={link.to} to={link.to} aria-current={activeTo === link.to ? 'page' : undefined} className={`${itemClass} ${selection(activeTo === link.to)}`}>{link.label}</Link>)}
      </AdminTabBar>
    </nav>
  )
}
