import type { LucideIcon } from 'lucide-react';

export interface StatusConfig {
  label: string;
  icon?: LucideIcon;
  muted?: boolean;
}

interface StatusBadgeProps {
  status: string;
  config: Record<string, StatusConfig>;
  className?: string;
}

export function StatusBadge({ status, config, className = '' }: StatusBadgeProps) {
  const entry = config[status];
  if (!entry) return null;
  const Icon = entry.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 border rounded text-xs ${entry.muted ? 'border-zinc-800 text-zinc-500' : 'border-zinc-600 text-zinc-300'} ${className}`}>
      {Icon && <Icon size={11} />}
      {entry.label}
    </span>
  );
}
