interface Tab { value: string; label: string; }

interface TabNavProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (value: string) => void;
  className?: string;
}

export function TabNav({ tabs, activeTab, onTabChange, className = '' }: TabNavProps) {
  return (
    <div className={`border-b border-stone-200 ${className}`}>
      <nav className="-mb-px flex gap-6 overflow-x-auto no-scrollbar">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => onTabChange(tab.value)}
            className={`pb-3 text-sm border-b-2 whitespace-nowrap ${activeTab === tab.value ? 'border-zinc-900 text-zinc-900 font-medium' : 'border-transparent text-stone-500 hover:text-stone-700'}`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
