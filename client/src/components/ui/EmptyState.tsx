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
    <div className={`text-center py-16 border border-zinc-800 rounded ${className}`}>
      <Icon size={20} className="mx-auto mb-3 text-zinc-600" />
      <p className="text-zinc-300 text-sm font-medium mb-1">{title}</p>
      <p className="text-zinc-500 text-sm mb-4 max-w-sm mx-auto">{description}</p>
      {onAction && actionLabel && (
        <button onClick={onAction} className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-100 text-zinc-900 hover:bg-white text-sm rounded">
          {ActionIcon && <ActionIcon size={14} />}
          {actionLabel}
        </button>
      )}
    </div>
  );
}
