import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent } from '../components';
import { irIncidents } from '../api/client';
import type { IRAnalyticsSummary, IRTrendsAnalysis, IRLocationAnalysis, IRIncident } from '../types';

const TYPE_LABELS: Record<string, string> = {
  safety: 'Safety',
  behavioral: 'Behavioral',
  property: 'Property',
  near_miss: 'Near Miss',
  other: 'Other',
};

const TYPE_COLORS: Record<string, string> = {
  safety: 'bg-red-500',
  behavioral: 'bg-orange-500',
  property: 'bg-blue-500',
  near_miss: 'bg-yellow-500',
  other: 'bg-zinc-500',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-600',
  high: 'bg-orange-500',
  medium: 'bg-yellow-500',
  low: 'bg-green-500',
};

const STATUS_COLORS: Record<string, string> = {
  reported: 'bg-blue-500/20 text-blue-400',
  investigating: 'bg-yellow-500/20 text-yellow-400',
  action_required: 'bg-orange-500/20 text-orange-400',
  resolved: 'bg-green-500/20 text-green-400',
  closed: 'bg-zinc-700 text-zinc-300',
};

const STATUS_LABELS: Record<string, string> = {
  reported: 'Reported',
  investigating: 'Investigating',
  action_required: 'Action Required',
  resolved: 'Resolved',
  closed: 'Closed',
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
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-zinc-500">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Incident Reports</h1>
          <p className="text-zinc-400 mt-1">Track and manage workplace incidents</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate('/app/ir/incidents')}>
            View All
          </Button>
          <Button onClick={() => navigate('/app/ir/incidents/new')}>Report Incident</Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardContent className="py-4">
            <div className="text-sm text-zinc-500 mb-1">Total Incidents</div>
            <div className="text-3xl font-bold text-white">{summary?.total_incidents || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="py-4">
            <div className="text-sm text-zinc-500 mb-1">Last 30 Days</div>
            <div className="text-3xl font-bold text-white">{summary?.recent_count || 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="py-4">
            <div className="text-sm text-zinc-500 mb-1">Avg Resolution</div>
            <div className="text-3xl font-bold text-white">
              {summary?.avg_resolution_days ? `${summary.avg_resolution_days}d` : '-'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="py-4">
            <div className="text-sm text-zinc-500 mb-1">Open Incidents</div>
            <div className="text-3xl font-bold text-white">
              {(summary?.by_status?.reported || 0) +
                (summary?.by_status?.investigating || 0) +
                (summary?.by_status?.action_required || 0)}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* By Type */}
        <Card>
          <CardContent>
            <h3 className="text-lg font-medium text-white mb-4">By Type</h3>
            {summary && Object.keys(summary.by_type).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(summary.by_type).map(([type, count]) => (
                  <div key={type} className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${TYPE_COLORS[type] || 'bg-zinc-500'}`} />
                    <div className="flex-1 text-sm text-zinc-300">{TYPE_LABELS[type] || type}</div>
                    <div className="text-sm font-medium text-white">{count}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-zinc-500">No data</div>
            )}
          </CardContent>
        </Card>

        {/* By Severity */}
        <Card>
          <CardContent>
            <h3 className="text-lg font-medium text-white mb-4">By Severity</h3>
            {summary && Object.keys(summary.by_severity).length > 0 ? (
              <div className="space-y-3">
                {['critical', 'high', 'medium', 'low'].map((severity) => {
                  const count = summary.by_severity[severity] || 0;
                  if (count === 0) return null;
                  return (
                    <div key={severity} className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${SEVERITY_COLORS[severity]}`} />
                      <div className="flex-1 text-sm text-zinc-300 capitalize">{severity}</div>
                      <div className="text-sm font-medium text-white">{count}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-sm text-zinc-500">No data</div>
            )}
          </CardContent>
        </Card>

        {/* By Status */}
        <Card>
          <CardContent>
            <h3 className="text-lg font-medium text-white mb-4">By Status</h3>
            {summary && Object.keys(summary.by_status).length > 0 ? (
              <div className="space-y-3">
                {['reported', 'investigating', 'action_required', 'resolved', 'closed'].map((status) => {
                  const count = summary.by_status[status] || 0;
                  if (count === 0) return null;
                  return (
                    <div key={status} className="flex items-center gap-3">
                      <div className="flex-1 text-sm text-zinc-300">{STATUS_LABELS[status]}</div>
                      <div className="text-sm font-medium text-white">{count}</div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-sm text-zinc-500">No data</div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Incidents */}
        <Card>
          <CardContent>
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-medium text-white">Recent Incidents</h3>
              <button
                onClick={() => navigate('/app/ir/incidents')}
                className="text-sm text-zinc-400 hover:text-white transition-colors"
              >
                View all
              </button>
            </div>
            {recentIncidents.length > 0 ? (
              <div className="space-y-3">
                {recentIncidents.map((incident) => (
                  <div
                    key={incident.id}
                    onClick={() => navigate(`/app/ir/incidents/${incident.id}`)}
                    className="flex items-start gap-3 p-3 rounded-lg bg-zinc-800/50 hover:bg-zinc-800 cursor-pointer transition-colors"
                  >
                    <div className={`w-2 h-2 rounded-full mt-2 ${SEVERITY_COLORS[incident.severity]}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-zinc-500 font-mono">{incident.incident_number}</span>
                        <span className={`px-1.5 py-0.5 text-xs rounded ${STATUS_COLORS[incident.status]}`}>
                          {STATUS_LABELS[incident.status]}
                        </span>
                      </div>
                      <div className="text-sm text-white truncate">{incident.title}</div>
                      <div className="text-xs text-zinc-500 mt-1">
                        {formatDate(incident.occurred_at)} • {TYPE_LABELS[incident.incident_type]}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <div className="text-zinc-500 mb-2">No incidents reported</div>
                <Button size="sm" onClick={() => navigate('/app/ir/incidents/new')}>
                  Report First Incident
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Location Hotspots */}
        <Card>
          <CardContent>
            <h3 className="text-lg font-medium text-white mb-4">Location Hotspots</h3>
            {locations && locations.hotspots.length > 0 ? (
              <div className="space-y-3">
                {locations.hotspots.map((hotspot, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-zinc-800 flex items-center justify-center text-xs text-zinc-400">
                      {idx + 1}
                    </div>
                    <div className="flex-1">
                      <div className="text-sm text-white">{hotspot.location}</div>
                      <div className="text-xs text-zinc-500">
                        Avg severity: {hotspot.avg_severity_score.toFixed(1)}/4
                      </div>
                    </div>
                    <div className="text-lg font-medium text-white">{hotspot.count}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-zinc-500">No location data available</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Trends Chart Placeholder */}
      {trends && trends.data.length > 0 && (
        <Card className="mt-6">
          <CardContent>
            <h3 className="text-lg font-medium text-white mb-4">Weekly Trend (Last 90 Days)</h3>
            <div className="flex items-end gap-1 h-32">
              {trends.data.map((point, idx) => {
                const maxCount = Math.max(...trends.data.map((d) => d.count), 1);
                const height = (point.count / maxCount) * 100;
                return (
                  <div
                    key={idx}
                    className="flex-1 bg-matcha-500/50 hover:bg-matcha-500 transition-colors rounded-t"
                    style={{ height: `${height}%` }}
                    title={`${point.date}: ${point.count} incidents`}
                  />
                );
              })}
            </div>
            <div className="flex justify-between text-xs text-zinc-500 mt-2">
              <span>{trends.start_date}</span>
              <span>{trends.end_date}</span>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default IRDashboard;
