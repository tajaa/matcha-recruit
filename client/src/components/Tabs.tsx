import { useState, type ReactNode } from 'react';

interface Tab {
  id: string;
  label: string;
  icon?: React.ElementType;
  count?: number;
  badge?: boolean;
}

interface TabsProps {
  tabs: Tab[];
  children: (activeTabId: string) => ReactNode;
  variant?: 'dark' | 'light';
  /** Controlled mode — pass current tab id */
  activeTab?: string;
  /** Controlled mode — called when tab changes */
  onTabChange?: (id: string) => void;
  /** Extra controls rendered to the right of tabs (filters, toggles) */
  controls?: ReactNode;
  className?: string;
}

export function Tabs({ tabs, children, variant = 'dark', activeTab, onTabChange, controls, className = '' }: TabsProps) {
  const [internalTab, setInternalTab] = useState(tabs[0].id);
  const currentTab = activeTab ?? internalTab;
  const setTab = onTabChange ?? setInternalTab;
  const isLight = variant === 'light';

  return (
    <div className={`space-y-3.5 ${className}`}>
      <div className={`flex items-center gap-3 border-b ${isLight ? 'border-stone-200' : 'border-white/10'}`}>
        {tabs.map((tab) => {
          const isActive = currentTab === tab.id;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setTab(tab.id)}
              className={`pb-2 text-xs tracking-wide transition-all relative ${
                isActive
                  ? isLight ? 'text-zinc-900 font-semibold' : 'text-white'
                  : isLight ? 'text-stone-400 hover:text-zinc-900' : 'text-zinc-500 hover:text-zinc-400'
              }`}
            >
              <div className="flex items-center gap-1.5">
                 {Icon && <Icon className={`w-3 h-3 ${isActive ? (isLight ? 'text-zinc-900' : 'text-emerald-500') : (isLight ? 'text-stone-400' : 'text-zinc-600')}`} />}
                 <span className="text-[11px]">{tab.label}</span>
                 {tab.count !== undefined && (
                   <span className={`text-[9px] font-mono ${isActive ? 'opacity-50' : 'opacity-30'}`}>
                     [{tab.count}]
                   </span>
                 )}
                 {tab.badge && (
                   <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                 )}
              </div>
              {isActive && (
                <div className={`absolute bottom-0 left-0 right-0 h-0.5 animate-in fade-in slide-in-from-left-4 duration-500 ${isLight ? 'bg-zinc-900' : 'bg-emerald-500'}`} />
              )}
            </button>
          );
        })}
        {controls && <div className="ml-auto flex items-center gap-1.5">{controls}</div>}
      </div>
      <div className="animate-in fade-in duration-500">
        {children(currentTab)}
      </div>
    </div>
  );
}
