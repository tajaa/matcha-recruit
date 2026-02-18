import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { policies } from '../api/client';
import type { Policy, PolicyStatus } from '../types';
import { ChevronRight, FileText, Plus, Pencil, CheckCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { FeatureGuideTrigger } from '../features/feature-guides';

// ─── Policy Lifecycle Wizard ──────────────────────────────────────────────────

type PolicyStepIcon = 'draft' | 'review' | 'activate' | 'publish' | 'audit';

type PolicyWizardStep = {
  id: number;
  icon: PolicyStepIcon;
  title: string;
  description: string;
  action?: string;
};

const POLICY_CYCLE_STEPS: PolicyWizardStep[] = [
  {
    id: 1,
    icon: 'draft',
    title: 'Draft Policy',
    description: 'Create a new policy or handbook section. Define the title, content, and versioning.',
    action: 'Click "Create Policy" to start your first draft.',
  },
  {
    id: 2,
    icon: 'review',
    title: 'Internal Review',
    description: 'Review the draft with legal or management to ensure compliance and clarity.',
    action: 'Edit your draft until it is ready for activation.',
  },
  {
    id: 3,
    icon: 'activate',
    title: 'Activate',
    description: 'Set the policy to "Active" status. This locks the version and prepares it for distribution.',
    action: 'Use the checkmark button in the list below to activate a draft.',
  },
  {
    id: 4,
    icon: 'publish',
    title: 'Issue & Publish',
    description: 'Publish the policy to the Employee Portal so your team can view and acknowledge it.',
    action: 'Active policies automatically appear in the Portal Guidelines.',
  },
  {
    id: 5,
    icon: 'audit',
    title: 'Audit & Track',
    description: 'Track signature counts and view audit logs of who has acknowledged each policy version.',
    action: 'View the "Signed" column to monitor real-time compliance.',
  },
];

function PolicyCycleIcon({ icon, className = '' }: { icon: PolicyStepIcon; className?: string }) {
  const common = { className, width: 16, height: 16, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true as const };
  
  if (icon === 'draft') {
    return (
      <svg {...common}>
        <path d="M10 6.5V3.5M10 16.5V13.5M13.5 10H16.5M3.5 10H6.5M12.5 7.5L14.5 5.5M5.5 14.5L7.5 12.5M12.5 12.5L14.5 14.5M5.5 5.5L7.5 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="10" r="2.3" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'review') {
    return (
      <svg {...common}>
        <path d="M5 10L8 13L15 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M3 10H5M15 10H17M10 3V5M10 15V17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
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
  if (icon === 'publish') {
    return (
      <svg {...common}>
        <path d="M4 10L10 4L16 10M10 4V16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === 'audit') {
    return (
      <svg {...common}>
        <circle cx="10" cy="8" r="3" stroke="currentColor" strokeWidth="1.6" />
        <path d="M5 16C5 13.5 7.23858 11.5 10 11.5C12.7614 11.5 15 13.5 15 16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M15 8L18 8M2 8L5 8M10 2L10 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  return null;
}

function PolicyCycleWizard({ policiesList }: { policiesList: Policy[] }) {
  const storageKey = 'policy-wizard-collapsed-v1';
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'true'; } catch { return false; }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(storageKey, String(next)); } catch {}
  };

  const activeStep = policiesList.some(p => (p.signed_count || 0) > 0) ? 5 
                  : policiesList.some(p => p.status === 'active') ? 4
                  : policiesList.length > 0 ? 3
                  : 1;

  return (
    <div className="border border-white/10 bg-zinc-950/60 mb-10">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">Policy Lifecycle</span>
          <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 border border-zinc-700 text-zinc-400">
            Step {activeStep} of 5
          </span>
          <span className="text-[10px] text-zinc-600">
            {POLICY_CYCLE_STEPS[activeStep - 1].title}
          </span>
        </div>
        <ChevronDownIcon className={`text-zinc-600 transition-transform duration-200 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      {!collapsed && (
        <div className="border-t border-white/10">
          <div className="relative px-5 pt-5 pb-2 overflow-x-auto">
            <div className="flex items-start gap-0 min-w-max">
              {POLICY_CYCLE_STEPS.map((step, idx) => {
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
                        {isComplete ? '✓' : <PolicyCycleIcon icon={step.icon} className="w-4 h-4" />}
                      </div>
                      <div className={`mt-2 text-center text-[10px] font-bold uppercase tracking-wider leading-tight px-1 ${
                        isActive ? 'text-white' : isComplete ? 'text-matcha-400/70' : 'text-zinc-600'
                      }`}>
                        {step.title}
                      </div>
                    </div>
                    {idx < POLICY_CYCLE_STEPS.length - 1 && (
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
                <PolicyCycleIcon icon={POLICY_CYCLE_STEPS[activeStep - 1].icon} className="w-5 h-5" />
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    {POLICY_CYCLE_STEPS[activeStep - 1].title}
                  </span>
                  <span className="text-[9px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-white/10 text-zinc-400 border border-white/10">
                    Current Step
                  </span>
                </div>
                <p className="text-[11px] text-zinc-400 leading-relaxed mb-2">
                  {POLICY_CYCLE_STEPS[activeStep - 1].description}
                </p>
                {POLICY_CYCLE_STEPS[activeStep - 1].action && (
                  <p className="text-[11px] text-matcha-400/80 font-medium">
                    → {POLICY_CYCLE_STEPS[activeStep - 1].action}
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

export function Policies() {
  const navigate = useNavigate();
  const [policiesList, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<PolicyStatus | ''>('');

  const loadPolicies = useCallback(async (status: PolicyStatus | '' = '') => {
    try {
      setLoading(true);
      const data = await policies.list(status || undefined);
      if (data) {
        setPolicies(data);
      }
    } catch (error) {
      console.error('Failed to load policies:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPolicies(filterStatus);
  }, [filterStatus, loadPolicies]);

  const handleFilterChange = (status: string) => {
    setFilterStatus(status as PolicyStatus | '');
  };

  const handleActivate = async (e: React.MouseEvent, policyId: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm('Activate this policy?')) return;
    try {
      await policies.update(policyId, { status: 'active' });
      loadPolicies(filterStatus);
    } catch (error) {
      console.error('Failed to activate policy:', error);
    }
  };

  const statusColors: Record<PolicyStatus, string> = {
    draft: 'text-zinc-500',
    active: 'text-white',
    archived: 'text-zinc-600',
  };

  const statusDotColors: Record<PolicyStatus, string> = {
    draft: 'bg-zinc-600',
    active: 'bg-white',
    archived: 'bg-zinc-800',
  };

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex justify-between items-start border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Policies</h1>
            <FeatureGuideTrigger guideId="policies" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Company Guidelines & Compliance</p>
        </div>
        <button
          data-tour="policies-create-btn"
          onClick={() => navigate('/app/matcha/policies/new')}
          className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
        >
          <Plus size={14} />
          Create Policy
        </button>
      </div>

      <PolicyCycleWizard policiesList={policiesList} />

      {/* Filter Tabs */}
      <div data-tour="policies-tabs" className="flex gap-8 border-b border-white/10 pb-px">
        {[
          { label: 'All', value: '' },
          { label: 'Active', value: 'active' },
          { label: 'Drafts', value: 'draft' },
          { label: 'Archived', value: 'archived' },
        ].map((tab) => (
          <button
            key={tab.value}
            onClick={() => handleFilterChange(tab.value)}
            className={`pb-3 text-[10px] font-bold uppercase tracking-widest transition-colors border-b-2 ${
              filterStatus === tab.value
                ? 'border-white text-white'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading policies...</div>
        </div>
      ) : policiesList.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
             <FileText size={20} className="text-zinc-600" />
          </div>
          <div className="text-xs text-zinc-500 mb-4 font-mono uppercase tracking-wider">NO POLICIES FOUND</div>
          <button
            onClick={() => navigate('/app/matcha/policies/new')}
            className="text-xs text-white hover:text-zinc-300 font-bold uppercase tracking-wider underline underline-offset-4"
          >
            Create first policy
          </button>
        </div>
      ) : (
        <div data-tour="policies-list" className="space-y-px bg-white/10 border border-white/10">
          {/* List Header */}
          <div className="flex items-center gap-4 py-3 px-4 text-[10px] text-zinc-500 uppercase tracking-widest bg-zinc-950 border-b border-white/10">
            <div className="w-4"></div>
            <div className="flex-1">Policy Title</div>
            <div className="w-24 text-center">Version</div>
            <div className="w-24 text-center">Signed</div>
            <div className="w-32 text-center">Status</div>
            <div className="w-28 text-center">Actions</div>
            <div className="w-8"></div>
          </div>

          {policiesList.map((policy) => (
            <Link 
              key={policy.id} 
              to={`/app/matcha/policies/${policy.id}`}
              className="group flex items-center gap-4 py-4 px-4 cursor-pointer bg-zinc-950 hover:bg-zinc-900 transition-colors"
            >
              <div className="w-4 flex justify-center">
                <div className={`w-1.5 h-1.5 rounded-full ${statusDotColors[policy.status] || 'bg-zinc-700'}`} />
              </div>
              
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-bold text-white truncate group-hover:text-zinc-300 transition-colors">
                  {policy.title}
                </h3>
                {policy.description && (
                  <p className="text-[10px] text-zinc-500 mt-1 truncate max-w-xl font-mono">{policy.description}</p>
                )}
              </div>

              <div className="w-24 text-center text-[10px] font-mono text-zinc-500">
                v{policy.version}
              </div>

              <div className="w-24 text-center">
                <span className="text-[10px] font-mono text-white font-bold">{policy.signed_count || 0}</span>
                <span className="text-[10px] text-zinc-600 uppercase tracking-tighter ml-1">Total</span>
              </div>

              <div className={`w-32 text-center text-[10px] font-bold uppercase tracking-wider ${statusColors[policy.status]}`}>
                {policy.status}
              </div>

              <div className="w-28 flex justify-center gap-2">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    navigate(`/app/matcha/policies/${policy.id}/edit`);
                  }}
                  className="p-1.5 text-zinc-600 hover:text-white hover:bg-white/10 transition-colors rounded"
                  title="Edit policy"
                >
                  <Pencil size={14} />
                </button>
                {policy.status === 'draft' && (
                  <button
                    data-tour="policies-activate-btn"
                    onClick={(e) => handleActivate(e, policy.id)}
                    className="p-1.5 text-emerald-600 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors rounded"
                    title="Activate policy"
                  >
                    <CheckCircle size={14} />
                  </button>
                )}
              </div>

              <div className="w-8 flex justify-center text-zinc-600 group-hover:text-white transition-colors">
                <ChevronRight size={14} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default Policies;
