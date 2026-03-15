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
    <div className={`flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-stone-200 pb-4 ${className}`}>
      <div>
        <h1 className="text-xl font-semibold text-zinc-900">{title}</h1>
        {subtitle && <p className="text-sm text-stone-500 mt-0.5">{subtitle}</p>}
        {afterSubtitle}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
