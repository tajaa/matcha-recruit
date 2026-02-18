import { useState, useEffect } from 'react';
import {
  ClipboardCheck,
  Plus,
  RefreshCw,
  AlertTriangle,
  Users,
  TrendingUp,
  Calendar,
  X,
  ChevronRight,
  MessageCircle,
} from 'lucide-react';
import { enpsApi } from '../../api/xp';
import { useENPSSurveys } from '../../hooks/useENPSSurveys';
import type { ENPSSurvey, ENPSResults } from '../../types/xp';
import { StatCard } from '../../components/xp/StatCard';
import { StatusBadge } from '../../components/xp/StatusBadge';
import { ENPSScoreDisplay } from '../../components/xp/ENPSScoreDisplay';
import { ThemeCloud } from '../../components/xp/ThemeCloud';

// ─── eNPS Cycle Wizard ────────────────────────────────────────────────────────

type ENPSStepIcon = 'draft' | 'activate' | 'collect' | 'categorize' | 'score';

type ENPSWizardStep = {
  id: number;
  icon: ENPSStepIcon;
  title: string;
  description: string;
  action?: string;
};

const ENPS_CYCLE_STEPS: ENPSWizardStep[] = [
  {
    id: 1,
    icon: 'draft',
    title: 'Draft Survey',
    description: 'Set your survey period (typically 2 weeks), add a description, and include a custom follow-up question.',
    action: 'Click "New Survey" to start a draft.',
  },
  {
    id: 2,
    icon: 'activate',
    title: 'Activate',
    description: 'Launch the survey. This sends notification emails and makes it visible in the employee portal.',
    action: 'Click "Activate" on a draft survey.',
  },
  {
    id: 3,
    icon: 'collect',
    title: 'Collect Data',
    description: 'Monitor response rates in real-time. The system ensures high-quality data through automated reminders.',
    action: 'Review the "Response Rate" stat in analytics.',
  },
  {
    id: 4,
    icon: 'categorize',
    title: 'Categorize',
    description: 'The system automatically labels respondents as Promoters (9-10), Passives (7-8), or Detractors (0-6).',
    action: 'See the Promoter and Detractor rates below.',
  },
  {
    id: 5,
    icon: 'score',
    title: 'Score & Insight',
    description: 'AI analyzes the "why" behind the numbers, extracting themes from comments to calculate your final eNPS.',
    action: 'Review the "Promoter Themes" and final eNPS Score.',
  },
];

function ENPSCycleIcon({ icon, className = '' }: { icon: ENPSStepIcon; className?: string }) {
  const common = { className, width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true as const };
  
  if (icon === 'draft') {
    return (
      <svg {...common}>
        <path d="M10 6.5V3.5M10 16.5V13.5M13.5 10H16.5M3.5 10H6.5M12.5 7.5L14.5 5.5M5.5 14.5L7.5 12.5M12.5 12.5L14.5 14.5M5.5 5.5L7.5 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="10" r="2.3" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'activate') {
    return (
      <svg {...common}>
        <path d="M5 10H15M10 5L15 10L10 15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'collect') {
    return (
      <svg {...common}>
        <path d="M16 5L4 10L10 11L11 17L16 5Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === 'categorize') {
    return (
      <svg {...common}>
        <rect x="5" y="5" width="10" height="10" rx="1" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 8V12M8 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'score') {
    return (
      <svg {...common}>
        <path d="M4 16V12M10 16V8M16 16V4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M3 17H17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  return null;
}

function ENPSCycleWizard({ surveys, activeSurveysCount }: { surveys: ENPSSurvey[], activeSurveysCount: number }) {
  const storageKey = 'enps-wizard-collapsed-v1';
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'true'; } catch { return false; }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(storageKey, String(next)); } catch {}
  };

  const activeStep = surveys.some(s => (s.status === 'closed' || s.status === 'archived')) ? 5 
                  : activeSurveysCount > 0 ? 3
                  : surveys.some(s => s.status === 'draft') ? 2
                  : 1;

  return (
    <div className="border border-white/10 bg-zinc-950/60 mb-10">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">eNPS Cycle</span>
          <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 border border-zinc-700 text-zinc-400">
            Step {activeStep} of 5
          </span>
          <span className="text-[10px] text-zinc-600">
            {ENPS_CYCLE_STEPS[activeStep - 1].title}
          </span>
        </div>
        <ChevronDownIcon className={`text-zinc-600 transition-transform duration-200 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      {!collapsed && (
        <div className="border-t border-white/10">
          <div className="relative px-5 pt-5 pb-2 overflow-x-auto">
            <div className="flex items-start gap-0 min-w-max">
              {ENPS_CYCLE_STEPS.map((step, idx) => {
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
                        {isComplete ? '✓' : <ENPSCycleIcon icon={step.icon} className="w-4 h-4" />}
                      </div>
                      <div className={`mt-2 text-center text-[10px] font-bold uppercase tracking-wider leading-tight px-1 ${
                        isActive ? 'text-white' : isComplete ? 'text-matcha-400/70' : 'text-zinc-600'
                      }`}>
                        {step.title}
                      </div>
                    </div>
                    {idx < ENPS_CYCLE_STEPS.length - 1 && (
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
                <ENPSCycleIcon icon={ENPS_CYCLE_STEPS[activeStep - 1].icon} className="w-5 h-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    {ENPS_CYCLE_STEPS[activeStep - 1].title}
                  </span>
                  <span className="text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-white/10 text-zinc-400 border border-white/10">
                    Current Step
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed mb-2">
                  {ENPS_CYCLE_STEPS[activeStep - 1].description}
                </p>
                {ENPS_CYCLE_STEPS[activeStep - 1].action && (
                  <p className="text-[11px] text-matcha-400/80 font-medium">
                    → {ENPS_CYCLE_STEPS[activeStep - 1].action}
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

export default function ENPS() {
  const { data: surveys, loading: loadingSurveys, error: surveysError, refetch } = useENPSSurveys();
  const [selectedSurvey, setSelectedSurvey] = useState<ENPSSurvey | null>(null);
  const [results, setResults] = useState<ENPSResults | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create survey form state
  const [newSurvey, setNewSurvey] = useState({
    title: '',
    description: '',
    start_date: new Date().toISOString().split('T')[0],
    end_date: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    is_anonymous: true,
    custom_question: '',
  });
  const [creating, setCreating] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState<string | null>(null);

  // Auto-select first active survey
  useEffect(() => {
    if (surveys.length > 0 && !selectedSurvey) {
      const activeSurvey = surveys.find(s => s.status === 'active');
      if (activeSurvey) {
        setSelectedSurvey(activeSurvey);
      }
    }
  }, [surveys, selectedSurvey]);

  // Fetch results when survey is selected
  useEffect(() => {
    if (selectedSurvey) {
      fetchResults(selectedSurvey.id);
    }
  }, [selectedSurvey]);

  const fetchResults = async (surveyId: string) => {
    try {
      setLoadingResults(true);
      const data = await enpsApi.getResults(surveyId);
      setResults(data);
    } catch (err) {
      console.error('Failed to fetch results:', err);
      setResults(null);
    } finally {
      setLoadingResults(false);
    }
  };

  const handleCreateSurvey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSurvey.title.trim()) {
      setError('Please enter a survey title');
      return;
    }

    try {
      setCreating(true);
      setError(null);
      await enpsApi.createSurvey({
        ...newSurvey,
        status: 'draft',
      });
      setShowCreateModal(false);
      setNewSurvey({
        title: '',
        description: '',
        start_date: new Date().toISOString().split('T')[0],
        end_date: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        is_anonymous: true,
        custom_question: '',
      });
      refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create survey');
    } finally {
      setCreating(false);
    }
  };

  const handleUpdateStatus = async (surveyId: string, status: ENPSSurvey['status']) => {
    if (updatingStatus) return; // Prevent double-clicks
    try {
      setError(null);
      setUpdatingStatus(surveyId);
      await enpsApi.updateSurvey(surveyId, { status });
      await refetch();
      if (selectedSurvey?.id === surveyId) {
        setSelectedSurvey({ ...selectedSurvey, status });
      }
    } catch (err) {
      console.error('[eNPS] Status update failed:', err);
      setError(err instanceof Error ? err.message : 'Failed to update survey');
    } finally {
      setUpdatingStatus(null);
    }
  };

  const activeSurveys = surveys.filter(s => s.status === 'active');
  const draftSurveys = surveys.filter(s => s.status === 'draft');
  const closedSurveys = surveys.filter(s => s.status === 'closed' || s.status === 'archived');

  if (loadingSurveys) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
          Loading surveys...
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
              Employee Sentiment
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            eNPS Surveys
          </h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Measure employee loyalty and satisfaction
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={refetch}
            className="p-2 border border-white/10 hover:border-white/30 transition-colors rounded"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-zinc-400 hover:text-white transition-colors" />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 bg-white text-black px-4 py-2 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Survey
          </button>
        </div>
      </div>

      <ENPSCycleWizard surveys={surveys} activeSurveysCount={activeSurveys.length} />

      {(error || surveysError) && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-red-400" size={16} />
            <p className="text-sm text-red-400 font-mono">{error || surveysError}</p>
          </div>
          <button onClick={() => setError(null)} className="text-xs text-red-400 uppercase">
            Dismiss
          </button>
        </div>
      )}

      {/* Active Survey Card */}
      {activeSurveys.length > 0 && (
        <div className="bg-emerald-900/10 border border-emerald-500/20 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-bold text-emerald-400 uppercase tracking-[0.2em]">Active Survey</h2>
            <StatusBadge status="active" />
          </div>
          {activeSurveys.map(survey => (
            <div key={survey.id} className="space-y-4">
              <div>
                <h3 className="text-xl font-bold text-white">{survey.title}</h3>
                {survey.description && (
                  <p className="text-sm text-zinc-400 mt-1">{survey.description}</p>
                )}
              </div>
              <div className="flex items-center gap-6 text-xs text-zinc-500">
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  <span>
                    {new Date(survey.start_date).toLocaleDateString()} - {new Date(survey.end_date).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  <span>{survey.is_anonymous ? 'Anonymous' : 'Named'}</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSelectedSurvey(survey)}
                  className="text-xs text-emerald-400 uppercase tracking-wider hover:text-emerald-300 transition-colors flex items-center gap-1"
                >
                  View Results <ChevronRight className="w-3 h-3" />
                </button>
                <button
                  onClick={() => handleUpdateStatus(survey.id, 'closed')}
                  disabled={!!updatingStatus}
                  className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {updatingStatus === survey.id ? 'Closing...' : 'Close Survey'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Analytics Section */}
      {selectedSurvey && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">
              Analytics: {selectedSurvey.title}
            </h2>
            <button
              onClick={() => fetchResults(selectedSurvey.id)}
              className="text-xs text-zinc-400 uppercase tracking-wider hover:text-white transition-colors"
            >
              Refresh
            </button>
          </div>

          {loadingResults ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
                Loading analytics...
              </div>
            </div>
          ) : results ? (
            <>
              {/* eNPS Score Display */}
              <ENPSScoreDisplay
                score={results.enps_score}
                promoters={results.promoters}
                passives={results.passives}
                detractors={results.detractors}
                totalResponses={results.total_responses}
                size="lg"
              />

              {/* Stats Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-white/10 border border-white/10">
                <StatCard
                  label="Response Rate"
                  value={`${Math.round(results.response_rate)}%`}
                  subtext={`${results.total_responses} total responses`}
                  icon={Users}
                  color="text-emerald-400"
                />
                <StatCard
                  label="Promoter Rate"
                  value={`${results.total_responses > 0 ? Math.round((results.promoters / results.total_responses) * 100) : 0}%`}
                  subtext={`${results.promoters} promoters (9-10)`}
                  icon={TrendingUp}
                  color="text-emerald-400"
                />
                <StatCard
                  label="Detractor Rate"
                  value={`${results.total_responses > 0 ? Math.round((results.detractors / results.total_responses) * 100) : 0}%`}
                  subtext={`${results.detractors} detractors (0-6)`}
                  icon={AlertTriangle}
                  color="text-red-400"
                />
              </div>

              {/* Theme Clouds */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {results.promoter_themes && results.promoter_themes.length > 0 && (
                  <div className="bg-zinc-900/30 border border-emerald-500/20 p-6">
                    <h3 className="text-xs font-bold text-emerald-400 uppercase tracking-[0.2em] mb-4">
                      Promoter Themes
                    </h3>
                    <ThemeCloud
                      themes={results.promoter_themes.map(t => ({ ...t, sentiment: 0.5 }))}
                      maxThemes={10}
                    />
                  </div>
                )}
                {results.passive_themes && results.passive_themes.length > 0 && (
                  <div className="bg-zinc-900/30 border border-amber-500/20 p-6">
                    <h3 className="text-xs font-bold text-amber-400 uppercase tracking-[0.2em] mb-4">
                      Passive Themes
                    </h3>
                    <ThemeCloud
                      themes={results.passive_themes.map(t => ({ ...t, sentiment: 0 }))}
                      maxThemes={10}
                    />
                  </div>
                )}
                {results.detractor_themes && results.detractor_themes.length > 0 && (
                  <div className="bg-zinc-900/30 border border-red-500/20 p-6">
                    <h3 className="text-xs font-bold text-red-400 uppercase tracking-[0.2em] mb-4">
                      Detractor Themes
                    </h3>
                    <ThemeCloud
                      themes={results.detractor_themes.map(t => ({ ...t, sentiment: -0.5 }))}
                      maxThemes={10}
                    />
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
              <ClipboardCheck className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
              <p className="text-sm text-zinc-500">No results available yet</p>
            </div>
          )}
        </div>
      )}

      {/* Survey Lists */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Draft Surveys */}
        <div className="bg-zinc-900/30 border border-white/10">
          <div className="p-6 border-b border-white/10">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Draft Surveys</h2>
          </div>
          <div className="divide-y divide-white/5">
            {draftSurveys.length === 0 ? (
              <div className="p-8 text-center text-sm text-zinc-500">No draft surveys</div>
            ) : (
              draftSurveys.map(survey => (
                <div key={survey.id} className="p-4 hover:bg-white/5 transition-colors">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-medium text-white">{survey.title}</h3>
                      <p className="text-xs text-zinc-500 mt-1">
                        Created {new Date(survey.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <StatusBadge status="draft" />
                  </div>
                  <div className="flex items-center gap-3 mt-3">
                    <button
                      onClick={() => handleUpdateStatus(survey.id, 'active')}
                      disabled={!!updatingStatus}
                      className="text-xs text-emerald-400 uppercase tracking-wider hover:text-emerald-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {updatingStatus === survey.id ? 'Activating...' : 'Activate'}
                    </button>
                    <button
                      onClick={() => setSelectedSurvey(survey)}
                      className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors"
                    >
                      Preview
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Closed Surveys */}
        <div className="bg-zinc-900/30 border border-white/10">
          <div className="p-6 border-b border-white/10">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Closed Surveys</h2>
          </div>
          <div className="divide-y divide-white/5">
            {closedSurveys.length === 0 ? (
              <div className="p-8 text-center text-sm text-zinc-500">No closed surveys</div>
            ) : (
              closedSurveys.map(survey => (
                <div key={survey.id} className="p-4 hover:bg-white/5 transition-colors">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-medium text-white">{survey.title}</h3>
                      <p className="text-xs text-zinc-500 mt-1">
                        {new Date(survey.start_date).toLocaleDateString()} - {new Date(survey.end_date).toLocaleDateString()}
                      </p>
                    </div>
                    <StatusBadge status={survey.status} />
                  </div>
                  <div className="flex items-center gap-3 mt-3">
                    <button
                      onClick={() => setSelectedSurvey(survey)}
                      className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors flex items-center gap-1"
                    >
                      <MessageCircle className="w-3 h-3" /> View Results
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Create Survey Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <h2 className="text-sm font-bold text-white uppercase tracking-[0.2em]">Create eNPS Survey</h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className="p-2 hover:bg-white/5 rounded transition-colors"
              >
                <X className="w-4 h-4 text-zinc-400" />
              </button>
            </div>

            <form onSubmit={handleCreateSurvey} className="p-6 space-y-6">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Survey Title *
                </label>
                <input
                  type="text"
                  value={newSurvey.title}
                  onChange={(e) => setNewSurvey({ ...newSurvey, title: e.target.value })}
                  placeholder="Q1 2024 Employee Sentiment"
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Description
                </label>
                <textarea
                  value={newSurvey.description}
                  onChange={(e) => setNewSurvey({ ...newSurvey, description: e.target.value })}
                  placeholder="Help us understand how you feel about working here..."
                  rows={3}
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={newSurvey.start_date}
                    onChange={(e) => setNewSurvey({ ...newSurvey, start_date: e.target.value })}
                    className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={newSurvey.end_date}
                    onChange={(e) => setNewSurvey({ ...newSurvey, end_date: e.target.value })}
                    className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newSurvey.is_anonymous}
                    onChange={(e) => setNewSurvey({ ...newSurvey, is_anonymous: e.target.checked })}
                    className="w-4 h-4 rounded bg-zinc-900 border-white/10 text-emerald-500 focus:ring-emerald-500"
                  />
                  <span className="text-sm text-zinc-300">Anonymous responses</span>
                </label>
                <p className="text-xs text-zinc-500 mt-1 ml-6">
                  Employees will not be identified in their responses
                </p>
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Custom Follow-up Question (optional)
                </label>
                <input
                  type="text"
                  value={newSurvey.custom_question}
                  onChange={(e) => setNewSurvey({ ...newSurvey, custom_question: e.target.value })}
                  placeholder="What's one thing we could do better?"
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                />
              </div>

              <div className="flex items-center gap-3 pt-4 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 border border-white/10 text-white py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="flex-1 bg-white text-black py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create Survey'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
