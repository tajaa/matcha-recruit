import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface CollapsibleProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  icon?: React.ElementType;
  variant?: 'dark' | 'light';
}

export function Collapsible({ title, children, defaultOpen = true, icon: Icon, variant = 'dark' }: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const isLight = variant === 'light';

  return (
    <div className={isLight ? 'bg-stone-100 rounded-xl overflow-hidden' : 'border border-white/10 bg-zinc-900/30 overflow-hidden'}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full p-3 flex justify-between items-center transition-colors text-left ${isLight ? 'hover:bg-stone-50' : 'hover:bg-white/5'}`}
      >
        <div className="flex items-center gap-2.5">
          {Icon && <Icon className={`w-3.5 h-3.5 ${isLight ? 'text-stone-400' : 'text-zinc-500'}`} />}
          <h2 className={isLight ? 'text-[11px] text-stone-500 font-semibold' : 'text-zinc-100 text-[11px] font-semibold'}>{title}</h2>
        </div>
        {isOpen ? (
          <ChevronUp className={`w-3.5 h-3.5 ${isLight ? 'text-stone-400' : 'text-zinc-500'}`} />
        ) : (
          <ChevronDown className={`w-3.5 h-3.5 ${isLight ? 'text-stone-400' : 'text-zinc-500'}`} />
        )}
      </button>
      {isOpen && (
        <div className={`animate-in slide-in-from-top-2 duration-200 ${isLight ? 'border-t border-stone-200' : 'border-t border-white/10'}`}>
          {children}
        </div>
      )}
    </div>
  );
}
