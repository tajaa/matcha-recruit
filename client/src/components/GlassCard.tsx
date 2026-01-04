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
        bg-zinc-900/40 backdrop-blur-sm
        border border-white/5
        shadow-xl shadow-black/20
        ${hoverEffect ? 'hover:bg-zinc-900/60 hover:border-white/10 hover:shadow-2xl hover:shadow-black/30 hover:-translate-y-0.5' : ''}
        transition-all duration-300 ease-out
        ${className}
      `}
      onClick={onClick}
    >
      {/* Subtle top sheen */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-50" />
      
      {children}
    </div>
  );
}
