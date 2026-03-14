import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: string;
  afterSubtitle?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function PageHeader({ title, subtitle, afterSubtitle, children, className = '' }: PageHeaderProps) {
  return (
    <div className={`flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-zinc-800 pb-6 ${className}`}>
      <div>
        <h1 className="text-xl font-semibold text-zinc-100">{title}</h1>
        {subtitle && <p className="text-sm text-zinc-500 mt-0.5">{subtitle}</p>}
        {afterSubtitle}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
