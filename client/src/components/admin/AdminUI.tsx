import { useContext, useId, type ComponentProps, type ReactNode } from 'react'
import { Button } from '../ui/Button'
import { AdminPageContext } from './AdminPageContext'

const field = 'admin-field rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 outline-none transition-colors focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 disabled:opacity-50'
const labelClass = 'mb-1.5 block text-xs font-medium text-zinc-300'

type LabelProps = { label?: string }
const fieldWidth = (className: string) => /(?:^|\s)w-/.test(className) ? '' : 'w-full'

export function AdminInput({ label, id, className = '', ...props }: ComponentProps<'input'> & LabelProps) {
  const generated = useId()
  const inputId = id || generated
  const input = <input id={inputId} className={`${fieldWidth(className)} ${field} ${className}`} {...props} />
  return label ? <label htmlFor={inputId}><span className={labelClass}>{label}</span>{input}</label> : input
}

export function AdminTextarea({ label, id, className = '', ...props }: ComponentProps<'textarea'> & LabelProps) {
  const generated = useId()
  const textareaId = id || generated
  const input = <textarea id={textareaId} className={`${fieldWidth(className)} min-h-20 resize-y ${field} ${className}`} {...props} />
  return label ? <label htmlFor={textareaId}><span className={labelClass}>{label}</span>{input}</label> : input
}

type SelectProps = ComponentProps<'select'> & LabelProps & {
  options?: readonly { value: string; label: string }[]
  placeholder?: string
}

export function AdminSelect({ label, id, options, placeholder, children, className = '', ...props }: SelectProps) {
  const generated = useId()
  const selectId = id || generated
  const select = <select id={selectId} className={`${label ? fieldWidth(className) : ''} ${field} ${className}`} {...props}>
    {placeholder && <option value="">{placeholder}</option>}
    {options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    {children}
  </select>
  return label ? <label htmlFor={selectId}><span className={labelClass}>{label}</span>{select}</label> : select
}

export function AdminButton({ size = 'sm', variant = 'primary', className = '', ...props }: ComponentProps<typeof Button>) {
  return <Button size={size} variant={variant} data-admin-variant={variant} className={`admin-button ${className}`} {...props} />
}

export function AdminCard({ className = '', ...props }: ComponentProps<'div'>) {
  const border = /(?:^|\s)border-(?:zinc|emerald|red|amber|orange|sky|blue|white|transparent)/.test(className) ? '' : 'admin-border border-zinc-800'
  const background = /(?:^|\s)bg-/.test(className) ? '' : 'admin-surface bg-zinc-900/50'
  return <div className={`rounded-lg border p-4 ${border} ${background} ${className}`} {...props} />
}

type SectionProps = { title: ReactNode; description?: ReactNode; actions?: ReactNode; className?: string }

export function AdminSectionHeader({ title, description, actions, className = '' }: SectionProps) {
  const embedded = useContext(AdminPageContext)
  const Heading = embedded ? 'h3' : 'h2'
  return <div className={`mb-4 flex flex-wrap items-start justify-between gap-3 ${className}`}>
      <div className="min-w-0 flex-1">
        <Heading className="text-sm font-medium text-zinc-300">{title}</Heading>
        {description && <div className="mt-1 text-xs leading-relaxed text-zinc-500">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
}

export function AdminSection({ title, description, actions, children, className = '' }: SectionProps & { children: ReactNode }) {
  return <section className={`min-w-0 ${className}`}>
    <AdminSectionHeader title={title} description={description} actions={actions} />
    {children}
  </section>
}

export function AdminFilterBar({ className = '', ...props }: ComponentProps<'div'>) {
  return <div className={`mb-6 flex flex-wrap items-center gap-3 ${className}`} {...props} />
}

export function AdminStat({ label, value, hint, icon, tone }: { label: ReactNode; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: 'gap' | 'ok' }) {
  return <AdminCard>
    <div className="flex items-center justify-between gap-2"><p className="text-xs font-medium text-zinc-500">{label}</p>{icon}</div>
    <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === 'gap' ? 'text-amber-400' : tone === 'ok' ? 'text-emerald-400' : 'text-zinc-100'}`}>{typeof value === 'number' ? value.toLocaleString() : value}</p>
    {hint && <div className="mt-1 text-xs text-zinc-500">{hint}</div>}
  </AdminCard>
}

export function AdminTable({ className = '', ...props }: ComponentProps<'table'>) {
  return <div className="admin-table overflow-x-auto rounded-lg border border-zinc-800">
    <table className={`w-full text-left text-sm text-zinc-300 [&_thead]:border-b [&_thead]:border-zinc-800 [&_thead]:bg-zinc-900/50 [&_th]:px-4 [&_th]:py-3 [&_th]:text-xs [&_th]:font-medium [&_th]:text-zinc-500 [&_td]:px-4 [&_td]:py-3 [&_tbody>tr+tr]:border-t [&_tbody>tr+tr]:border-zinc-800/60 ${className}`} {...props} />
  </div>
}
