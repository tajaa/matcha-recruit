interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const statusConfig: Record<string, { color: string; bg: string; border: string }> = {
  draft: { color: 'text-zinc-400', bg: 'bg-zinc-900/30', border: 'border-zinc-500/20' },
  pending: { color: 'text-amber-400', bg: 'bg-amber-900/30', border: 'border-amber-500/20' },
  active: { color: 'text-emerald-400', bg: 'bg-emerald-900/30', border: 'border-emerald-500/20' },
  closed: { color: 'text-zinc-500', bg: 'bg-zinc-900/30', border: 'border-zinc-600/20' },
  completed: { color: 'text-emerald-400', bg: 'bg-emerald-900/30', border: 'border-emerald-500/20' },
  archived: { color: 'text-zinc-600', bg: 'bg-zinc-900/30', border: 'border-zinc-700/20' },
  self_submitted: { color: 'text-blue-400', bg: 'bg-blue-900/30', border: 'border-blue-500/20' },
  manager_submitted: { color: 'text-purple-400', bg: 'bg-purple-900/30', border: 'border-purple-500/20' },
  skipped: { color: 'text-zinc-500', bg: 'bg-zinc-900/30', border: 'border-zinc-600/20' },
};

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const config = statusConfig[status.toLowerCase()] || statusConfig.draft;
  const sizeClass = size === 'sm' ? 'text-[10px] px-2 py-1' : 'text-xs px-3 py-1.5';

  return (
    <span className={`inline-flex items-center gap-1.5 rounded font-bold uppercase tracking-wider border ${config.color} ${config.bg} ${config.border} ${sizeClass}`}>
      {status.replace('_', ' ')}
    </span>
  );
}
