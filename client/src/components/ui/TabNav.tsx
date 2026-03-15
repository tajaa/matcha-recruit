interface Tab { value: string; label: string; }

interface TabNavProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (value: string) => void;
  className?: string;
}

export function TabNav({ tabs, activeTab, onTabChange, className = '' }: TabNavProps) {
  return (
    <div className={`border-b border-zinc-200 ${className}`}>
      <nav className="-mb-px flex gap-6 overflow-x-auto no-scrollbar">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => onTabChange(tab.value)}
            className={`pb-3 text-sm border-b-2 whitespace-nowrap ${activeTab === tab.value ? 'border-zinc-800 text-zinc-800 font-medium' : 'border-transparent text-zinc-400 hover:text-zinc-600'}`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
