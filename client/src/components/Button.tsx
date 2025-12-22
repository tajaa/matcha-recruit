import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  ...props
}: ButtonProps) {
  const baseStyles =
    'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed font-mono tracking-wide uppercase';

  const variants = {
    primary:
      'bg-matcha-500 text-black hover:bg-matcha-400 hover:shadow-[0_0_20px_rgba(34,197,94,0.3)]',
    secondary:
      'bg-zinc-900 text-zinc-400 border border-zinc-700 hover:bg-zinc-800 hover:text-white hover:border-zinc-600',
    danger:
      'bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 hover:border-red-500/40',
    outline:
      'bg-transparent text-zinc-400 border border-zinc-700 hover:bg-zinc-900 hover:text-white hover:border-zinc-600',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-[10px]',
    md: 'px-4 py-2 text-[11px]',
    lg: 'px-6 py-3 text-xs',
  };

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
