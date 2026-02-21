import { useState, type ReactNode } from 'react';

interface Tab {
  id: string;
  label: string;
  icon?: React.ElementType;
}

interface TabsProps {
  tabs: Tab[];
  children: (activeTabId: string) => ReactNode;
}

export function Tabs({ tabs, children }: TabsProps) {
  const [activeTabId, setActiveTabId] = useState(tabs[0].id);

  return (
    <div className="space-y-8">
      <div className="flex border-b border-white/10 gap-8">
        {tabs.map((tab) => {
          const isActive = activeTabId === tab.id;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTabId(tab.id)}
              className={`pb-4 text-[10px] uppercase tracking-[0.2em] transition-all relative ${
                isActive ? 'text-white' : 'text-zinc-500 hover:text-zinc-400'
              }`}
            >
              <div className="flex items-center gap-2">
                 {Icon && <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-emerald-500' : 'text-zinc-600'}`} />}
                 <span>{tab.label}</span>
              </div>
              {isActive && (
                <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 animate-in fade-in slide-in-from-left-4 duration-500" />
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
