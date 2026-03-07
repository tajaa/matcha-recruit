import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRConsistencyAnalytics as IRConsistencyAnalyticsData } from '../types';
import { ArrowLeft, BarChart3, Shield, Clock, Scale, Info } from 'lucide-react';
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  cardDark: 'bg-zinc-900 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-800',
  cardDarkGhost: 'text-zinc-800',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  labelOnDark: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  barFill: 'bg-zinc-100',
  barTrack: 'bg-zinc-800',
  barFillLight: 'bg-stone-500',
  barTrackLight: 'bg-stone-200',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardDark: 'bg-zinc-800 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-700',
  cardDarkGhost: 'text-zinc-700',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  labelOnDark: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  barFill: 'bg-zinc-100',
  barTrack: 'bg-zinc-800',
  barFillLight: 'bg-zinc-600',
  barTrackLight: 'bg-zinc-800/40',
} as const;

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low'];

function CardInfo({ text }: { text: string }) {
  return (
    <div className="relative group/info ml-auto">
      <button className="text-zinc-600 hover:text-zinc-400 transition-colors">
        <Info size={12} />
      </button>
      <div className="absolute right-0 top-5 w-56 bg-zinc-950 border border-white/10 rounded-xl p-3 text-[11px] text-zinc-400 leading-relaxed z-20 opacity-0 pointer-events-none group-hover/info:opacity-100 group-hover/info:pointer-events-auto transition-opacity shadow-xl">
        {text}
      </div>
    </div>
  );
}

function formatCategory(raw: string): string {
  if (raw === 'osha_report') return 'OSHA Report';
  return raw
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function IRConsistencyAnalytics() {
  const navigate = useNavigate();
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [data, setData] = useState<IRConsistencyAnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    irIncidents
      .getConsistencyAnalytics()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="flex items-center justify-center min-h-[50vh]">
          <div className={`text-xs ${t.textFaint} uppercase tracking-wider animate-pulse`}>Analyzing consistency patterns...</div>
        </div>
      </div>
    );
  }

  if (!data || (data.total_resolved === 0)) {
    return (
      <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="max-w-5xl mx-auto">
          <button
            onClick={() => navigate('/app/ir/dashboard')}
            className={`${t.btnGhost} text-xs uppercase tracking-wider mb-8 flex items-center gap-1 font-bold`}
          >
            <ArrowLeft size={12} /> Dashboard
          </button>
          <div className="text-center py-20">
            <div className={`text-xs ${t.textMuted} font-mono uppercase tracking-wider`}>No resolved incidents to analyze</div>
          </div>
        </div>
      </div>
    );
  }

  const topAction = data.action_distribution[0];
  const maxProbability = topAction?.probability || 1;
  const resolutionEntries = Object.entries(data.avg_resolution_by_action).sort(([, a], [, b]) => a - b);
  const maxResolution = Math.max(...resolutionEntries.map(([, d]) => d), 1);

  const stats = [
    { label: 'Resolved', value: data.total_resolved, sub: 'Total Incidents', icon: Scale },
    { label: 'With Actions', value: data.total_with_actions, sub: `${data.total_resolved ? Math.round((data.total_with_actions / data.total_resolved) * 100) : 0}% documented`, icon: BarChart3 },
    { label: 'Top Action', value: topAction ? formatCategory(topAction.category) : '—', sub: topAction ? `${Math.round(topAction.probability * 100)}% of cases` : '', icon: Shield },
    { label: 'Actions Tracked', value: data.action_distribution.length, sub: 'Distinct Categories', icon: BarChart3 },
  ];

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
      <div className="max-w-5xl mx-auto space-y-6 animate-in fade-in duration-500">
        {/* Header */}
        <div className="flex justify-between items-start mb-12 pb-8">
          <div>
            <button
              onClick={() => navigate('/app/ir/dashboard')}
              className={`${t.btnGhost} text-xs uppercase tracking-wider mb-4 flex items-center gap-1 font-bold`}
            >
              <ArrowLeft size={12} /> Dashboard
            </button>
            <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>
              Consistency Analytics
            </h1>
            <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>Corrective action patterns across resolved incidents</p>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className={`${t.cardDark} p-6 group relative overflow-hidden`}
            >
              <div className={`absolute top-0 right-0 p-3 ${t.cardDarkGhost} group-hover:scale-110 transition-all duration-500`}>
                <stat.icon className="w-10 h-10" strokeWidth={0.5} />
              </div>
              <div className="relative z-10">
                <div className={`${t.labelOnDark} mb-3`}>{stat.label}</div>
                <div className="text-4xl font-light font-mono text-zinc-50 mb-1 tabular-nums truncate">
                  {typeof stat.value === 'number' ? stat.value : <span className="text-2xl">{stat.value}</span>}
                </div>
                <div className={`text-[10px] ${t.textMuted} font-mono`}>{stat.sub}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Overall Action Distribution */}
        {data.action_distribution.length > 0 && (
          <div className={`${t.cardDark} p-6 shadow-lg`}>
            <div className={`${t.labelOnDark} mb-6 flex items-center gap-2`}>
              <BarChart3 size={14} className="text-zinc-500" /> Action Distribution
              <CardInfo text="How often each corrective action category appeared across all resolved incidents. Bars are scaled relative to the most common action. The count on the right shows how many incidents used that action." />
            </div>
            <div className="space-y-3">
              {data.action_distribution.map((action) => (
                <div key={action.category} className="group">
                  <div className="flex justify-between items-baseline mb-1.5">
                    <span className="text-xs text-zinc-400 group-hover:text-zinc-100 transition-colors">
                      {formatCategory(action.category)}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] text-zinc-600 font-mono tabular-nums">
                        {action.weighted_count.toFixed(0)}
                      </span>
                      <span className="text-xs text-zinc-300 font-mono tabular-nums w-10 text-right">
                        {Math.round(action.probability * 100)}%
                      </span>
                    </div>
                  </div>
                  <div className={`h-2 ${t.barTrack} rounded-full overflow-hidden`}>
                    <div
                      className={`h-full ${t.barFill} rounded-full transition-all duration-500`}
                      style={{ width: `${(action.probability / maxProbability) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* By Incident Type + By Severity */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* By Incident Type */}
          {data.by_incident_type.length > 0 && (
            <div className={`${t.cardDark} p-6 shadow-md`}>
              <div className={`${t.labelOnDark} mb-6 flex items-center gap-2`}>
                <Shield size={14} className="text-zinc-500" /> By Incident Type
                <CardInfo text="The most common corrective actions for each incident category. Shows the top 3 actions per type, helping identify whether certain incident types consistently trigger specific responses." />
              </div>
              <div className="space-y-5">
                {data.by_incident_type.map((group) => (
                  <div key={group.incident_type}>
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs text-zinc-300 font-bold uppercase tracking-wider">
                        {TYPE_LABELS[group.incident_type] || group.incident_type}
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 border border-white/5">
                        {group.total}
                      </span>
                    </div>
                    <div className="space-y-1.5">
                      {group.actions.slice(0, 3).map((action) => (
                        <div key={action.category} className="flex items-center gap-2">
                          <div className={`flex-1 h-1 ${isLight ? t.barTrackLight : 'bg-zinc-700/50'} rounded-full overflow-hidden`}>
                            <div
                              className={`h-full ${isLight ? t.barFillLight : 'bg-zinc-400'} rounded-full`}
                              style={{ width: `${action.probability * 100}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-zinc-500 w-24 truncate">{formatCategory(action.category)}</span>
                          <span className="text-[10px] text-zinc-600 font-mono tabular-nums w-8 text-right">
                            {Math.round(action.probability * 100)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* By Severity */}
          {data.by_severity.length > 0 && (
            <div className={`${t.cardDark} p-6 shadow-md`}>
              <div className={`${t.labelOnDark} mb-6 flex items-center gap-2`}>
                <Shield size={14} className="text-zinc-500" /> By Severity
                <CardInfo text="How corrective actions vary by incident severity. Reveals whether serious incidents (critical/high) receive consistently stronger responses than lower-severity ones." />
              </div>
              <div className="space-y-5">
                {SEVERITY_ORDER.map((sev) => {
                  const group = data.by_severity.find((g) => g.severity === sev);
                  if (!group) return null;
                  return (
                    <div key={sev}>
                      <div className="flex justify-between items-center mb-2">
                        <div className="flex items-center gap-2">
                          <div className={`w-1.5 h-1.5 rounded-full ${
                            sev === 'critical' ? 'bg-zinc-100' :
                            sev === 'high' ? 'bg-zinc-400' :
                            sev === 'medium' ? 'bg-zinc-500' : 'bg-zinc-600'
                          }`} />
                          <span className="text-xs text-zinc-300 font-bold uppercase tracking-wider capitalize">{sev}</span>
                        </div>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 border border-white/5">
                          {group.total}
                        </span>
                      </div>
                      <div className="space-y-1.5">
                        {group.actions.slice(0, 3).map((action) => (
                          <div key={action.category} className="flex items-center gap-2">
                            <div className={`flex-1 h-1 ${isLight ? t.barTrackLight : 'bg-zinc-700/50'} rounded-full overflow-hidden`}>
                              <div
                                className={`h-full ${isLight ? t.barFillLight : 'bg-zinc-400'} rounded-full`}
                                style={{ width: `${action.probability * 100}%` }}
                              />
                            </div>
                            <span className="text-[10px] text-zinc-500 w-24 truncate">{formatCategory(action.category)}</span>
                            <span className="text-[10px] text-zinc-600 font-mono tabular-nums w-8 text-right">
                              {Math.round(action.probability * 100)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Resolution by Action */}
        {resolutionEntries.length > 0 && (
          <div className={`${t.cardDark} p-6 shadow-lg`}>
            <div className={`${t.labelOnDark} mb-6 flex items-center gap-2`}>
              <Clock size={14} className="text-zinc-500" /> Avg Resolution by Action
              <CardInfo text="Average days from incident occurrence to resolution, grouped by the corrective action taken. Shorter bars indicate faster resolution. Useful for understanding which actions close incidents quickly vs. those involving longer processes." />
            </div>
            <div className="space-y-3">
              {resolutionEntries.map(([category, days]) => (
                <div key={category} className="group">
                  <div className="flex justify-between items-baseline mb-1.5">
                    <span className="text-xs text-zinc-400 group-hover:text-zinc-100 transition-colors">
                      {formatCategory(category)}
                    </span>
                    <span className="text-xs text-zinc-300 font-mono tabular-nums">
                      {days.toFixed(1)}d
                    </span>
                  </div>
                  <div className={`h-2 ${t.barTrack} rounded-full overflow-hidden`}>
                    <div
                      className={`h-full ${t.barFill} rounded-full transition-all duration-500`}
                      style={{ width: `${(days / maxResolution) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default IRConsistencyAnalytics;
