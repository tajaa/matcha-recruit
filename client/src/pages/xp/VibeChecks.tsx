import { useState, useEffect } from 'react';
import { Smile, TrendingUp, Users, MessageCircle, RefreshCw, AlertTriangle } from 'lucide-react';
import { vibeChecksApi } from '../../api/xp';
import { useVibeAnalytics } from '../../hooks/useVibeAnalytics';
import type { VibeCheckConfig, VibeCheckResponse } from '../../types/xp';
import { StatCard } from '../../components/xp/StatCard';
import { PeriodSelector } from '../../components/xp/PeriodSelector';
import { ThemeCloud } from '../../components/xp/ThemeCloud';
import { TrendChart } from '../../components/xp/TrendChart';

export default function VibeChecks() {
  const [config, setConfig] = useState<VibeCheckConfig | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [savingConfig, setSavingConfig] = useState(false);
  const [period, setPeriod] = useState<'week' | 'month' | 'quarter'>('week');
  const [responses, setResponses] = useState<VibeCheckResponse[]>([]);
  const [loadingResponses, setLoadingResponses] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: analytics, loading: loadingAnalytics, error: analyticsError, refetch } = useVibeAnalytics(period);

  useEffect(() => {
    fetchConfig();
    fetchResponses();
  }, []);

  const fetchConfig = async () => {
    try {
      setLoadingConfig(true);
      const data = await vibeChecksApi.getConfig();
      setConfig(data);
    } catch (err) {
      console.error('Failed to fetch config:', err);
    } finally {
      setLoadingConfig(false);
    }
  };

  const fetchResponses = async () => {
    try {
      setLoadingResponses(true);
      const data = await vibeChecksApi.getResponses(20, 0);
      setResponses(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch responses:', err);
      setResponses([]);
    } finally {
      setLoadingResponses(false);
    }
  };

  const handleConfigUpdate = async (updates: Partial<VibeCheckConfig>) => {
    if (!config) return;

    try {
      setSavingConfig(true);
      setError(null);
      const updated = await vibeChecksApi.updateConfig(updates);
      setConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update configuration');
    } finally {
      setSavingConfig(false);
    }
  };

  const getMoodColor = (avgMood: number) => {
    if (avgMood >= 4.5) return 'text-emerald-400';
    if (avgMood >= 3.5) return 'text-emerald-500';
    if (avgMood >= 2.5) return 'text-amber-400';
    if (avgMood >= 1.5) return 'text-orange-400';
    return 'text-red-400';
  };

  const getMoodLabel = (rating: number) => {
    const labels = ['', '😞 Very Bad', '😕 Bad', '😐 Okay', '🙂 Good', '😄 Great'];
    return labels[rating] || '';
  };

  const getSentimentColor = (score: number) => {
    if (score > 0.3) return 'text-emerald-400';
    if (score > -0.3) return 'text-amber-400';
    return 'text-red-400';
  };

  if (loadingConfig) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
          Loading configuration...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Pulse Check
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Vibe Checks
          </h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Quick pulse surveys to measure team mood
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-red-400" size={16} />
            <p className="text-sm text-red-400 font-mono">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="text-xs text-red-400 uppercase">
            Dismiss
          </button>
        </div>
      )}

      {/* Configuration Card */}
      {config && (
        <div className="bg-zinc-900/30 border border-white/10 p-6">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-6">Configuration</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                Frequency
              </label>
              <select
                value={config.frequency}
                onChange={(e) => handleConfigUpdate({ frequency: e.target.value as any })}
                disabled={savingConfig}
                className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded hover:border-white/30 focus:border-white/50 outline-none transition-colors disabled:opacity-50"
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="biweekly">Bi-weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                Settings
              </label>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.enabled}
                    onChange={(e) => handleConfigUpdate({ enabled: e.target.checked })}
                    disabled={savingConfig}
                    className="w-4 h-4 rounded bg-zinc-900 border-white/10 text-emerald-500 focus:ring-emerald-500 disabled:opacity-50"
                  />
                  <span className="text-sm text-zinc-300">Enabled</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.is_anonymous}
                    onChange={(e) => handleConfigUpdate({ is_anonymous: e.target.checked })}
                    disabled={savingConfig}
                    className="w-4 h-4 rounded bg-zinc-900 border-white/10 text-emerald-500 focus:ring-emerald-500 disabled:opacity-50"
                  />
                  <span className="text-sm text-zinc-300">Anonymous</span>
                </label>
              </div>
            </div>
          </div>

          {savingConfig && (
            <div className="mt-4 text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
              Saving...
            </div>
          )}
        </div>
      )}

      {/* Analytics Section */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Analytics Dashboard</h2>
          <div className="flex items-center gap-4">
            <PeriodSelector selected={period} onChange={setPeriod} />
            <button
              onClick={refetch}
              className="p-2 border border-white/10 hover:border-white/30 transition-colors rounded"
              title="Refresh analytics"
            >
              <RefreshCw className="w-4 h-4 text-zinc-400 hover:text-white transition-colors" />
            </button>
          </div>
        </div>

        {loadingAnalytics ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
              Loading analytics...
            </div>
          </div>
        ) : analyticsError ? (
          <div className="bg-red-500/10 border border-red-500/20 rounded p-4 text-center">
            <p className="text-sm text-red-400">Failed to load analytics</p>
          </div>
        ) : analytics ? (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10">
              <StatCard
                label="Avg Mood Rating"
                value={analytics.avg_mood_rating?.toFixed(1) ?? '—'}
                subtext={analytics.avg_mood_rating ? getMoodLabel(Math.round(analytics.avg_mood_rating)) : 'No data'}
                icon={Smile}
                color={analytics.avg_mood_rating ? getMoodColor(analytics.avg_mood_rating) : 'text-zinc-500'}
              />
              <StatCard
                label="Response Rate"
                value={analytics.response_rate != null ? `${Math.round(analytics.response_rate)}%` : '—'}
                subtext={`${analytics.total_responses ?? 0} responses`}
                icon={Users}
                color="text-emerald-400"
              />
              <StatCard
                label="Total Responses"
                value={analytics.total_responses ?? 0}
                subtext="This period"
                icon={MessageCircle}
                color="text-white"
              />
              <StatCard
                label="Avg Sentiment"
                value={analytics.avg_sentiment_score?.toFixed(2) ?? '—'}
                subtext={analytics.avg_sentiment_score != null ? (analytics.avg_sentiment_score > 0 ? 'Positive' : analytics.avg_sentiment_score < 0 ? 'Negative' : 'Neutral') : 'No data'}
                icon={TrendingUp}
                color={analytics.avg_sentiment_score != null ? getSentimentColor(analytics.avg_sentiment_score) : 'text-zinc-500'}
              />
            </div>

            {/* Trend Chart */}
            {analytics.trend_data && analytics.trend_data.length > 0 && (
              <div className="bg-zinc-900/30 border border-white/10 p-6">
                <h3 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-6">Mood Trend</h3>
                <TrendChart
                  data={analytics.trend_data.map(d => ({
                    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                    value: d.avg_mood ?? 0,
                    label: `${d.avg_mood?.toFixed(1) ?? '—'} / 5.0`
                  }))}
                  color="#34d399"
                />
              </div>
            )}

            {/* Theme Cloud */}
            {analytics.top_themes && analytics.top_themes.length > 0 && (
              <div className="bg-zinc-900/30 border border-white/10 p-6">
                <h3 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-6">Top Themes</h3>
                <ThemeCloud themes={analytics.top_themes} />
              </div>
            )}
          </>
        ) : (
          <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
            <Smile className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
            <p className="text-sm text-zinc-500">No analytics data available yet</p>
          </div>
        )}
      </div>

      {/* Recent Responses */}
      <div className="bg-zinc-900/30 border border-white/10">
        <div className="p-6 border-b border-white/10 flex justify-between items-center">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Recent Responses</h2>
          <button
            onClick={fetchResponses}
            className="text-xs text-zinc-400 hover:text-white uppercase tracking-wider transition-colors"
          >
            Refresh
          </button>
        </div>
        <div className="divide-y divide-white/5">
          {loadingResponses ? (
            <div className="p-8 text-center text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
              Loading responses...
            </div>
          ) : !responses || responses.length === 0 ? (
            <div className="p-8 text-center text-sm text-zinc-500">
              No responses yet
            </div>
          ) : (
            responses.map((response) => (
              <div key={response.id} className="p-4 hover:bg-white/5 transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">{getMoodLabel(response.mood_rating).split(' ')[0]}</span>
                      <div>
                        <div className="text-sm text-white font-medium">
                          {config?.is_anonymous ? 'Anonymous' : response.employee_name || 'Unknown Employee'}
                        </div>
                        <div className="text-xs text-zinc-500 font-mono">
                          {new Date(response.created_at).toLocaleString()}
                        </div>
                      </div>
                    </div>
                    {response.comment && (
                      <p className="text-sm text-zinc-400 mt-2">{response.comment}</p>
                    )}
                    {response.sentiment_analysis?.themes && response.sentiment_analysis.themes.length > 0 && (
                      <div className="flex gap-2 mt-2 flex-wrap">
                        {response.sentiment_analysis.themes.map((theme, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-2 py-1 rounded bg-zinc-800/50 text-zinc-400 uppercase tracking-wider"
                          >
                            {theme}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
