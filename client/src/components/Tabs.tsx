import { useState, type ReactNode } from 'react';

interface Tab {
  id: string;
  label: string;
  icon?: React.ElementType;
}

interface TabsProps {
  tabs: Tab[];
  children: (activeTabId: string) => ReactNode;
  variant?: 'dark' | 'light';
}

export function Tabs({ tabs, children, variant = 'dark' }: TabsProps) {
  const [activeTabId, setActiveTabId] = useState(tabs[0].id);
  const isLight = variant === 'light';

  return (
    <div className="space-y-4">
      <div className={`flex gap-4 border-b ${isLight ? 'border-stone-200' : 'border-white/10'}`}>
        {tabs.map((tab) => {
          const isActive = activeTabId === tab.id;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTabId(tab.id)}
              className={`pb-2.5 text-xs tracking-wide transition-all relative ${
                isActive
                  ? isLight ? 'text-zinc-900 font-semibold' : 'text-white'
                  : isLight ? 'text-stone-400 hover:text-zinc-900' : 'text-zinc-500 hover:text-zinc-400'
              }`}
            >
              <div className="flex items-center gap-2">
                 {Icon && <Icon className={`w-3.5 h-3.5 ${isActive ? (isLight ? 'text-zinc-900' : 'text-emerald-500') : (isLight ? 'text-stone-400' : 'text-zinc-600')}`} />}
                 <span>{tab.label}</span>
              </div>
              {isActive && (
                <div className={`absolute bottom-0 left-0 right-0 h-0.5 animate-in fade-in slide-in-from-left-4 duration-500 ${isLight ? 'bg-zinc-900' : 'bg-emerald-500'}`} />
              )}
            </button>
          );
        })}
      </div>
      <div className="animate-in fade-in duration-500">
        {children(activeTabId)}
      </div>
    </div>
  );
}
