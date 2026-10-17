export function ActionBtn({
  icon: Icon,
  label,
  onClick,
  tone,
  disabled,
}: {
  icon?: React.ElementType
  label: string
  onClick: () => void
  tone?: 'danger' | 'success'
  disabled?: boolean
}) {
  const cls =
    tone === 'danger'
      ? 'bg-red-900/40 text-red-200 hover:bg-red-900/60'
      : tone === 'success'
      ? 'bg-emerald-700 text-white hover:bg-emerald-600'
      : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors disabled:opacity-40 ${cls}`}
    >
      {Icon && <Icon size={10} />}
      {label}
    </button>
  )
}
