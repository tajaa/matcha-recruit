import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'

type Option = { value: string; label: string }

type SelectProps = {
  label?: string
  options: Option[]
  value?: string
  onChange?: (event: { target: { value: string } }) => void
  placeholder?: string
  id?: string
  className?: string
  disabled?: boolean
  name?: string
}

export function Select({
  label,
  options,
  value = '',
  onChange,
  placeholder,
  id,
  className = '',
  disabled = false,
  name,
}: SelectProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const all: Option[] = placeholder
    ? [{ value: '', label: placeholder }, ...options]
    : options
  const selected = all.find((o) => o.value === value) ?? all[0]

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function pick(v: string) {
    setOpen(false)
    onChange?.({ target: { value: v } })
  }

  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className="block text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-500 mb-1.5">
          {label}
        </label>
      )}
      <div ref={ref} className="relative">
        <button
          type="button"
          id={id}
          name={name}
          disabled={disabled}
          onClick={() => !disabled && setOpen((v) => !v)}
          className={`w-full flex items-center justify-between gap-2 bg-zinc-900 border border-white/[0.08] rounded-lg px-3 py-2 text-[12px] text-zinc-200 hover:border-white/15 hover:bg-zinc-800/60 transition-colors ${
            disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
          } ${open ? 'border-white/20' : ''}`}
        >
          <span className="truncate">{selected?.label ?? placeholder ?? ''}</span>
          <ChevronDown className={`w-3.5 h-3.5 text-zinc-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} strokeWidth={1.6} />
        </button>
        {open && (
          <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-zinc-900 border border-white/10 rounded-lg shadow-2xl shadow-black/40 overflow-hidden max-h-[280px] overflow-y-auto">
            {all.map((opt) => {
              const isSel = opt.value === selected?.value
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => pick(opt.value)}
                  className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-[12px] transition-colors ${
                    isSel ? 'text-zinc-100 bg-white/[0.04]' : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.03]'
                  }`}
                >
                  <span className="truncate">{opt.label}</span>
                  {isSel && <Check className="w-3 h-3 text-emerald-400 shrink-0" strokeWidth={2} />}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
