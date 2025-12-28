import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function Card({ children, className = '', onClick }: CardProps) {
  return (
    <div
      className={`bg-zinc-900 border border-zinc-800 hover:border-zinc-700 transition-colors ${className}`}
      onClick={onClick}
    >
      {children}
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
