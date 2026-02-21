import { useState, useEffect, type ReactNode } from 'react';
import { Settings, Eye, EyeOff } from 'lucide-react';

interface Widget {
  id: string;
  label: string;
  icon?: React.ElementType;
}

interface WidgetContainerProps {
  widgets: Widget[];
  children: (visibleWidgets: Set<string>) => ReactNode;
}

export function WidgetContainer({ widgets, children }: WidgetContainerProps) {
  const [isConfiguring, setIsConfiguring] = useState(false);
  const [visibleWidgets, setVisibleWidgets] = useState<Set<string>>(new Set(widgets.map(w => w.id)));

  // Load from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('matcha-dashboard-widgets');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          setVisibleWidgets(new Set(parsed));
        }
      } catch (e) {
        console.error('Failed to parse dashboard widgets from localStorage:', e);
      }
    }
  }, []);

  const toggleWidget = (id: string) => {
    const next = new Set(visibleWidgets);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setVisibleWidgets(next);
    localStorage.setItem('matcha-dashboard-widgets', JSON.stringify(Array.from(next)));
  };

  return (
    <div className="space-y-12">
      <div className="flex justify-between items-center bg-zinc-950 p-4 border border-white/5 rounded-lg shadow-2xl">
        <div className="flex items-center gap-3">
          <div className="p-1.5 bg-emerald-500/10 rounded">
             <Settings className="w-3 h-3 text-emerald-500" />
          </div>
          <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-400 font-bold">Customize Dashboard</span>
        </div>
        <button
          onClick={() => setIsConfiguring(!isConfiguring)}
          className={`px-4 py-1.5 text-[9px] uppercase tracking-[0.2em] font-mono border transition-all ${
            isConfiguring ? 'bg-white text-black border-white' : 'text-zinc-500 border-white/10 hover:border-white/30'
          }`}
        >
          {isConfiguring ? 'Done' : 'Edit Layout'}
        </button>
      </div>

      {isConfiguring && (
        <div className="p-8 bg-zinc-900/50 border border-white/10 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 animate-in slide-in-from-top-2 duration-300">
          {widgets.map((w) => {
            const isVisible = visibleWidgets.has(w.id);
            const Icon = w.icon;
            return (
              <button
                key={w.id}
                onClick={() => toggleWidget(w.id)}
                className={`p-4 flex items-center gap-3 border transition-all group ${
                  isVisible ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-white/5 bg-transparent opacity-50 grayscale'
                }`}
              >
                <div className={`p-2 rounded ${isVisible ? 'bg-emerald-500/20' : 'bg-white/5'}`}>
                   {Icon && <Icon className={`w-3.5 h-3.5 ${isVisible ? 'text-emerald-500' : 'text-zinc-600'}`} />}
                </div>
                <div className="flex-1 text-left">
                   <div className={`text-[10px] uppercase tracking-widest font-bold ${isVisible ? 'text-white' : 'text-zinc-500'}`}>{w.label}</div>
                </div>
                {isVisible ? (
                  <Eye className="w-3 h-3 text-emerald-500 group-hover:scale-110 transition-transform" />
                ) : (
                  <EyeOff className="w-3 h-3 text-zinc-700 group-hover:scale-110 transition-transform" />
                )}
              </button>
            );
          })}
        </div>
      )}

      <div>
        {children(visibleWidgets)}
      </div>
    </div>
  );
}
