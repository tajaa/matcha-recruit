import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface CollapsibleProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  icon?: React.ElementType;
}

export function Collapsible({ title, children, defaultOpen = true, icon: Icon }: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-white/10 bg-zinc-900/30 overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-6 flex justify-between items-center hover:bg-white/5 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          {Icon && <Icon className="w-4 h-4 text-zinc-500" />}
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">{title}</h2>
        </div>
        {isOpen ? (
          <ChevronUp className="w-4 h-4 text-zinc-500" />
        ) : (
          <ChevronDown className="w-4 h-4 text-zinc-500" />
        )}
      </button>
      {isOpen && (
        <div className="border-t border-white/10 animate-in slide-in-from-top-2 duration-200">
          {children}
        </div>
      )}
    </div>
  );
}
