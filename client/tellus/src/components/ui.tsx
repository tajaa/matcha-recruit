import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes, SelectHTMLAttributes } from 'react'
import { Loader2 } from 'lucide-react'

export function Button({
  children, loading, disabled, variant = 'primary', className = '', ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean; variant?: 'primary' | 'ghost' | 'danger' | 'soft' }) {
  const base = 'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed'
  const variants = {
    primary: 'bg-tu-accent text-black hover:bg-tu-accent-soft',
    soft: 'bg-tu-panel2 text-tu-text border border-tu-border hover:border-tu-accent',
    ghost: 'text-tu-dim hover:text-tu-text',
    danger: 'bg-tu-bad/15 text-tu-bad border border-tu-bad/30 hover:bg-tu-bad/25',
  }
  // `disabled` is destructured (not left in the spread) so a caller-passed
  // disabled={false} can't override the loading lock — an in-flight action
  // (e.g. redeem) must not be double-clickable.
  return (
    <button className={`${base} ${variants[variant]} ${className}`} disabled={loading || disabled} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

export function Input({ label, className = '', ...props }: InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  return (
    <label className="block">
      {label && <span className="mb-1 block text-xs font-medium text-tu-dim">{label}</span>}
      <input
        className={`w-full rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2 text-sm text-tu-text placeholder:text-tu-faint focus:border-tu-accent focus:outline-none ${className}`}
        {...props}
      />
    </label>
  )
}

export function Textarea({ label, className = '', ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }) {
  return (
    <label className="block">
      {label && <span className="mb-1 block text-xs font-medium text-tu-dim">{label}</span>}
      <textarea
        className={`w-full rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2 text-sm text-tu-text placeholder:text-tu-faint focus:border-tu-accent focus:outline-none ${className}`}
        {...props}
      />
    </label>
  )
}

export function Select({ label, options, className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label?: string; options: { value: string; label: string }[] }) {
  return (
    <label className="block">
      {label && <span className="mb-1 block text-xs font-medium text-tu-dim">{label}</span>}
      <select
        className={`w-full rounded-lg border border-tu-border bg-tu-panel2 px-3 py-2 text-sm text-tu-text focus:border-tu-accent focus:outline-none ${className}`}
        {...props}
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-tu-border bg-tu-panel p-5 ${className}`}>{children}</div>
}

export function ErrorText({ children }: { children: ReactNode }) {
  if (!children) return null
  return <p className="text-sm text-tu-bad">{children}</p>
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-16 text-tu-faint">
      <Loader2 className="h-6 w-6 animate-spin" />
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-tu-border p-10 text-center text-sm text-tu-faint">{children}</div>
}

const SENTIMENT_STYLE: Record<string, string> = {
  positive: 'bg-tu-good/15 text-tu-good',
  neutral: 'bg-tu-panel2 text-tu-dim',
  negative: 'bg-tu-bad/15 text-tu-bad',
}

export function Chip({ children, tone }: { children: ReactNode; tone?: string }) {
  const cls = tone && SENTIMENT_STYLE[tone] ? SENTIMENT_STYLE[tone] : 'bg-tu-panel2 text-tu-dim'
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>{children}</span>
}
