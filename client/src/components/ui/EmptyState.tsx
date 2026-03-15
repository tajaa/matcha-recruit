import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  actionIcon?: LucideIcon;
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, actionLabel, onAction, actionIcon: ActionIcon, className = '' }: EmptyStateProps) {
  return (
    <div className={`text-center py-16 border border-zinc-200 rounded ${className}`}>
      <Icon size={20} className="mx-auto mb-3 text-zinc-400" />
      <p className="text-zinc-700 text-sm font-medium mb-1">{title}</p>
      <p className="text-zinc-400 text-sm mb-4 max-w-sm mx-auto">{description}</p>
      {onAction && actionLabel && (
        <button onClick={onAction} className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-800 text-white hover:bg-zinc-700 text-sm rounded">
          {ActionIcon && <ActionIcon size={14} />}
          {actionLabel}
        </button>
      )}
    </div>
  );
}
