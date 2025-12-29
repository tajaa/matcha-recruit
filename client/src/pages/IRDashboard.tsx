import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { irIncidents } from '../api/client';
import type { IRAnalyticsSummary, IRTrendsAnalysis, IRLocationAnalysis, IRIncident } from '../types';

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-600',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
};

const STATUS_COLORS: Record<string, string> = {
  reported: 'text-blue-400',
  investigating: 'text-yellow-400',
  action_required: 'text-orange-400',
  resolved: 'text-green-400',
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
        <div className="text-xs text-zinc-600 uppercase tracking-wider">Loading...</div>
      </div>
    );
  }

  const openCount = (summary?.by_status?.reported || 0) +
    (summary?.by_status?.investigating || 0) +
    (summary?.by_status?.action_required || 0);

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-12">
        <div>
          <h1 className="text-xl font-medium text-white">Incidents</h1>
          <p className="text-xs text-zinc-600 mt-1">Workplace incident tracking</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => navigate('/app/ir/incidents')}
            className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider"
          >
            View All
          </button>
          <button
            onClick={() => navigate('/app/ir/incidents/new')}
            className="px-3 py-1.5 bg-white text-black text-xs font-medium rounded hover:bg-zinc-200 uppercase tracking-wider"
          >
            Report
          </button>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-8 mb-12">
        <div>
          <div className="text-3xl font-light text-white">{summary?.total_incidents || 0}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-1">Total</div>
        </div>
        <div>
          <div className="text-3xl font-light text-white">{summary?.recent_count || 0}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-1">Last 30d</div>
        </div>
        <div>
          <div className="text-3xl font-light text-white">{openCount}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-1">Open</div>
        </div>
        <div>
          <div className="text-3xl font-light text-white">
            {summary?.avg_resolution_days ? `${summary.avg_resolution_days}d` : '—'}
          </div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mt-1">Avg Resolution</div>
        </div>
      </div>

      {/* Trend Chart */}
      {trends && trends.data.length > 0 && (
        <div className="mb-12">
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-4">Weekly Trend</div>
          <div className="flex items-end gap-px h-16">
            {trends.data.map((point, idx) => {
              const maxCount = Math.max(...trends.data.map((d) => d.count), 1);
              const height = (point.count / maxCount) * 100;
              return (
                <div
                  key={idx}
                  className="flex-1 bg-zinc-800 hover:bg-zinc-700 transition-colors"
                  style={{ height: `${Math.max(height, 2)}%` }}
                  title={`${point.date}: ${point.count}`}
                />
              );
            })}
          </div>
          <div className="flex justify-between text-[10px] text-zinc-700 mt-2">
            <span>{trends.start_date}</span>
            <span>{trends.end_date}</span>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-12">
        {/* By Type */}
        <div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-4">By Type</div>
          {summary && Object.keys(summary.by_type).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(summary.by_type).map(([type, count]) => (
                <div key={type} className="flex justify-between items-center">
                  <span className="text-xs text-zinc-400">{TYPE_LABELS[type] || type}</span>
                  <span className="text-xs text-white font-medium">{count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-zinc-700">No data</div>
          )}
        </div>

        {/* By Severity */}
        <div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-4">By Severity</div>
          {summary && Object.keys(summary.by_severity).length > 0 ? (
            <div className="space-y-2">
              {['critical', 'high', 'medium', 'low'].map((severity) => {
                const count = summary.by_severity[severity] || 0;
                if (count === 0) return null;
                return (
                  <div key={severity} className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${SEVERITY_COLORS[severity]}`} />
                      <span className="text-xs text-zinc-400 capitalize">{severity}</span>
                    </div>
                    <span className="text-xs text-white font-medium">{count}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-xs text-zinc-700">No data</div>
          )}
        </div>

        {/* Hotspots */}
        <div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider mb-4">Hotspots</div>
          {locations && locations.hotspots.length > 0 ? (
            <div className="space-y-2">
              {locations.hotspots.slice(0, 4).map((hotspot, idx) => (
                <div key={idx} className="flex justify-between items-center">
                  <span className="text-xs text-zinc-400 truncate max-w-[120px]">{hotspot.location}</span>
                  <span className="text-xs text-white font-medium">{hotspot.count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-zinc-700">No data</div>
          )}
        </div>
      </div>

      {/* Recent Incidents */}
      <div className="mt-12 pt-8 border-t border-zinc-900">
        <div className="flex justify-between items-center mb-4">
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider">Recent</div>
          <button
            onClick={() => navigate('/app/ir/incidents')}
            className="text-[10px] text-zinc-600 hover:text-white uppercase tracking-wider"
          >
            All
          </button>
        </div>
        {recentIncidents.length > 0 ? (
          <div className="space-y-3">
            {recentIncidents.map((incident) => (
              <div
                key={incident.id}
                onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
                className="flex items-center gap-4 py-2 cursor-pointer group"
              >
                <div className={`w-1.5 h-1.5 rounded-full ${SEVERITY_COLORS[incident.severity]}`} />
                <span className="text-[10px] text-zinc-600 font-mono w-24">{incident.incident_number}</span>
                <span className="text-xs text-zinc-300 flex-1 truncate group-hover:text-white transition-colors">
                  {incident.title}
                </span>
                <span className={`text-[10px] ${STATUS_COLORS[incident.status]}`}>
                  {incident.status.replace('_', ' ')}
                </span>
                <span className="text-[10px] text-zinc-600 w-16 text-right">{formatDate(incident.occurred_at)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <div className="text-xs text-zinc-600 mb-3">No incidents reported</div>
            <button
              onClick={() => navigate('/app/ir/incidents/new')}
              className="text-xs text-zinc-500 hover:text-white uppercase tracking-wider"
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
