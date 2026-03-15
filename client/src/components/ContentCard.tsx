import type { ReactNode } from 'react';
import { useIsLightMode } from '../hooks/useIsLightMode';

interface ContentCardProps {
  children: ReactNode;
  className?: string;
  padding?: boolean;
}

interface ContentCardHeaderProps {
  children: ReactNode;
  className?: string;
}

interface ContentCardBodyProps {
  children: ReactNode;
  className?: string;
}

/**
 * Shared card wrapper used across pages (Dashboard, Compliance, etc.).
 * Automatically picks light/dark styling.
 */
export function ContentCard({ children, className = '', padding = false }: ContentCardProps) {
  const isLight = useIsLightMode();
  const base = isLight
    ? 'bg-stone-100 rounded-xl'
    : 'bg-zinc-900/50 border border-white/10 rounded-xl';
  return (
    <div className={`${base} overflow-hidden ${padding ? 'p-6' : ''} ${className}`}>
      {children}
    </div>
  );
}

export function ContentCardHeader({ children, className = '' }: ContentCardHeaderProps) {
  const isLight = useIsLightMode();
  return (
    <div className={`p-4 border-b ${isLight ? 'border-stone-200' : 'border-white/10'} flex items-center justify-between ${className}`}>
      {children}
    </div>
  );
}

export function ContentCardBody({ children, className = '' }: ContentCardBodyProps) {
  return (
    <div className={`p-4 ${className}`}>{children}</div>
  );
}
