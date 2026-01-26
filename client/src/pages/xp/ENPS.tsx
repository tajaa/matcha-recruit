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
    try {
      setError(null);
      await enpsApi.updateSurvey(surveyId, { status });
      refetch();
      if (selectedSurvey?.id === surveyId) {
        setSelectedSurvey({ ...selectedSurvey, status });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update survey');
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
                  className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors"
                >
                  Close Survey
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
                      className="text-xs text-emerald-400 uppercase tracking-wider hover:text-emerald-300 transition-colors"
                    >
                      Activate
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
