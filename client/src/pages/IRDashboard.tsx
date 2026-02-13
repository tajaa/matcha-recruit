import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRAnalyticsSummary, IRTrendsAnalysis, IRLocationAnalysis, IRIncident } from '../types';
import { Plus, ArrowRight, Activity, MapPin, ShieldAlert } from 'lucide-react';

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-emerald-500',
};

const STATUS_COLORS: Record<string, string> = {
  reported: 'text-blue-400',
  investigating: 'text-amber-400',
  action_required: 'text-orange-400',
  resolved: 'text-emerald-400',
  closed: 'text-zinc-500',
};

export function IRDashboard() {
  const navigate = useNavigate();
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
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading analytics...</div>
      </div>
    );
  }

  const openCount = (summary?.by_status?.reported || 0) +
    (summary?.by_status?.investigating || 0) +
    (summary?.by_status?.action_required || 0);

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Incidents</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Workplace incident tracking</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/app/ir')}
            className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider transition-colors px-4 py-2 border border-white/10"
          >
            View All
          </button>
          <button
            onClick={() => navigate('/app/ir/incidents/new')}
            className="flex items-center gap-2 px-4 py-2 bg-white text-black text-xs font-bold hover:bg-zinc-200 uppercase tracking-wider transition-colors"
          >
            <Plus size={14} /> Report
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-px bg-white/10 border border-white/10">
        <div className="bg-zinc-950 p-6">
          <div className="text-3xl font-light text-white font-mono">{summary?.total_incidents || 0}</div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-2 font-bold">Total</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-3xl font-light text-white font-mono">{summary?.recent_count || 0}</div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-2 font-bold">Last 30d</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-3xl font-light text-white font-mono">{openCount}</div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-2 font-bold">Open</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-3xl font-light text-white font-mono">
            {summary?.avg_resolution_days ? `${summary.avg_resolution_days}d` : '—'}
          </div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest mt-2 font-bold">Avg Resolution</div>
        </div>
      </div>

      {/* Trend Chart */}
      {trends && trends.data.length > 0 && (
        <div className="bg-zinc-900 border border-white/10 p-6">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-6 font-bold flex items-center gap-2">
             <Activity size={14} /> Weekly Trend
          </div>
          <div className="flex items-end gap-1 h-32">
            {trends.data.map((point, idx) => {
              const maxCount = Math.max(...trends.data.map((d) => d.count), 1);
              const height = (point.count / maxCount) * 100;
              return (
                <div
                  key={idx}
                  className="flex-1 bg-zinc-800 hover:bg-white transition-colors cursor-crosshair group relative"
                  style={{ height: `${Math.max(height, 2)}%` }}
                >
                   <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-white text-black text-[10px] font-bold px-2 py-1 z-10 whitespace-nowrap">
                      {point.count} Incidents • {point.date}
                   </div>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-[9px] text-zinc-600 mt-3 font-mono uppercase">
            <span>{trends.start_date}</span>
            <span>{trends.end_date}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* By Type */}
        <div className="bg-zinc-950 border border-white/10 p-6">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-6 font-bold flex items-center gap-2">
             <ShieldAlert size={14} /> By Type
          </div>
          {summary && Object.keys(summary.by_type).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(summary.by_type).map(([type, count]) => (
                <div key={type} className="flex justify-between items-center group">
                  <span className="text-xs text-zinc-400 group-hover:text-white transition-colors">{TYPE_LABELS[type] || type}</span>
                  <span className="text-xs text-white font-mono bg-zinc-900 px-2 py-0.5 border border-zinc-800">{count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-zinc-600 font-mono">No data available</div>
          )}
        </div>

        {/* By Severity */}
        <div className="bg-zinc-950 border border-white/10 p-6">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-6 font-bold flex items-center gap-2">
             <ShieldAlert size={14} /> By Severity
          </div>
          {summary && Object.keys(summary.by_severity).length > 0 ? (
            <div className="space-y-3">
              {['critical', 'high', 'medium', 'low'].map((severity) => {
                const count = summary.by_severity[severity] || 0;
                if (count === 0) return null;
                return (
                  <div key={severity} className="flex justify-between items-center group">
                    <div className="flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full ${SEVERITY_COLORS[severity]}`} />
                      <span className="text-xs text-zinc-400 capitalize group-hover:text-white transition-colors">{severity}</span>
                    </div>
                    <span className="text-xs text-white font-mono bg-zinc-900 px-2 py-0.5 border border-zinc-800">{count}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-xs text-zinc-600 font-mono">No data available</div>
          )}
        </div>

        {/* Hotspots */}
        <div className="bg-zinc-950 border border-white/10 p-6">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-6 font-bold flex items-center gap-2">
             <MapPin size={14} /> Hotspots
          </div>
          {locations && locations.hotspots.length > 0 ? (
            <div className="space-y-3">
              {locations.hotspots.slice(0, 4).map((hotspot, idx) => (
                <div key={idx} className="flex justify-between items-center group">
                  <span className="text-xs text-zinc-400 truncate max-w-[120px] group-hover:text-white transition-colors">{hotspot.location}</span>
                  <span className="text-xs text-white font-mono bg-zinc-900 px-2 py-0.5 border border-zinc-800">{hotspot.count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-zinc-600 font-mono">No data available</div>
          )}
        </div>
      </div>

      {/* Recent Incidents */}
      <div className="space-y-px bg-white/10 border border-white/10">
        <div className="flex justify-between items-center p-4 bg-zinc-950 border-b border-white/10">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Recent Incidents</div>
          <button
            onClick={() => navigate('/app/ir')}
            className="text-[10px] text-zinc-500 hover:text-white uppercase tracking-wider transition-colors flex items-center gap-1"
          >
            All <ArrowRight size={10} />
          </button>
        </div>
        {recentIncidents.length > 0 ? (
          recentIncidents.map((incident) => (
            <div
              key={incident.id}
              onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
              className="flex items-center gap-4 p-4 bg-zinc-950 hover:bg-zinc-900 cursor-pointer group transition-colors"
            >
              <div className={`w-1.5 h-1.5 rounded-full ${SEVERITY_COLORS[incident.severity]}`} />
              <span className="text-[10px] text-zinc-500 font-mono w-24 group-hover:text-zinc-400">{incident.incident_number}</span>
              <span className="text-xs text-zinc-300 flex-1 truncate group-hover:text-white transition-colors font-bold">
                {incident.title}
              </span>
              <span className={`text-[10px] font-bold uppercase tracking-wider ${STATUS_COLORS[incident.status]}`}>
                {incident.status.replace('_', ' ')}
              </span>
              <span className="text-[10px] text-zinc-600 w-16 text-right font-mono">{formatDate(incident.occurred_at)}</span>
            </div>
          ))
        ) : (
          <div className="text-center py-12 bg-zinc-950">
            <div className="text-xs text-zinc-500 mb-3 font-mono uppercase tracking-wider">No incidents reported</div>
            <button
              onClick={() => navigate('/app/ir/incidents/new')}
              className="text-xs text-white hover:text-zinc-300 uppercase tracking-wider transition-colors font-bold underline underline-offset-4"
            >
              Report First Incident
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default IRDashboard;
