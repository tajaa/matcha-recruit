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

// ─── Review Cycle Wizard ──────────────────────────────────────────────────────

type ReviewStepIcon = 'template' | 'launch' | 'self' | 'manager' | 'finalize';

type ReviewWizardStep = {
  id: number;
  icon: ReviewStepIcon;
  title: string;
  description: string;
  action?: string;
};

const REVIEW_CYCLE_STEPS: ReviewWizardStep[] = [
  {
    id: 1,
    icon: 'template',
    title: 'Define Templates',
    description: 'Create structured criteria, categories (e.g., Job Performance, Collaboration), and weighted scores.',
    action: 'Switch to the "Templates" tab to build or edit.',
  },
  {
    id: 2,
    icon: 'launch',
    title: 'Launch Cycle',
    description: 'Set the review period and select a template. This automatically notifies all participants.',
    action: 'Click "New Cycle" to start a review period.',
  },
  {
    id: 3,
    icon: 'self',
    title: 'Self-Assessments',
    description: 'Employees reflect on their own performance and submit self-reviews through the portal.',
    action: 'Monitor "Self Reviews" in the progress dashboard.',
  },
  {
    id: 4,
    icon: 'manager',
    title: 'Manager Reviews',
    description: 'Managers complete evaluations for their direct reports based on the established template.',
    action: 'Monitor "Manager Reviews" in the progress dashboard.',
  },
  {
    id: 5,
    icon: 'finalize',
    title: 'Finalize Growth',
    description: 'Complete the cycle to lock scores and finalize development plans and growth paths.',
    action: 'Review completion rates and click "Complete Cycle".',
  },
];

function ReviewCycleIcon({ icon, className = '' }: { icon: ReviewStepIcon; className?: string }) {
  const common = { className, width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true as const };
  
  if (icon === 'template') {
    return (
      <svg {...common}>
        <path d="M10 6.5V3.5M10 16.5V13.5M13.5 10H16.5M3.5 10H6.5M12.5 7.5L14.5 5.5M5.5 14.5L7.5 12.5M12.5 12.5L14.5 14.5M5.5 5.5L7.5 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="10" r="2.3" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'launch') {
    return (
      <svg {...common}>
        <path d="M16 5L4 10L10 11L11 17L16 5Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === 'self') {
    return (
      <svg {...common}>
        <path d="M10 5C7.23858 5 5 7.23858 5 10C5 12.7614 7.23858 15 10 15C12.7614 15 15 12.7614 15 10C15 7.23858 12.7614 5 10 5Z" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 8V12M8 10H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'manager') {
    return (
      <svg {...common}>
        <rect x="5" y="4" width="10" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
        <path d="M8 8H12M8 11H12M8 14H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'finalize') {
    return (
      <svg {...common}>
        <path d="M6 10.3L8.5 12.8L14 7.3" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  return null;
}

function ReviewCycleWizard({ activeCyclesCount, cyclesCount, templatesCount }: { activeCyclesCount: number, cyclesCount: number, templatesCount: number }) {
  const storageKey = 'review-wizard-collapsed-v1';
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'true'; } catch { return false; }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(storageKey, String(next)); } catch {}
  };

  const activeStep = cyclesCount > activeCyclesCount ? 5 
                  : activeCyclesCount > 0 ? 3
                  : templatesCount > 0 ? 2
                  : 1;

  return (
    <div className="border border-white/10 bg-zinc-950/60 mb-10">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">Review Cycle</span>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 border border-zinc-700 text-zinc-400">
              Step {activeStep} of 5
            </span>
            <span className="text-[10px] text-zinc-600 hidden sm:inline">
              {REVIEW_CYCLE_STEPS[activeStep - 1].title}
            </span>
          </div>
        </div>
        <ChevronDownIcon className={`text-zinc-600 transition-transform duration-200 shrink-0 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      {!collapsed && (
        <div className="border-t border-white/10">
          <div className="relative px-5 pt-5 pb-2 overflow-x-auto no-scrollbar">
            <div className="flex items-start gap-0 min-w-max">
              {REVIEW_CYCLE_STEPS.map((step, idx) => {
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
                        {isComplete ? '✓' : <ReviewCycleIcon icon={step.icon} className="w-4 h-4" />}
                      </div>
                      <div className={`mt-2 text-center text-[10px] font-bold uppercase tracking-wider leading-tight px-1 ${
                        isActive ? 'text-white' : isComplete ? 'text-matcha-400/70' : 'text-zinc-600'
                      }`}>
                        {step.title}
                      </div>
                    </div>
                    {idx < REVIEW_CYCLE_STEPS.length - 1 && (
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
                <ReviewCycleIcon icon={REVIEW_CYCLE_STEPS[activeStep - 1].icon} className="w-5 h-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    {REVIEW_CYCLE_STEPS[activeStep - 1].title}
                  </span>
                  <span className="text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-white/10 text-zinc-400 border border-white/10">
                    Current Step
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed mb-2">
                  {REVIEW_CYCLE_STEPS[activeStep - 1].description}
                </p>
                {REVIEW_CYCLE_STEPS[activeStep - 1].action && (
                  <p className="text-[11px] text-matcha-400/80 font-medium">
                    → {REVIEW_CYCLE_STEPS[activeStep - 1].action}
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

export default function PerformanceReviews() {
  const [activeTab, setActiveTab] = useState<Tab>('cycles');
  const { data: templates, loading: loadingTemplates, error: templatesError, refetch: refetchTemplates } = useReviewTemplates();
  const { data: cycles, loading: loadingCycles, error: cyclesError, refetch: refetchCycles } = useReviewCycles();

  const [selectedCycle, setSelectedCycle] = useState<ReviewCycle | null>(null);
  const [cycleProgress, setCycleProgress] = useState<CycleProgress | null>(null);
  const [loadingProgress, setLoadingProgress] = useState(false);

  const [showCreateCycleModal, setShowCreateCycleModal] = useState(false);
  const [showCreateTemplateModal, setShowCreateTemplateModal] = useState(false);
  const [editingTemplateId, setEditingTemplateId] = useState<string | null>(null);
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

      if (editingTemplateId) {
        await reviewsApi.updateTemplate(editingTemplateId, {
          ...newTemplate,
          is_active: true,
        });
      } else {
        await reviewsApi.createTemplate({
          ...newTemplate,
          is_active: true,
        });
      }

      closeTemplateModal();
      refetchTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : editingTemplateId ? 'Failed to update template' : 'Failed to create template');
    } finally {
      setCreatingTemplate(false);
    }
  };

  const closeTemplateModal = () => {
    setShowCreateTemplateModal(false);
    setEditingTemplateId(null);
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
  };

  const handleEditTemplate = (template: typeof templates[0]) => {
    setEditingTemplateId(template.id);
    setNewTemplate({
      name: template.name,
      description: template.description || '',
      categories: template.categories.map(cat => ({
        id: cat.id as ReturnType<typeof crypto.randomUUID>,
        name: cat.name,
        weight: cat.weight,
        criteria: cat.criteria.map(crit => ({
          id: crit.id as ReturnType<typeof crypto.randomUUID>,
          name: crit.name,
          description: crit.description,
        })),
      })),
    });
    setShowCreateTemplateModal(true);
  };

  const handleDuplicateTemplate = (template: typeof templates[0]) => {
    setEditingTemplateId(null);
    setNewTemplate({
      name: `${template.name} (Copy)`,
      description: template.description || '',
      categories: template.categories.map(cat => ({
        id: crypto.randomUUID(),
        name: cat.name,
        weight: cat.weight,
        criteria: cat.criteria.map(crit => ({
          id: crypto.randomUUID(),
          name: crit.name,
          description: crit.description,
        })),
      })),
    });
    setShowCreateTemplateModal(true);
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

      <ReviewCycleWizard activeCyclesCount={activeCycles.length} cyclesCount={cycles.length} templatesCount={templates.length} />

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
                      subtext={`${cycleProgress.completed} of ${cycleProgress.total_reviews} completed`}
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
                            style={{ width: `${(cycleProgress.completed / cycleProgress.total_reviews) * 100}%` }}
                            title={`${cycleProgress.completed} completed`}
                          />
                        )}
                        {cycleProgress.manager_submitted > 0 && (
                          <div
                            className="bg-purple-500 transition-all duration-500"
                            style={{ width: `${(cycleProgress.manager_submitted / cycleProgress.total_reviews) * 100}%` }}
                            title={`${cycleProgress.manager_submitted} manager submitted`}
                          />
                        )}
                        {cycleProgress.self_submitted > 0 && (
                          <div
                            className="bg-blue-500 transition-all duration-500"
                            style={{ width: `${(cycleProgress.self_submitted / cycleProgress.total_reviews) * 100}%` }}
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
                    <button
                      onClick={() => handleEditTemplate(template)}
                      className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDuplicateTemplate(template)}
                      className="text-xs text-zinc-400 uppercase tracking-wider hover:text-zinc-300 transition-colors"
                    >
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
              <h2 className="text-sm font-bold text-white uppercase tracking-[0.2em]">
                {editingTemplateId ? 'Edit Review Template' : 'Create Review Template'}
              </h2>
              <button
                onClick={closeTemplateModal}
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
                  <div>
                    <label className="text-[10px] uppercase tracking-wider text-zinc-500">
                      Review Categories
                    </label>
                    <p className="text-[9px] text-zinc-600 mt-1">
                      Category weights should total 100%
                    </p>
                  </div>
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
                        <label className="text-[9px] uppercase tracking-wider text-zinc-600 mb-1 block">
                          Weight %
                        </label>
                        <input
                          type="number"
                          value={category.weight}
                          onChange={(e) => updateCategory(category.id, { weight: parseInt(e.target.value) || 0 })}
                          placeholder="0"
                          min="0"
                          max="100"
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
                  onClick={closeTemplateModal}
                  className="flex-1 border border-white/10 text-white py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingTemplate}
                  className="flex-1 bg-white text-black py-2 px-4 text-sm font-medium uppercase tracking-wider hover:bg-zinc-200 transition-colors disabled:opacity-50"
                >
                  {creatingTemplate ? (editingTemplateId ? 'Saving...' : 'Creating...') : (editingTemplateId ? 'Save Template' : 'Create Template')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
