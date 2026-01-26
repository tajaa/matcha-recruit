import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon?: LucideIcon;
  color?: string;
  trend?: 'up' | 'down' | 'neutral';
}

export function StatCard({ label, value, subtext, icon: Icon, color = 'text-white', trend }: StatCardProps) {
  const trendColors = {
    up: 'text-emerald-400',
    down: 'text-red-400',
    neutral: 'text-zinc-500',
  };

  return (
    <div className="bg-zinc-900/30 border border-white/10 p-6 hover:bg-zinc-900/50 transition-colors group relative overflow-hidden">
      {Icon && (
        <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 group-hover:scale-110 transition-all duration-500">
          <Icon className="w-20 h-20 text-white" strokeWidth={0.5} />
        </div>
      )}

      <div className="relative z-10">
        <div className="flex items-center gap-3 mb-4">
          {Icon && (
            <div className={`p-2 rounded bg-white/5 ${color}`}>
              <Icon className="w-4 h-4" />
            </div>
          )}
          <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">{label}</span>
        </div>

        <div className={`text-3xl font-light mb-2 tabular-nums tracking-tight ${color}`}>
          {value}
        </div>

        {subtext && (
          <div className={`flex items-center gap-2 text-[10px] font-mono uppercase ${trend ? trendColors[trend] : 'text-zinc-400'}`}>
            <span className="w-1 h-1 bg-current rounded-full" />
            {subtext}
          </div>
        )}
      </div>
    </div>
  );
}
