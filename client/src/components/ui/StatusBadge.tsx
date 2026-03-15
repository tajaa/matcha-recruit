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
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${entry.muted ? 'bg-stone-100 text-stone-400' : 'bg-stone-200 text-stone-600'} ${className}`}>
      {Icon && <Icon size={11} />}
      {entry.label}
    </span>
  );
}
