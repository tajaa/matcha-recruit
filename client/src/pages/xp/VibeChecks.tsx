import { useState, useEffect } from 'react';
import { Smile, TrendingUp, Users, MessageCircle, RefreshCw, AlertTriangle } from 'lucide-react';
import { vibeChecksApi } from '../../api/xp';
import { useVibeAnalytics } from '../../hooks/useVibeAnalytics';
import type { VibeCheckConfig, VibeCheckResponse } from '../../types/xp';
import { StatCard } from '../../components/xp/StatCard';
import { PeriodSelector } from '../../components/xp/PeriodSelector';
import { ThemeCloud } from '../../components/xp/ThemeCloud';
import { TrendChart } from '../../components/xp/TrendChart';

// ─── Vibe Cycle Wizard ────────────────────────────────────────────────────────

type VibeStepIcon = 'config' | 'broadcast' | 'capture' | 'analyze' | 'trends';

type VibeWizardStep = {
  id: number;
  icon: VibeStepIcon;
  title: string;
  description: string;
  action?: string;
};

const VIBE_CYCLE_STEPS: VibeWizardStep[] = [
  {
    id: 1,
    icon: 'config',
    title: 'Configure Vibe',
    description: 'Set your pulse survey frequency (daily to monthly), anonymity rules, and enable the system.',
    action: 'Review the Configuration card below.',
  },
  {
    id: 2,
    icon: 'broadcast',
    title: 'Auto-Broadcast',
    description: 'Matcha automatically pings your team via email or portal when it is time for a vibe check.',
    action: 'Ensure "Enabled" is checked in your settings.',
  },
  {
    id: 3,
    icon: 'capture',
    title: 'Capture Mood',
    description: 'Team members submit a 1-click mood rating (1–5) and optional qualitative comments.',
    action: 'Recent submissions appear in the "Recent Responses" section.',
  },
  {
    id: 4,
    icon: 'analyze',
    title: 'AI Analysis',
    description: 'The AI extracts sentiment scores and trending themes from all incoming comments.',
    action: 'Check "Top Themes" and "Avg Sentiment" in analytics.',
  },
  {
    id: 5,
    icon: 'trends',
    title: 'Review Trends',
    description: 'Monitor mood trends over time to identify burnout, morale shifts, or cultural wins.',
    action: 'View the Mood Trend chart to see longitudinal shifts.',
  },
];

function VibeCycleIcon({ icon, className = '' }: { icon: VibeStepIcon; className?: string }) {
  const common = { className, width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true as const };
  
  if (icon === 'config') {
    return (
      <svg {...common}>
        <path d="M10 6.5V3.5M10 16.5V13.5M13.5 10H16.5M3.5 10H6.5M12.5 7.5L14.5 5.5M5.5 14.5L7.5 12.5M12.5 12.5L14.5 14.5M5.5 5.5L7.5 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="10" r="2.3" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'broadcast') {
    return (
      <svg {...common}>
        <path d="M16 5L4 10L10 11L11 17L16 5Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === 'capture') {
    return (
      <svg {...common}>
        <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.6" />
        <path d="M7 10L9 12L13 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === 'analyze') {
    return (
      <svg {...common}>
        <rect x="5" y="5" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 8V12M8 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'trends') {
    return (
      <svg {...common}>
        <path d="M4 16V12M10 16V8M16 16V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M3 17H17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  return null;
}

function VibeCycleWizard({ responsesCount, configEnabled }: { responsesCount: number, configEnabled: boolean }) {
  const storageKey = 'vibe-wizard-collapsed-v1';
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'true'; } catch { return false; }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(storageKey, String(next)); } catch {}
  };

  const activeStep = responsesCount > 10 ? 5 
                  : responsesCount > 0 ? 4
                  : configEnabled ? 2
                  : 1;

  return (
    <div className="border border-white/10 bg-zinc-950/60 mb-10">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">Vibe Cycle</span>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 border border-zinc-700 text-zinc-400">
              Step {activeStep} of 5
            </span>
            <span className="text-[10px] text-zinc-600 hidden sm:inline">
              {VIBE_CYCLE_STEPS[activeStep - 1].title}
            </span>
          </div>
        </div>
        <ChevronDownIcon className={`text-zinc-600 transition-transform duration-200 shrink-0 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      {!collapsed && (
        <div className="border-t border-white/10">
          <div className="relative px-5 pt-5 pb-2 overflow-x-auto no-scrollbar">
            <div className="flex items-start gap-0 min-w-max">
              {VIBE_CYCLE_STEPS.map((step, idx) => {
                const isComplete = step.id < activeStep;
                const isActive = step.id === activeStep;

                return (
                  <div key={step.id} className="flex items-start">
                    <div className="flex flex-col items-center w-28">
                      <div className={`relative w-9 h-9 rounded-full border-2 flex items-center justify-center text-sm transition-all ${
                        isComplete
                          ? 'bg-matcha-500/20 border-matcha-500/50 text-matcha-400'
                          : isActive
                          ? 'bg-white/10 border-white text-white shadow-[0_0_12px_rgba(255,255,255,0.15)]'
                          : 'bg-zinc-900 border-zinc-700 text-zinc-600'
                      }`}>
                        {isComplete ? '✓' : <VibeCycleIcon icon={step.icon} className="w-4 h-4" />}
                      </div>
                      <div className={`mt-2 text-center text-[10px] font-bold uppercase tracking-wider leading-tight px-1 ${
                        isActive ? 'text-white' : isComplete ? 'text-matcha-400/70' : 'text-zinc-600'
                      }`}>
                        {step.title}
                      </div>
                    </div>
                    {idx < VIBE_CYCLE_STEPS.length - 1 && (
                      <div className={`w-10 h-0.5 mt-[18px] flex-shrink-0 transition-colors ${
                        step.id < activeStep ? 'bg-matcha-500/40' : 'bg-zinc-800'
                      }`} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mx-5 mb-5 p-4 bg-white/[0.03] border border-white/10">
            <div className="flex items-start gap-3">
              <span className="text-xl flex-shrink-0 text-zinc-200">
                <VibeCycleIcon icon={VIBE_CYCLE_STEPS[activeStep - 1].icon} className="w-5 h-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    {VIBE_CYCLE_STEPS[activeStep - 1].title}
                  </span>
                  <span className="text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-white/10 text-zinc-400 border border-white/10">
                    Current Step
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed mb-2">
                  {VIBE_CYCLE_STEPS[activeStep - 1].description}
                </p>
                {VIBE_CYCLE_STEPS[activeStep - 1].action && (
                  <p className="text-[11px] text-matcha-400/80 font-medium">
                    → {VIBE_CYCLE_STEPS[activeStep - 1].action}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ChevronDownIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden="true"
    >
      <path d="M5 7.5L10 12.5L15 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

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

      <VibeCycleWizard responsesCount={responses.length} configEnabled={config?.enabled ?? false} />

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
              {(() => {
                const avgMood = analytics.avg_mood_rating != null ? Number(analytics.avg_mood_rating) : null;
                const avgSentiment = analytics.avg_sentiment_score != null ? Number(analytics.avg_sentiment_score) : null;
                const responseRate = analytics.response_rate != null ? Number(analytics.response_rate) : null;
                return (
                  <>
                    <StatCard
                      label="Avg Mood Rating"
                      value={avgMood != null && !isNaN(avgMood) ? avgMood.toFixed(1) : '—'}
                      subtext={avgMood != null && !isNaN(avgMood) ? getMoodLabel(Math.round(avgMood)) : 'No data'}
                      icon={Smile}
                      color={avgMood != null && !isNaN(avgMood) ? getMoodColor(avgMood) : 'text-zinc-500'}
                    />
                    <StatCard
                      label="Response Rate"
                      value={responseRate != null && !isNaN(responseRate) ? `${Math.round(responseRate)}%` : '—'}
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
                      value={avgSentiment != null && !isNaN(avgSentiment) ? avgSentiment.toFixed(2) : '—'}
                      subtext={avgSentiment != null && !isNaN(avgSentiment) ? (avgSentiment > 0 ? 'Positive' : avgSentiment < 0 ? 'Negative' : 'Neutral') : 'No data'}
                      icon={TrendingUp}
                      color={avgSentiment != null && !isNaN(avgSentiment) ? getSentimentColor(avgSentiment) : 'text-zinc-500'}
                    />
                  </>
                );
              })()}
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
                          {response.employee_name || 'Unknown Employee'}
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
