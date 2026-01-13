import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'outline' | 'ghost';
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
    'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed font-mono tracking-wider uppercase relative overflow-hidden group';

  const variants = {
    primary:
      'bg-zinc-900 text-white hover:bg-zinc-800 border border-zinc-900',
    secondary:
      'bg-white text-zinc-600 border border-zinc-200 hover:border-zinc-300 hover:text-zinc-900 hover:bg-zinc-50',
    danger:
      'bg-zinc-100 text-zinc-700 border border-zinc-300 hover:bg-zinc-200 hover:border-zinc-400',
    outline:
      'bg-transparent text-zinc-600 border border-zinc-300 hover:border-zinc-400 hover:text-zinc-900',
    ghost:
      'bg-transparent text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-[10px]',
    md: 'px-5 py-2.5 text-[10px]',
    lg: 'px-8 py-3 text-xs',
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
