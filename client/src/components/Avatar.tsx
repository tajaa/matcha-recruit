type AvatarProps = {
  name: string
  avatarUrl?: string | null
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizes = {
  sm: 'w-7 h-7 text-[10px]',
  md: 'w-9 h-9 text-xs',
  lg: 'w-14 h-14 text-lg',
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  return (name[0] || '?').toUpperCase()
}

// Deterministic color from name
const colors = [
  'bg-emerald-800', 'bg-blue-800', 'bg-violet-800', 'bg-amber-800',
  'bg-rose-800', 'bg-cyan-800', 'bg-fuchsia-800', 'bg-lime-800',
]

function colorFor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return colors[Math.abs(hash) % colors.length]
}

export default function Avatar({ name, avatarUrl, size = 'md', className = '' }: AvatarProps) {
  const s = sizes[size]

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={name}
        className={`${s} rounded-full object-cover shrink-0 ${className}`}
      />
    )
  }

  return (
    <div className={`${s} rounded-full ${colorFor(name)} flex items-center justify-center text-white font-medium shrink-0 ${className}`}>
      {initials(name)}
    </div>
  )
}
