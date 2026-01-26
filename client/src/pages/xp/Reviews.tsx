import { useState, useEffect } from 'react';
import {
  FileText,
  Plus,
  RefreshCw,
  AlertTriangle,
  Users,
  CheckCircle,
  Clock,
  X,
  Calendar,
  ChevronRight,
  Layers,
  Trash2,
} from 'lucide-react';
import { reviewsApi } from '../../api/xp';
import { useReviewTemplates, useReviewCycles } from '../../hooks/usePerformanceReviews';
import type { ReviewCycle, CycleProgress } from '../../types/xp';
import { StatCard } from '../../components/xp/StatCard';
import { StatusBadge } from '../../components/xp/StatusBadge';

type Tab = 'cycles' | 'templates';

export default function PerformanceReviews() {
  const [activeTab, setActiveTab] = useState<Tab>('cycles');
  const { data: templates, loading: loadingTemplates, error: templatesError, refetch: refetchTemplates } = useReviewTemplates();
  const { data: cycles, loading: loadingCycles, error: cyclesError, refetch: refetchCycles } = useReviewCycles();

  const [selectedCycle, setSelectedCycle] = useState<ReviewCycle | null>(null);
  const [cycleProgress, setCycleProgress] = useState<CycleProgress | null>(null);
  const [loadingProgress, setLoadingProgress] = useState(false);

  const [showCreateCycleModal, setShowCreateCycleModal] = useState(false);
  const [showCreateTemplateModal, setShowCreateTemplateModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Create cycle form state
  const [newCycle, setNewCycle] = useState({
    title: '',
    description: '',
    start_date: new Date().toISOString().split('T')[0],
    end_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    template_id: '',
  });
  const [creatingCycle, setCreatingCycle] = useState(false);

  // Create template form state
  const [newTemplate, setNewTemplate] = useState({
    name: '',
    description: '',
    categories: [
      {
        id: crypto.randomUUID(),
        name: 'Job Performance',
        weight: 40,
        criteria: [
          { id: crypto.randomUUID(), name: 'Quality of Work', description: 'Accuracy, thoroughness, and reliability of work output' },
          { id: crypto.randomUUID(), name: 'Productivity', description: 'Volume of work completed and efficiency' },
        ],
      },
      {
        id: crypto.randomUUID(),
        name: 'Collaboration',
        weight: 30,
        criteria: [
          { id: crypto.randomUUID(), name: 'Teamwork', description: 'Works effectively with others and contributes to team goals' },
          { id: crypto.randomUUID(), name: 'Communication', description: 'Clear and effective verbal and written communication' },
        ],
      },
      {
        id: crypto.randomUUID(),
        name: 'Growth',
        weight: 30,
        criteria: [
          { id: crypto.randomUUID(), name: 'Learning', description: 'Demonstrates willingness to learn and adapt' },
          { id: crypto.randomUUID(), name: 'Initiative', description: 'Takes initiative and shows ownership' },
        ],
      },
    ],
  });
  const [creatingTemplate, setCreatingTemplate] = useState(false);

  // Auto-select first active cycle
  useEffect(() => {
    if (cycles.length > 0 && !selectedCycle) {
      const activeCycle = cycles.find(c => c.status === 'active');
      if (activeCycle) {
        setSelectedCycle(activeCycle);
      }
    }
  }, [cycles, selectedCycle]);

  // Fetch progress when cycle is selected
  useEffect(() => {
    if (selectedCycle) {
      fetchProgress(selectedCycle.id);
    }
  }, [selectedCycle]);

  const fetchProgress = async (cycleId: string) => {
    try {
      setLoadingProgress(true);
      const data = await reviewsApi.getCycleProgress(cycleId);
      setCycleProgress(data);
    } catch (err) {
      console.error('Failed to fetch progress:', err);
      setCycleProgress(null);
    } finally {
      setLoadingProgress(false);
    }
  };

  const handleCreateCycle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCycle.title.trim()) {
      setError('Please enter a cycle title');
      return;
    }

    try {
      setCreatingCycle(true);
      setError(null);
      await reviewsApi.createCycle({
        ...newCycle,
        status: 'draft',
        template_id: newCycle.template_id || undefined,
      });
      setShowCreateCycleModal(false);
      setNewCycle({
        title: '',
        description: '',
        start_date: new Date().toISOString().split('T')[0],
        end_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        template_id: '',
      });
      refetchCycles();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create cycle');
    } finally {
      setCreatingCycle(false);
    }
  };

  const handleCreateTemplate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTemplate.name.trim()) {
      setError('Please enter a template name');
      return;
    }

    try {
      setCreatingTemplate(true);
      setError(null);
      await reviewsApi.createTemplate({
        ...newTemplate,
        is_active: true,
      });
      setShowCreateTemplateModal(false);
      setNewTemplate({
        name: '',
        description: '',
        categories: [
          {
            id: crypto.randomUUID(),
            name: 'Job Performance',
            weight: 40,
            criteria: [
              { id: crypto.randomUUID(), name: 'Quality of Work', description: 'Accuracy, thoroughness, and reliability of work output' },
              { id: crypto.randomUUID(), name: 'Productivity', description: 'Volume of work completed and efficiency' },
            ],
          },
        ],
      });
      refetchTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create template');
    } finally {
      setCreatingTemplate(false);
    }
  };

  const handleUpdateCycleStatus = async (cycleId: string, status: ReviewCycle['status']) => {
    try {
      setError(null);
      await reviewsApi.updateCycle(cycleId, { status });
      refetchCycles();
      if (selectedCycle?.id === cycleId) {
        setSelectedCycle({ ...selectedCycle, status });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update cycle');
    }
  };

  const addCategory = () => {
    setNewTemplate({
      ...newTemplate,
      categories: [
        ...newTemplate.categories,
        {
          id: crypto.randomUUID(),
          name: '',
          weight: 0,
          criteria: [{ id: crypto.randomUUID(), name: '', description: '' }],
        },
      ],
    });
  };

  const removeCategory = (categoryId: string) => {
    setNewTemplate({
      ...newTemplate,
      categories: newTemplate.categories.filter(c => c.id !== categoryId),
    });
  };

  const updateCategory = (categoryId: string, updates: Partial<typeof newTemplate.categories[0]>) => {
    setNewTemplate({
      ...newTemplate,
      categories: newTemplate.categories.map(c =>
        c.id === categoryId ? { ...c, ...updates } : c
      ),
    });
  };

  const addCriterion = (categoryId: string) => {
    setNewTemplate({
      ...newTemplate,
      categories: newTemplate.categories.map(c =>
        c.id === categoryId
          ? { ...c, criteria: [...c.criteria, { id: crypto.randomUUID(), name: '', description: '' }] }
          : c
      ),
    });
  };

  const removeCriterion = (categoryId: string, criterionId: string) => {
    setNewTemplate({
      ...newTemplate,
      categories: newTemplate.categories.map(c =>
        c.id === categoryId
          ? { ...c, criteria: c.criteria.filter(cr => cr.id !== criterionId) }
          : c
      ),
    });
  };

  const updateCriterion = (categoryId: string, criterionId: string, updates: Partial<typeof newTemplate.categories[0]['criteria'][0]>) => {
    setNewTemplate({
      ...newTemplate,
      categories: newTemplate.categories.map(c =>
        c.id === categoryId
          ? { ...c, criteria: c.criteria.map(cr => cr.id === criterionId ? { ...cr, ...updates } : cr) }
          : c
      ),
    });
  };

  const activeCycles = cycles.filter(c => c.status === 'active');
  const draftCycles = cycles.filter(c => c.status === 'draft');
  const completedCycles = cycles.filter(c => c.status === 'completed' || c.status === 'archived');

  const loading = loadingCycles || loadingTemplates;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
          Loading...
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
              Growth & Development
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Performance Reviews
          </h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Structured review cycles and feedback
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => activeTab === 'cycles' ? refetchCycles() : refetchTemplates()}
            className="p-2 border border-white/10 hover:border-white/30 transition-colors rounded"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4 text-zinc-400 hover:text-white transition-colors" />
          </button>
          <button
            onClick={() => activeTab === 'cycles' ? setShowCreateCycleModal(true) : setShowCreateTemplateModal(true)}
            className="flex items-center gap-2 bg-white text-black px-4 py-2 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors"
          >
            <Plus className="w-4 h-4" />
            {activeTab === 'cycles' ? 'New Cycle' : 'New Template'}
          </button>
        </div>
      </div>

      {(error || cyclesError || templatesError) && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="text-red-400" size={16} />
            <p className="text-sm text-red-400 font-mono">{error || cyclesError || templatesError}</p>
          </div>
          <button onClick={() => setError(null)} className="text-xs text-red-400 uppercase">
            Dismiss
          </button>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex border-b border-white/10">
        <button
          onClick={() => setActiveTab('cycles')}
          className={`px-6 py-3 text-sm font-bold uppercase tracking-wider transition-colors relative ${
            activeTab === 'cycles'
              ? 'text-white'
              : 'text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Review Cycles
          {activeTab === 'cycles' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-white" />
          )}
        </button>
        <button
          onClick={() => setActiveTab('templates')}
          className={`px-6 py-3 text-sm font-bold uppercase tracking-wider transition-colors relative ${
            activeTab === 'templates'
              ? 'text-white'
              : 'text-zinc-500 hover:text-zinc-300'
          }`}
        >
          Templates
          {activeTab === 'templates' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-white" />
          )}
        </button>
      </div>

      {/* Cycles Tab */}
      {activeTab === 'cycles' && (
        <div className="space-y-6">
          {/* Active Cycle Card */}
          {activeCycles.length > 0 && (
            <div className="bg-emerald-900/10 border border-emerald-500/20 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xs font-bold text-emerald-400 uppercase tracking-[0.2em]">Active Cycle</h2>
                <StatusBadge status="active" />
              </div>
              {activeCycles.map(cycle => (
                <div key={cycle.id} className="space-y-4">
                  <div>
                    <h3 className="text-xl font-bold text-white">{cycle.title}</h3>
                    {cycle.description && (
                      <p className="text-sm text-zinc-400 mt-1">{cycle.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-6 text-xs text-zinc-500">
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4" />
                      <span>
                        {new Date(cycle.start_date).toLocaleDateString()} - {new Date(cycle.end_date).toLocaleDateString()}
                      </span>
                    </div>
                    {cycle.template_name && (
                      <div className="flex items-center gap-2">
                        <Layers className="w-4 h-4" />
                        <span>{cycle.template_name}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setSelectedCycle(cycle)}
                      className="text-xs text-emerald-400 uppercase tracking-wider hover:text-emerald-300 transition-colors flex items-center gap-1"
                    >
                      View Progress <ChevronRight className="w-3 h-3" />
                    </button>
                    <button
                      onClick={() => handleUpdateCycleStatus(cycle.id, 'completed')}
                      className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors"
                    >
                      Complete Cycle
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Progress Section */}
          {selectedCycle && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">
                  Progress: {selectedCycle.title}
                </h2>
                <button
                  onClick={() => fetchProgress(selectedCycle.id)}
                  className="text-xs text-zinc-400 uppercase tracking-wider hover:text-white transition-colors"
                >
                  Refresh
                </button>
              </div>

              {loadingProgress ? (
                <div className="flex items-center justify-center py-12">
                  <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">
                    Loading progress...
                  </div>
                </div>
              ) : cycleProgress ? (
                <>
                  {/* Stats Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-px bg-white/10 border border-white/10">
                    <StatCard
                      label="Completion Rate"
                      value={`${Math.round(cycleProgress.completion_rate)}%`}
                      subtext={`${cycleProgress.completed} of ${cycleProgress.total} completed`}
                      icon={CheckCircle}
                      color="text-emerald-400"
                    />
                    <StatCard
                      label="Self Reviews"
                      value={cycleProgress.self_submitted}
                      subtext="Self-assessments submitted"
                      icon={Users}
                      color="text-blue-400"
                    />
                    <StatCard
                      label="Manager Reviews"
                      value={cycleProgress.manager_submitted}
                      subtext="Manager reviews submitted"
                      icon={FileText}
                      color="text-purple-400"
                    />
                    <StatCard
                      label="Pending"
                      value={cycleProgress.pending}
                      subtext="Awaiting submission"
                      icon={Clock}
                      color="text-amber-400"
                    />
                  </div>

                  {/* Progress Bar */}
                  <div className="bg-zinc-900/30 border border-white/10 p-6">
                    <h3 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-4">
                      Review Progress
                    </h3>
                    <div className="space-y-4">
                      <div className="h-4 rounded-full overflow-hidden flex bg-zinc-800">
                        {cycleProgress.completed > 0 && (
                          <div
                            className="bg-emerald-500 transition-all duration-500"
                            style={{ width: `${(cycleProgress.completed / cycleProgress.total) * 100}%` }}
                            title={`${cycleProgress.completed} completed`}
                          />
                        )}
                        {cycleProgress.manager_submitted > 0 && (
                          <div
                            className="bg-purple-500 transition-all duration-500"
                            style={{ width: `${(cycleProgress.manager_submitted / cycleProgress.total) * 100}%` }}
                            title={`${cycleProgress.manager_submitted} manager submitted`}
                          />
                        )}
                        {cycleProgress.self_submitted > 0 && (
                          <div
                            className="bg-blue-500 transition-all duration-500"
                            style={{ width: `${(cycleProgress.self_submitted / cycleProgress.total) * 100}%` }}
                            title={`${cycleProgress.self_submitted} self submitted`}
                          />
                        )}
                      </div>
                      <div className="flex items-center gap-6 text-xs">
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded bg-emerald-500" />
                          <span className="text-zinc-400">Completed ({cycleProgress.completed})</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded bg-purple-500" />
                          <span className="text-zinc-400">Manager Review ({cycleProgress.manager_submitted})</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded bg-blue-500" />
                          <span className="text-zinc-400">Self Review ({cycleProgress.self_submitted})</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded bg-zinc-700" />
                          <span className="text-zinc-400">Pending ({cycleProgress.pending})</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="bg-zinc-900/50 border border-white/10 p-12 text-center">
                  <FileText className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
                  <p className="text-sm text-zinc-500">No progress data available</p>
                </div>
              )}
            </div>
          )}

          {/* Cycle Lists */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Draft Cycles */}
            <div className="bg-zinc-900/30 border border-white/10">
              <div className="p-6 border-b border-white/10">
                <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Draft Cycles</h2>
              </div>
              <div className="divide-y divide-white/5">
                {draftCycles.length === 0 ? (
                  <div className="p-8 text-center text-sm text-zinc-500">No draft cycles</div>
                ) : (
                  draftCycles.map(cycle => (
                    <div key={cycle.id} className="p-4 hover:bg-white/5 transition-colors">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="text-sm font-medium text-white">{cycle.title}</h3>
                          <p className="text-xs text-zinc-500 mt-1">
                            {new Date(cycle.start_date).toLocaleDateString()} - {new Date(cycle.end_date).toLocaleDateString()}
                          </p>
                        </div>
                        <StatusBadge status="draft" />
                      </div>
                      <div className="flex items-center gap-3 mt-3">
                        <button
                          onClick={() => handleUpdateCycleStatus(cycle.id, 'active')}
                          className="text-xs text-emerald-400 uppercase tracking-wider hover:text-emerald-300 transition-colors"
                        >
                          Activate
                        </button>
                        <button
                          onClick={() => setSelectedCycle(cycle)}
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

            {/* Completed Cycles */}
            <div className="bg-zinc-900/30 border border-white/10">
              <div className="p-6 border-b border-white/10">
                <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Completed Cycles</h2>
              </div>
              <div className="divide-y divide-white/5">
                {completedCycles.length === 0 ? (
                  <div className="p-8 text-center text-sm text-zinc-500">No completed cycles</div>
                ) : (
                  completedCycles.map(cycle => (
                    <div key={cycle.id} className="p-4 hover:bg-white/5 transition-colors">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="text-sm font-medium text-white">{cycle.title}</h3>
                          <p className="text-xs text-zinc-500 mt-1">
                            {new Date(cycle.start_date).toLocaleDateString()} - {new Date(cycle.end_date).toLocaleDateString()}
                          </p>
                        </div>
                        <StatusBadge status={cycle.status} />
                      </div>
                      <div className="flex items-center gap-3 mt-3">
                        <button
                          onClick={() => setSelectedCycle(cycle)}
                          className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors flex items-center gap-1"
                        >
                          View Report
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Templates Tab */}
      {activeTab === 'templates' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.length === 0 ? (
              <div className="col-span-full bg-zinc-900/50 border border-white/10 p-12 text-center">
                <Layers className="w-16 h-16 text-zinc-700 mx-auto mb-4" />
                <p className="text-sm text-zinc-500 mb-4">No templates created yet</p>
                <button
                  onClick={() => setShowCreateTemplateModal(true)}
                  className="text-xs text-emerald-400 uppercase tracking-wider hover:text-emerald-300 transition-colors"
                >
                  Create Your First Template
                </button>
              </div>
            ) : (
              templates.map(template => (
                <div key={template.id} className="bg-zinc-900/30 border border-white/10 p-6 hover:border-white/20 transition-colors">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-white">{template.name}</h3>
                      {template.description && (
                        <p className="text-xs text-zinc-500 mt-1">{template.description}</p>
                      )}
                    </div>
                    <StatusBadge status={template.is_active ? 'active' : 'draft'} />
                  </div>
                  <div className="space-y-2">
                    <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                      {template.categories.length} Categories
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {template.categories.map(cat => (
                        <span
                          key={cat.id}
                          className="text-[10px] px-2 py-1 rounded bg-zinc-800/50 text-zinc-400"
                        >
                          {cat.name} ({cat.weight}%)
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-white/10 flex items-center gap-3">
                    <button className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors">
                      Edit
                    </button>
                    <button className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors">
                      Duplicate
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Create Cycle Modal */}
      {showCreateCycleModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-white/10 flex items-center justify-between">
              <h2 className="text-sm font-bold text-white uppercase tracking-[0.2em]">Create Review Cycle</h2>
              <button
                onClick={() => setShowCreateCycleModal(false)}
                className="p-2 hover:bg-white/5 rounded transition-colors"
              >
                <X className="w-4 h-4 text-zinc-400" />
              </button>
            </div>

            <form onSubmit={handleCreateCycle} className="p-6 space-y-6">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Cycle Title *
                </label>
                <input
                  type="text"
                  value={newCycle.title}
                  onChange={(e) => setNewCycle({ ...newCycle, title: e.target.value })}
                  placeholder="Q1 2024 Performance Review"
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Description
                </label>
                <textarea
                  value={newCycle.description}
                  onChange={(e) => setNewCycle({ ...newCycle, description: e.target.value })}
                  placeholder="Annual performance review for all employees..."
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
                    value={newCycle.start_date}
                    onChange={(e) => setNewCycle({ ...newCycle, start_date: e.target.value })}
                    className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={newCycle.end_date}
                    onChange={(e) => setNewCycle({ ...newCycle, end_date: e.target.value })}
                    className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Review Template
                </label>
                <select
                  value={newCycle.template_id}
                  onChange={(e) => setNewCycle({ ...newCycle, template_id: e.target.value })}
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                >
                  <option value="">Select a template (optional)</option>
                  {templates.map(template => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-3 pt-4 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setShowCreateCycleModal(false)}
                  className="flex-1 border border-white/10 text-white py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingCycle}
                  className="flex-1 bg-white text-black py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-50"
                >
                  {creatingCycle ? 'Creating...' : 'Create Cycle'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Template Modal */}
      {showCreateTemplateModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-white/10 flex items-center justify-between sticky top-0 bg-zinc-900">
              <h2 className="text-sm font-bold text-white uppercase tracking-[0.2em]">Create Review Template</h2>
              <button
                onClick={() => setShowCreateTemplateModal(false)}
                className="p-2 hover:bg-white/5 rounded transition-colors"
              >
                <X className="w-4 h-4 text-zinc-400" />
              </button>
            </div>

            <form onSubmit={handleCreateTemplate} className="p-6 space-y-6">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Template Name *
                </label>
                <input
                  type="text"
                  value={newTemplate.name}
                  onChange={(e) => setNewTemplate({ ...newTemplate, name: e.target.value })}
                  placeholder="Standard Performance Review"
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2 block">
                  Description
                </label>
                <textarea
                  value={newTemplate.description}
                  onChange={(e) => setNewTemplate({ ...newTemplate, description: e.target.value })}
                  placeholder="Template description..."
                  rows={2}
                  className="w-full bg-zinc-900 border border-white/10 text-white px-4 py-2 text-sm rounded focus:border-white/30 focus:outline-none resize-none"
                />
              </div>

              {/* Categories */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] uppercase tracking-wider text-zinc-500">
                    Review Categories
                  </label>
                  <button
                    type="button"
                    onClick={addCategory}
                    className="text-xs text-emerald-400 uppercase tracking-wider hover:text-emerald-300 transition-colors flex items-center gap-1"
                  >
                    <Plus className="w-3 h-3" /> Add Category
                  </button>
                </div>

                {newTemplate.categories.map((category) => (
                  <div key={category.id} className="bg-zinc-800/50 border border-white/10 p-4 space-y-4">
                    <div className="flex items-start gap-4">
                      <div className="flex-1">
                        <input
                          type="text"
                          value={category.name}
                          onChange={(e) => updateCategory(category.id, { name: e.target.value })}
                          placeholder="Category name"
                          className="w-full bg-zinc-900 border border-white/10 text-white px-3 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                        />
                      </div>
                      <div className="w-24">
                        <input
                          type="number"
                          value={category.weight}
                          onChange={(e) => updateCategory(category.id, { weight: parseInt(e.target.value) || 0 })}
                          placeholder="Weight %"
                          className="w-full bg-zinc-900 border border-white/10 text-white px-3 py-2 text-sm rounded focus:border-white/30 focus:outline-none"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => removeCategory(category.id)}
                        className="p-2 text-zinc-500 hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>

                    {/* Criteria */}
                    <div className="pl-4 space-y-2">
                      <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-2">Criteria</div>
                      {category.criteria.map((criterion) => (
                        <div key={criterion.id} className="flex items-start gap-2">
                          <div className="flex-1 space-y-2">
                            <input
                              type="text"
                              value={criterion.name}
                              onChange={(e) => updateCriterion(category.id, criterion.id, { name: e.target.value })}
                              placeholder="Criterion name"
                              className="w-full bg-zinc-900 border border-white/10 text-white px-3 py-1.5 text-xs rounded focus:border-white/30 focus:outline-none"
                            />
                            <input
                              type="text"
                              value={criterion.description}
                              onChange={(e) => updateCriterion(category.id, criterion.id, { description: e.target.value })}
                              placeholder="Description"
                              className="w-full bg-zinc-900 border border-white/10 text-zinc-400 px-3 py-1.5 text-xs rounded focus:border-white/30 focus:outline-none"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() => removeCriterion(category.id, criterion.id)}
                            className="p-1 text-zinc-600 hover:text-red-400 transition-colors"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                      <button
                        type="button"
                        onClick={() => addCriterion(category.id)}
                        className="text-[10px] text-zinc-500 uppercase tracking-wider hover:text-zinc-300 transition-colors flex items-center gap-1"
                      >
                        <Plus className="w-3 h-3" /> Add Criterion
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-3 pt-4 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setShowCreateTemplateModal(false)}
                  className="flex-1 border border-white/10 text-white py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingTemplate}
                  className="flex-1 bg-white text-black py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-50"
                >
                  {creatingTemplate ? 'Creating...' : 'Create Template'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
