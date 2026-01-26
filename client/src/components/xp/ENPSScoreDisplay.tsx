interface ENPSScoreDisplayProps {
  score: number;
  promoters: number;
  passives: number;
  detractors: number;
  totalResponses: number;
  size?: 'sm' | 'md' | 'lg';
}

export function ENPSScoreDisplay({
  score,
  promoters,
  passives,
  detractors,
  totalResponses,
  size = 'md',
}: ENPSScoreDisplayProps) {
  const getScoreColor = (score: number) => {
    if (score >= 50) return 'text-emerald-400';
    if (score >= 0) return 'text-amber-400';
    return 'text-red-400';
  };

  const getScoreLabel = (score: number) => {
    if (score >= 50) return 'Excellent';
    if (score >= 20) return 'Good';
    if (score >= 0) return 'Okay';
    if (score >= -20) return 'Needs Work';
    return 'Critical';
  };

  const getScoreBgColor = (score: number) => {
    if (score >= 50) return 'bg-emerald-500/10 border-emerald-500/20';
    if (score >= 0) return 'bg-amber-500/10 border-amber-500/20';
    return 'bg-red-500/10 border-red-500/20';
  };

  const sizeClasses = {
    sm: 'text-3xl',
    md: 'text-5xl',
    lg: 'text-7xl',
  };

  const total = promoters + passives + detractors;
  const promoterPct = total > 0 ? Math.round((promoters / total) * 100) : 0;
  const passivePct = total > 0 ? Math.round((passives / total) * 100) : 0;
  const detractorPct = total > 0 ? Math.round((detractors / total) * 100) : 0;

  return (
    <div className={`p-6 border rounded ${getScoreBgColor(score)}`}>
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">eNPS Score</div>
          <div className={`${sizeClasses[size]} font-bold tabular-nums tracking-tighter ${getScoreColor(score)}`}>
            {score > 0 ? '+' : ''}{score}
          </div>
          <div className={`text-sm mt-1 ${getScoreColor(score)}`}>
            {getScoreLabel(score)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Responses</div>
          <div className="text-2xl font-light text-white tabular-nums">{totalResponses}</div>
        </div>
      </div>

      {/* Breakdown Bar */}
      <div className="space-y-3">
        <div className="h-3 rounded-full overflow-hidden flex bg-zinc-800">
          {promoterPct > 0 && (
            <div
              className="bg-emerald-500 transition-all duration-500"
              style={{ width: `${promoterPct}%` }}
            />
          )}
          {passivePct > 0 && (
            <div
              className="bg-amber-500 transition-all duration-500"
              style={{ width: `${passivePct}%` }}
            />
          )}
          {detractorPct > 0 && (
            <div
              className="bg-red-500 transition-all duration-500"
              style={{ width: `${detractorPct}%` }}
            />
          )}
        </div>

        {/* Legend */}
        <div className="grid grid-cols-3 gap-4 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-emerald-500" />
            <div>
              <div className="text-zinc-400">Promoters</div>
              <div className="text-white font-medium">{promoters} ({promoterPct}%)</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-amber-500" />
            <div>
              <div className="text-zinc-400">Passives</div>
              <div className="text-white font-medium">{passives} ({passivePct}%)</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-red-500" />
            <div>
              <div className="text-zinc-400">Detractors</div>
              <div className="text-white font-medium">{detractors} ({detractorPct}%)</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
