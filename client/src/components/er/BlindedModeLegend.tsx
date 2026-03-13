interface LegendEntry {
  pseudonym: string;
  role: string;
}

interface Props {
  legend: LegendEntry[];
  t: {
    cardInner: string;
    textMain: string;
    textMuted: string;
    border: string;
  };
}

export function BlindedModeLegend({ legend, t }: Props) {
  return (
    <div className={`flex items-center gap-4 flex-wrap px-3 py-2 ${t.cardInner} border ${t.border} rounded-lg`}>
      <span className={`text-[10px] ${t.textMuted} uppercase tracking-widest`}>Legend</span>
      {legend.map((entry) => (
        <span key={entry.pseudonym} className={`text-[11px] ${t.textMain}`}>
          <span className="font-semibold">{entry.pseudonym}</span>
          <span className={`${t.textMuted} ml-1`}>— {entry.role}</span>
        </span>
      ))}
    </div>
  );
}
