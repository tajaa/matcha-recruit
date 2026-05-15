type Option<T extends string = string> = {
  value: T
  label: string
}

type Props<T extends string = string> = {
  options: Option<T>[]
  value: T
  onChange: (value: T) => void
  size?: 'sm' | 'md'
  className?: string
}

export function PillTabs<T extends string = string>({
  options,
  value,
  onChange,
  size = 'md',
  className = '',
}: Props<T>) {
  const padX = size === 'sm' ? 'px-3' : 'px-4'
  const padY = size === 'sm' ? 'py-1.5' : 'py-2'
  const text = size === 'sm' ? 'text-[10px]' : 'text-[11px]'

  return (
    <div
      className={`inline-flex border border-white/[0.08] rounded-lg overflow-hidden bg-zinc-900 ${className}`}
    >
      {options.map((opt) => {
        const active = value === opt.value
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`${padX} ${padY} ${text} uppercase tracking-[0.14em] font-medium transition-colors border-r border-white/[0.04] last:border-r-0 ${
              active
                ? 'bg-white/[0.06] text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.02]'
            }`}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
