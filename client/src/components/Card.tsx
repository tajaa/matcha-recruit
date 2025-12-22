import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Card({ children, className = '', onClick }: CardProps) {
  return (
    <div className={`relative ${className}`} onClick={onClick}>
      {/* Corner brackets */}
      <div className="absolute -top-1.5 -left-1.5 w-3 h-3 border-t border-l border-zinc-700" />
      <div className="absolute -top-1.5 -right-1.5 w-3 h-3 border-t border-r border-zinc-700" />
      <div className="absolute -bottom-1.5 -left-1.5 w-3 h-3 border-b border-l border-zinc-700" />
      <div className="absolute -bottom-1.5 -right-1.5 w-3 h-3 border-b border-r border-zinc-700" />

      <div className="bg-zinc-900/50 border border-zinc-800 transition-all hover:border-zinc-700">
        {children}
      </div>
    </div>
  );
}

export function CardHeader({ children, className = '' }: CardProps) {
  return (
    <div className={`px-5 py-3 border-b border-zinc-800 ${className}`}>
      {children}
    </div>
  );
}

export function CardContent({ children, className = '', onClick }: CardProps) {
  return (
    <div className={`px-5 py-4 ${className}`} onClick={onClick}>
      {children}
    </div>
  );
}
