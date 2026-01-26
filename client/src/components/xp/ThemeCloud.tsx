interface Theme {
  theme: string;
  count: number;
  sentiment?: number;
}

interface ThemeCloudProps {
  themes: Theme[];
  maxThemes?: number;
}

export function ThemeCloud({ themes, maxThemes = 20 }: ThemeCloudProps) {
  if (themes.length === 0) {
    return (
      <div className="text-center py-8 text-zinc-500 text-sm">
        No themes detected yet
      </div>
    );
  }

  const sortedThemes = [...themes]
    .sort((a, b) => b.count - a.count)
    .slice(0, maxThemes);

  const maxCount = Math.max(...sortedThemes.map(t => t.count));
  const minCount = Math.min(...sortedThemes.map(t => t.count));
  const countRange = maxCount - minCount || 1;

  const getSizeClass = (count: number) => {
    const normalized = (count - minCount) / countRange;
    if (normalized > 0.75) return 'text-2xl';
    if (normalized > 0.5) return 'text-xl';
    if (normalized > 0.25) return 'text-base';
    return 'text-sm';
  };

  const getColorClass = (sentiment?: number) => {
    if (sentiment === undefined) return 'text-zinc-400';
    if (sentiment > 0.3) return 'text-emerald-400';
    if (sentiment < -0.3) return 'text-red-400';
    return 'text-amber-400';
  };

  return (
    <div className="flex flex-wrap gap-3 items-center justify-center py-4">
      {sortedThemes.map((theme, index) => (
        <span
          key={index}
          className={`
            font-medium transition-all hover:scale-110 cursor-default
            ${getSizeClass(theme.count)}
            ${getColorClass(theme.sentiment)}
          `}
          title={`${theme.theme} (${theme.count} mentions${theme.sentiment !== undefined ? `, sentiment: ${theme.sentiment.toFixed(2)}` : ''})`}
        >
          {theme.theme}
        </span>
      ))}
    </div>
  );
}
