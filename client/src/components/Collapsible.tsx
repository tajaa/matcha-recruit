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
    <div className={isLight ? 'bg-sage-100 rounded-3xl overflow-hidden' : 'border border-white/10 bg-zinc-900/30 overflow-hidden'}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full p-4 flex justify-between items-center transition-colors text-left ${isLight ? 'hover:bg-sage-200' : 'hover:bg-white/5'}`}
      >
        <div className="flex items-center gap-3">
          {Icon && <Icon className={`w-4 h-4 ${isLight ? 'text-sage-400' : 'text-zinc-500'}`} />}
          <h2 className={`text-base font-semibold ${isLight ? 'text-sage-900' : 'text-white text-[10px] font-bold uppercase tracking-[0.2em]'}`}>{title}</h2>
        </div>
        {isOpen ? (
          <ChevronUp className={`w-4 h-4 ${isLight ? 'text-sage-400' : 'text-zinc-500'}`} />
        ) : (
          <ChevronDown className={`w-4 h-4 ${isLight ? 'text-sage-400' : 'text-zinc-500'}`} />
        )}
      </button>
      {isOpen && (
        <div className={`animate-in slide-in-from-top-2 duration-200 ${isLight ? 'border-t border-sage-300' : 'border-t border-white/10'}`}>
          {children}
        </div>
      )}
    </div>
  );
}
