import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRAnalyticsSummary, IRTrendsAnalysis, IRLocationAnalysis, IRIncident } from '../types';
import { Plus, ArrowRight, Activity, MapPin, ShieldAlert, ChevronRight } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  cardDark: 'bg-stone-200 rounded-2xl',
  statBg: 'bg-stone-200',
  statGap: 'bg-stone-300',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-xl',
  rowHover: 'hover:bg-stone-50',
  barBg: 'bg-stone-300',
  barHover: 'hover:bg-zinc-900',
  tooltipBg: 'bg-zinc-900 text-zinc-50',
  icon: 'text-stone-400',
  countBadge: 'bg-stone-200 text-zinc-900 border border-stone-300',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardDark: 'bg-zinc-900 rounded-2xl',
  statBg: 'bg-zinc-900',
  statGap: 'bg-zinc-950',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100 rounded-xl',
  rowHover: 'hover:bg-white/5',
  barBg: 'bg-zinc-800',
  barHover: 'hover:bg-white',
  tooltipBg: 'bg-white text-black',
  icon: 'text-zinc-600',
  countBadge: 'bg-zinc-800 text-zinc-100 border border-zinc-700',
} as const;

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const SEVERITY_DOTS: Record<string, string> = {
  critical: 'bg-zinc-100',
  high: 'bg-zinc-400',
  medium: 'bg-zinc-500',
  low: 'bg-zinc-600',
};

const SEVERITY_DOTS_LIGHT: Record<string, string> = {
  critical: 'bg-zinc-900',
  high: 'bg-stone-600',
  medium: 'bg-stone-400',
  low: 'bg-stone-300',
};

const STATUS_COLORS: Record<string, string> = {
  reported: 'text-zinc-100',
  investigating: 'text-zinc-400',
  action_required: 'text-zinc-300',
  resolved: 'text-zinc-500',
  closed: 'text-zinc-600',
};

const STATUS_COLORS_LIGHT: Record<string, string> = {
  reported: 'text-zinc-900',
  investigating: 'text-stone-600',
  action_required: 'text-stone-500',
  resolved: 'text-stone-400',
  closed: 'text-stone-300',
};

export function IRDashboard() {
  const navigate = useNavigate();
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const sevDots = isLight ? SEVERITY_DOTS_LIGHT : SEVERITY_DOTS;
  const statusColors = isLight ? STATUS_COLORS_LIGHT : STATUS_COLORS;
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<IRAnalyticsSummary | null>(null);
  const [trends, setTrends] = useState<IRTrendsAnalysis | null>(null);
  const [locations, setLocations] = useState<IRLocationAnalysis | null>(null);
  const [recentIncidents, setRecentIncidents] = useState<IRIncident[]>([]);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const [summaryData, trendsData, locationsData, incidentsData] = await Promise.all([
          irIncidents.getAnalyticsSummary(),
          irIncidents.getAnalyticsTrends('weekly', 90),
          irIncidents.getAnalyticsLocations(5),
          irIncidents.listIncidents({ limit: 5 }),
        ]);
        setSummary(summaryData);
        setTrends(trendsData);
        setLocations(locationsData);
        setRecentIncidents(incidentsData.incidents);
      } catch (err) {
        console.error('Failed to fetch dashboard data:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className={`text-xs ${t.textFaint} uppercase tracking-wider animate-pulse`}>Loading analytics...</div>
      </div>
    );
  }

  const openCount = (summary?.by_status?.reported || 0) +
    (summary?.by_status?.investigating || 0) +
    (summary?.by_status?.action_required || 0);

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex justify-between items-start mb-12 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>Incidents</h1>
            <FeatureGuideTrigger guideId="ir-dashboard" />
          </div>
          <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase`}>Workplace incident tracking</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/app/ir')}
            className={`text-xs uppercase tracking-wider transition-colors px-5 py-2 font-bold ${t.btnSecondary}`}
          >
            View All
          </button>
          <button
            onClick={() => navigate('/app/ir/incidents/new')}
            className={`flex items-center gap-2 px-5 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${t.btnPrimary}`}
          >
            <Plus size={14} /> Report
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div data-tour="ir-dash-stats" className={`grid grid-cols-4 gap-px ${t.statGap} rounded-2xl overflow-hidden`}>
        {[
          { label: 'Total', value: summary?.total_incidents || 0 },
          { label: 'Last 30d', value: summary?.recent_count || 0 },
          { label: 'Open', value: openCount },
          { label: 'Avg Resolution', value: summary?.avg_resolution_days ? `${summary.avg_resolution_days}d` : '—' },
        ].map((stat) => (
          <div key={stat.label} className={`${t.statBg} p-6`}>
            <div className={`text-3xl font-light ${t.textMain} font-mono tabular-nums`}>{stat.value}</div>
            <div className={`${t.label} mt-2`}>{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Trend Chart */}
      {trends && trends.data.length > 0 && (
        <div data-tour="ir-dash-trend" className={`${t.card} p-6`}>
          <div className={`${t.label} mb-6 flex items-center gap-2`}>
             <Activity size={14} className={t.icon} /> Weekly Trend
          </div>
          <div className="flex items-end gap-1 h-32">
            {trends.data.map((point, idx) => {
              const maxCount = Math.max(...trends.data.map((d) => d.count), 1);
              const height = (point.count / maxCount) * 100;
              return (
                <div
                  key={idx}
                  className={`flex-1 ${t.barBg} ${t.barHover} transition-colors cursor-crosshair group relative rounded-sm`}
                  style={{ height: `${Math.max(height, 2)}%` }}
                >
                   <div className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block ${t.tooltipBg} text-[10px] font-bold px-2 py-1 rounded-lg z-10 whitespace-nowrap`}>
                      {point.count} Incidents • {point.date}
                   </div>
                </div>
              );
            })}
          </div>
          <div className={`flex justify-between text-[9px] ${t.textFaint} mt-3 font-mono uppercase`}>
            <span>{trends.start_date}</span>
            <span>{trends.end_date}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* By Type */}
        <div data-tour="ir-dash-by-type" className={`${t.card} p-6`}>
          <div className={`${t.label} mb-6 flex items-center gap-2`}>
             <ShieldAlert size={14} className={t.icon} /> By Type
          </div>
          {summary && Object.keys(summary.by_type).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(summary.by_type).map(([type, count]) => (
                <div key={type} className="flex justify-between items-center group">
                  <span className={`text-xs ${t.textMuted} group-hover:${t.textMain} transition-colors`}>{TYPE_LABELS[type] || type}</span>
                  <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${t.countBadge}`}>{count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className={`text-xs ${t.textFaint} font-mono`}>No data available</div>
          )}
        </div>

        {/* By Severity */}
        <div data-tour="ir-dash-by-severity" className={`${t.card} p-6`}>
          <div className={`${t.label} mb-6 flex items-center gap-2`}>
             <ShieldAlert size={14} className={t.icon} /> By Severity
          </div>
          {summary && Object.keys(summary.by_severity).length > 0 ? (
            <div className="space-y-3">
              {['critical', 'high', 'medium', 'low'].map((severity) => {
                const count = summary.by_severity[severity] || 0;
                if (count === 0) return null;
                return (
                  <div key={severity} className="flex justify-between items-center group">
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full ${sevDots[severity]}`} />
                      <span className={`text-xs ${t.textMuted} capitalize group-hover:${t.textMain} transition-colors`}>{severity}</span>
                    </div>
                    <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${t.countBadge}`}>{count}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className={`text-xs ${t.textFaint} font-mono`}>No data available</div>
          )}
        </div>

        {/* Hotspots */}
        <div data-tour="ir-dash-hotspots" className={`${t.card} p-6`}>
          <div className={`${t.label} mb-6 flex items-center gap-2`}>
             <MapPin size={14} className={t.icon} /> Hotspots
          </div>
          {locations && locations.hotspots.length > 0 ? (
            <div className="space-y-3">
              {locations.hotspots.slice(0, 4).map((hotspot, idx) => (
                <div key={idx} className="flex justify-between items-center group">
                  <span className={`text-xs ${t.textMuted} truncate max-w-[120px] group-hover:${t.textMain} transition-colors`}>{hotspot.location}</span>
                  <span className={`text-xs font-mono px-2 py-0.5 rounded-full ${t.countBadge}`}>{hotspot.count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className={`text-xs ${t.textFaint} font-mono`}>No data available</div>
          )}
        </div>
      </div>

      {/* Recent Incidents */}
      <div data-tour="ir-dash-recent" className={`${t.cardDark} overflow-hidden`}>
        <div className={`flex justify-between items-center p-4 border-b ${t.border}`}>
          <div className={t.label}>Recent Incidents</div>
          <button
            onClick={() => navigate('/app/ir')}
            className={`text-[10px] ${t.textMuted} hover:text-zinc-100 uppercase tracking-wider transition-colors flex items-center gap-1`}
          >
            All <ArrowRight size={10} />
          </button>
        </div>
        {recentIncidents.length > 0 ? (
          <div className="divide-y divide-zinc-800">
          {recentIncidents.map((incident) => (
            <div
              key={incident.id}
              onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
              className="flex items-center gap-4 p-4 hover:bg-white/5 cursor-pointer group transition-colors"
            >
              <div className={`w-1.5 h-1.5 rounded-full ${sevDots[incident.severity]}`} />
              <span className="text-[10px] text-zinc-500 font-mono w-24 group-hover:text-zinc-400">{incident.incident_number}</span>
              <span className="text-xs text-zinc-300 flex-1 truncate group-hover:text-white transition-colors font-bold">
                {incident.title}
              </span>
              <span className={`text-[10px] font-bold uppercase tracking-wider ${statusColors[incident.status]}`}>
                {incident.status.replace('_', ' ')}
              </span>
              <span className="text-[10px] text-zinc-600 w-16 text-right font-mono">{formatDate(incident.occurred_at)}</span>
              <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400" />
            </div>
          ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className={`text-xs ${t.textMuted} mb-3 font-mono uppercase tracking-wider`}>No incidents reported</div>
            <button
              onClick={() => navigate('/app/ir/incidents/new')}
              className={`text-xs ${t.textMain} font-bold uppercase tracking-wider underline underline-offset-4`}
            >
              Report First Incident
            </button>
          </div>
        )}
      </div>
    </div>
    </div>
  );
}

export default IRDashboard;
