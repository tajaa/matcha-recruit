type Period = 'week' | 'month' | 'quarter';

interface PeriodSelectorProps {
  selected: Period;
  onChange: (period: Period) => void;
}

const periods: { value: Period; label: string }[] = [
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
];

export function PeriodSelector({ selected, onChange }: PeriodSelectorProps) {
  return (
    <div className="inline-flex border border-white/10 rounded overflow-hidden">
      {periods.map((period) => (
        <button
          key={period.value}
          onClick={() => onChange(period.value)}
          className={`
            px-4 py-2 text-xs font-mono uppercase tracking-wider transition-colors
            ${selected === period.value
              ? 'bg-white text-black font-bold'
              : 'bg-transparent text-zinc-400 hover:text-white hover:bg-white/5'
            }
          `}
        >
          {period.label}
        </button>
      ))}
    </div>
  );
}
