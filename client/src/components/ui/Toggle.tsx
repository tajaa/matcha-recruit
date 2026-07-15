type ToggleProps = {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  size?: 'md' | 'sm'
}

const SIZES = {
  md: { track: 'h-5 w-9', knob: 'h-4 w-4', on: 'translate-x-4' },
  sm: { track: 'h-4 w-7', knob: 'h-3 w-3', on: 'translate-x-3' },
} as const

export function Toggle({ checked, onChange, disabled, size = 'md' }: ToggleProps) {
  const s = SIZES[size]
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex ${s.track} shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? 'bg-emerald-600' : 'bg-zinc-700'
      }`}
    >
      <span
        className={`pointer-events-none inline-block ${s.knob} rounded-full bg-white shadow-sm transition-transform ${
          checked ? s.on : 'translate-x-0'
        }`}
      />
    </button>
  )
}
