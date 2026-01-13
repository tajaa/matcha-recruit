import type { ReactNode } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  hoverEffect?: boolean;
}

export function GlassCard({ children, className = '', onClick, hoverEffect = false }: GlassCardProps) {
  return (
    <div
      className={`
        relative overflow-hidden
        bg-white
        border border-zinc-200
        shadow-sm
        ${hoverEffect ? 'hover:border-zinc-300 hover:shadow-md hover:-translate-y-0.5' : ''}
        transition-all duration-300 ease-out
        ${className}
      `}
      onClick={onClick}
    >
      {children}
    </div>
  );
}
