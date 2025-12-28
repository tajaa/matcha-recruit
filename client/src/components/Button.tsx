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
    'inline-flex items-center justify-center font-medium transition-all duration-200 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed font-mono tracking-wide uppercase';

  const variants = {
    primary:
      'bg-white text-black hover:bg-zinc-200',
    secondary:
      'bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700 hover:text-white',
    danger:
      'bg-transparent text-red-400 border border-red-500/50 hover:bg-red-500/10',
    outline:
      'bg-transparent text-zinc-300 border border-zinc-600 hover:bg-zinc-800 hover:text-white',
    ghost:
      'bg-transparent text-zinc-400 hover:bg-zinc-800 hover:text-white',
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
