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
  const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-zinc-950 disabled:opacity-50 disabled:cursor-not-allowed';

  const variants = {
    primary: 'bg-matcha-500 text-zinc-950 hover:bg-matcha-400 focus:ring-matcha-500 border border-transparent shadow-[0_0_15px_rgba(34,197,94,0.3)] hover:shadow-[0_0_20px_rgba(34,197,94,0.5)]',
    secondary: 'bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700 hover:border-zinc-600 focus:ring-zinc-500 hover:text-white',
    danger: 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 hover:border-red-500/30 focus:ring-red-500',
    outline: 'bg-transparent text-white border border-zinc-700 hover:bg-zinc-800 focus:ring-zinc-500',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-xs tracking-wide uppercase',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
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
