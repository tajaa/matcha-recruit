import { useState, useMemo, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { BusinessLocation, ComplianceRequirement, LocationCreate, JurisdictionOption } from '../api/compliance';
import {
    complianceAPI,
    COMPLIANCE_CATEGORY_LABELS,
    JURISDICTION_LEVEL_LABELS
} from '../api/compliance';
import { adminOverview, api } from '../api/client';
import type { AvailablePoster, PosterOrder } from '../types';
import { useAuth } from '../context/AuthContext';
import {
    MapPin, Plus, Trash2, Edit2, X,
    ChevronDown, AlertTriangle, Bell, CheckCircle,
    ExternalLink, Building2, Loader2, Clock, Calendar,
    History, Eye, Zap, Info, ShieldCheck
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { FeatureGuideTrigger } from '../features/feature-guides';

function linkifyText(text: string) {
    const splitRegex = /(https?:\/\/[^\s,)]+)/g;
    const parts = text.split(splitRegex);
    if (parts.length === 1) return text;
    return parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
            <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-emerald-400 hover:text-emerald-300 underline decoration-emerald-500/20 underline-offset-2">{part}</a>
        ) : part
    );
}

const US_STATES = [
    { value: 'AL', label: 'Alabama' }, { value: 'AK', label: 'Alaska' },
    { value: 'AZ', label: 'Arizona' }, { value: 'AR', label: 'Arkansas' },
    { value: 'CA', label: 'California' }, { value: 'CO', label: 'Colorado' },
    { value: 'CT', label: 'Connecticut' }, { value: 'DE', label: 'Delaware' },
    { value: 'FL', label: 'Florida' }, { value: 'GA', label: 'Georgia' },
    { value: 'HI', label: 'Hawaii' }, { value: 'ID', label: 'Idaho' },
    { value: 'IL', label: 'Illinois' }, { value: 'IN', label: 'Indiana' },
    { value: 'IA', label: 'Iowa' }, { value: 'KS', label: 'Kansas' },
    { value: 'KY', label: 'Kentucky' }, { value: 'LA', label: 'Louisiana' },
    { value: 'ME', label: 'Maine' }, { value: 'MD', label: 'Maryland' },
    { value: 'MA', label: 'Massachusetts' }, { value: 'MI', label: 'Michigan' },
    { value: 'MN', label: 'Minnesota' }, { value: 'MS', label: 'Mississippi' },
    { value: 'MO', label: 'Missouri' }, { value: 'MT', label: 'Montana' },
    { value: 'NE', label: 'Nebraska' }, { value: 'NV', label: 'Nevada' },
    { value: 'NH', label: 'New Hampshire' }, { value: 'NJ', label: 'New Jersey' },
    { value: 'NM', label: 'New Mexico' }, { value: 'NY', label: 'New York' },
    { value: 'NC', label: 'North Carolina' }, { value: 'ND', label: 'North Dakota' },
    { value: 'OH', label: 'Ohio' }, { value: 'OK', label: 'Oklahoma' },
    { value: 'OR', label: 'Oregon' }, { value: 'PA', label: 'Pennsylvania' },
    { value: 'RI', label: 'Rhode Island' }, { value: 'SC', label: 'South Carolina' },
    { value: 'SD', label: 'South Dakota' }, { value: 'TN', label: 'Tennessee' },
    { value: 'TX', label: 'Texas' }, { value: 'UT', label: 'Utah' },
    { value: 'VT', label: 'Vermont' }, { value: 'VA', label: 'Virginia' },
    { value: 'WA', label: 'Washington' }, { value: 'WV', label: 'West Virginia' },
    { value: 'WI', label: 'Wisconsin' }, { value: 'WY', label: 'Wyoming' },
    { value: 'DC', label: 'Washington D.C.' }
];

interface LocationFormData {
    name: string;
    address: string;
    city: string;
    state: string;
    county: string;
    zipcode: string;
    jurisdictionKey: string;
}

const emptyFormData: LocationFormData = {
    name: '',
    address: '',
    city: '',
    state: '',
    county: '',
    zipcode: '',
    jurisdictionKey: ''
};

const REQUIREMENT_CATEGORY_ORDER = [
    'meal_breaks',
    'minimum_wage',
    'overtime',
    'pay_frequency',
    'sick_leave',
    'final_pay',
    'minor_work_permit',
    'scheduling_reporting',
    'workers_comp',
    'business_license',
    'tax_rate',
    'posting_requirements',
];

const CORE_REQUIREMENT_SECTIONS = [
    'meal_breaks',
    'minimum_wage',
    'overtime',
    'pay_frequency',
    'sick_leave',
    'final_pay',
    'minor_work_permit',
    'scheduling_reporting',
];

const RATE_TYPE_LABELS: Record<string, string> = {
    general: 'General',
    tipped: 'Tipped / Tip Credit',
    exempt_salary: 'Exempt Salary',
    hotel: 'Hotel',
    fast_food: 'Fast Food',
    healthcare: 'Healthcare',
    large_employer: 'Large Employer',
    small_employer: 'Small Employer',
};

function normalizeCategoryKey(category: string): string {
    return category.trim().toLowerCase().replace(/[\s-]+/g, '_');
}

function getRequirementEmptyStateCopy(category: string): string {
    switch (category) {
        case 'minimum_wage':
            return 'Coverage pending. This section should include general minimum wage, tipped/tip-credit treatment, and the exempt salary threshold.';
        case 'final_pay':
            return 'Coverage pending. This section should capture final pay timing for voluntary and involuntary separations, including payout rules for accrued sick/vacation balances.';
        case 'minor_work_permit':
            return 'Coverage pending. This section should capture minor work permit/certificate requirements and any age- or hour-based limits.';
        case 'scheduling_reporting':
            return 'No scheduling/reporting-time ordinance has been detected yet for this location. If local fair-workweek or reporting-time pay rules apply, they will appear here.';
        default:
            return 'No active requirements detected for this section yet.';
    }
}

// ─── Compliance Lifecycle Wizard ──────────────────────────────────────────────

type ComplianceStepIcon = 'locations' | 'research' | 'alerts' | 'posters' | 'audit';

type ComplianceWizardStep = {
  id: number;
  icon: ComplianceStepIcon;
  title: string;
  description: string;
  action?: string;
};

const COMPLIANCE_CYCLE_STEPS: ComplianceWizardStep[] = [
  {
    id: 1,
    icon: 'locations',
    title: 'Locations',
    description: 'Map applicable laws by pinning business sites.',
    action: 'Click "Add Location" to register a site.',
  },
  {
    id: 2,
    icon: 'research',
    title: 'Research',
    description: 'AI scans federal, state, and local ordinances.',
    action: 'Select a location and click "Check for Updates".',
  },
  {
    id: 3,
    icon: 'alerts',
    title: 'Monitor',
    description: 'Track changes and detected requirements.',
    action: 'Review the "Alerts" tab for attention items.',
  },
  {
    id: 4,
    icon: 'posters',
    title: 'Posters',
    description: 'Order or download mandatory compliance signage.',
    action: 'Navigate to "Posters" for downloads.',
  },
  {
    id: 5,
    icon: 'audit',
    title: 'Audit',
    description: 'Maintain verifiable records of all checks.',
    action: 'View the "Log" for a full audit trail.',
  },
];

function ComplianceCycleIcon({ icon, className = '' }: { icon: ComplianceStepIcon; className?: string }) {
  const common = { className, width: 14, height: 14, viewBox: '0 0 20 20', fill: 'none', 'aria-hidden': true as const };
  
  if (icon === 'locations') {
    return (
      <svg {...common}>
        <path d="M10 17C10 17 4 11 4 7C4 3.68629 6.68629 1 10 1C13.3137 1 16 3.68629 16 7C16 11 10 17 10 17Z" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="10" cy="7" r="2" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'research') {
    return (
      <svg {...common}>
        <path d="M10 6.5V3.5M10 16.5V13.5M13.5 10H16.5M3.5 10H6.5M12.5 7.5L14.5 5.5M5.5 14.5L7.5 12.5M12.5 12.5L14.5 14.5M5.5 5.5L7.5 7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="10" r="2.3" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    );
  }
  if (icon === 'alerts') {
    return (
      <svg {...common}>
        <path d="M10 3V17M3 10H17M14.5 5.5L5.5 14.5M14.5 14.5L5.5 5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'posters') {
    return (
      <svg {...common}>
        <rect x="5" y="4" width="10" height="12" rx="1" stroke="currentColor" strokeWidth="1.6" />
        <path d="M7 7H13M7 10H13M7 13H10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (icon === 'audit') {
    return (
      <svg {...common}>
        <path d="M4 10L8 14L16 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return null;
}

function ComplianceCycleWizard({ locations, alerts }: { locations?: BusinessLocation[], alerts?: any[] }) {
  const storageKey = 'compliance-wizard-collapsed-v1';
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(storageKey) === 'true'; } catch { return false; }
  });

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem(storageKey, String(next)); } catch {}
  };

  const activeStep = (alerts && alerts.length > 0) ? 3
                  : (locations && locations.some(l => (l.requirements_count || 0) > 0)) ? 2
                  : (locations && locations.length > 0) ? 2
                  : 1;

  return (
    <div className="border border-white/5 bg-zinc-900/30 rounded-sm overflow-hidden mb-8 shadow-sm">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-4">
          <span className="text-[9px] font-bold uppercase tracking-[0.25em] text-zinc-500 font-mono">System Lifecycle</span>
          <div className="flex items-center gap-2">
            <span className="px-1.5 py-0.5 text-[8px] font-mono font-bold uppercase tracking-widest bg-zinc-800 border border-white/5 text-zinc-400">
              Stage 0{activeStep}
            </span>
            <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-600 hidden sm:inline">
              {COMPLIANCE_CYCLE_STEPS[activeStep - 1].title}
            </span>
          </div>
        </div>
        <ChevronDownIcon className={`text-zinc-600 transition-transform duration-300 ${collapsed ? '' : 'rotate-180'}`} />
      </button>

      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="border-t border-white/5 overflow-hidden"
          >
            <div className="px-4 py-6">
              <div className="flex items-start justify-between gap-8 mb-6 overflow-x-auto no-scrollbar pb-2">
                {COMPLIANCE_CYCLE_STEPS.map((step, idx) => {
                  const isComplete = step.id < activeStep;
                  const isActive = step.id === activeStep;

                  return (
                    <div key={step.id} className="flex items-center gap-4 group flex-shrink-0">
                      <div className="flex flex-col items-center">
                        <div className={`relative w-8 h-8 rounded-full border flex items-center justify-center transition-all duration-500 ${
                          isComplete
                            ? 'bg-matcha-500/10 border-matcha-500/30 text-matcha-500'
                            : isActive
                            ? 'bg-white/5 border-white/20 text-white shadow-[0_0_15px_rgba(255,255,255,0.05)]'
                            : 'bg-zinc-900 border-white/5 text-zinc-700'
                        }`}>
                          {isComplete ? <CheckCircle size={14} strokeWidth={2.5} /> : <ComplianceCycleIcon icon={step.icon} />}
                        </div>
                        <span className={`mt-2 text-[8px] font-bold uppercase tracking-[0.15em] ${
                          isActive ? 'text-white' : isComplete ? 'text-matcha-500/60' : 'text-zinc-700'
                        }`}>
                          {step.title}
                        </span>
                      </div>
                      {idx < COMPLIANCE_CYCLE_STEPS.length - 1 && (
                        <div className={`w-8 h-px transition-colors duration-700 ${
                          step.id < activeStep ? 'bg-matcha-500/20' : 'bg-white/5'
                        }`} />
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="p-4 bg-zinc-950/40 border border-white/5 rounded-sm">
                <div className="flex items-start gap-4">
                  <div className="p-2 bg-white/5 rounded-sm text-zinc-400">
                    <ComplianceCycleIcon icon={COMPLIANCE_CYCLE_STEPS[activeStep - 1].icon} className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <h4 className="text-[10px] font-bold text-white uppercase tracking-widest">
                        {COMPLIANCE_CYCLE_STEPS[activeStep - 1].title}
                      </h4>
                      <span className="text-[7px] px-1.5 py-0.5 font-bold uppercase tracking-widest bg-matcha-500/10 text-matcha-500 border border-matcha-500/20 rounded-xs">
                        Active Stage
                      </span>
                    </div>
                    <p className="text-[11px] text-zinc-500 leading-relaxed">
                      {COMPLIANCE_CYCLE_STEPS[activeStep - 1].description}
                    </p>
                    {COMPLIANCE_CYCLE_STEPS[activeStep - 1].action && (
                      <p className="text-[10px] text-zinc-400 font-mono mt-2 opacity-80">
                        <span className="text-matcha-500">→</span> {COMPLIANCE_CYCLE_STEPS[activeStep - 1].action}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
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

export function Compliance() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const isClient = user?.role === 'client';
    const isAdmin = user?.role === 'admin';
    const queryClient = useQueryClient();
    const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
    const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);
    const [jurisdictionSearch, setJurisdictionSearch] = useState('');
    const [showAddModal, setShowAddModal] = useState(false);
    const [editingLocation, setEditingLocation] = useState<BusinessLocation | null>(null);
    const [formData, setFormData] = useState<LocationFormData>(emptyFormData);
    const [useManualEntry, setUseManualEntry] = useState(false);
    const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
    const [activeTab, setActiveTab] = useState<'requirements' | 'alerts' | 'upcoming' | 'history' | 'posters'>('requirements');
    const [checkInProgress, setCheckInProgress] = useState(false);
    const [checkMessages, setCheckMessages] = useState<{ type: string; status?: string; message?: string; location?: string; new?: number; updated?: number; alerts?: number }[]>([]);
    const [expandedAlertSources, setExpandedAlertSources] = useState<Set<string>>(new Set());
    const [availablePosters, setAvailablePosters] = useState<AvailablePoster[]>([]);
    const [posterOrders, setPosterOrders] = useState<PosterOrder[]>([]);
    const [postersLoading, setPostersLoading] = useState(false);
    const [posterOrderLoading, setPosterOrderLoading] = useState<string | null>(null);

    const wizardReturnPath = useMemo(() => {
        const rawPath = searchParams.get('return_to');
        if (!rawPath) return null;
        const normalized = rawPath.trim();
        if (!normalized.startsWith('/app/matcha/')) return null;
        return normalized;
    }, [searchParams]);

    const syncStates = useMemo(() => {
        const raw = searchParams.get('sync_states');
        if (!raw || !wizardReturnPath) return new Set<string>();
        return new Set(raw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean));
    }, [searchParams, wizardReturnPath]);

    const { data: companies } = useQuery({
        queryKey: ['admin-overview'],
        queryFn: () => adminOverview.get(),
        enabled: isAdmin,
    });

    useEffect(() => {
        if (isAdmin && companies?.companies?.length && !selectedCompanyId) {
            setSelectedCompanyId(companies.companies[0].id);
        }
    }, [isAdmin, companies, selectedCompanyId]);

    const companyId = isAdmin ? selectedCompanyId ?? undefined : undefined;

    const { data: locations, isLoading: loadingLocations } = useQuery({
        queryKey: ['compliance-locations', companyId],
        queryFn: () => complianceAPI.getLocations(companyId),
        enabled: !isAdmin || !!companyId,
    });

    useEffect(() => {
        setSelectedLocationId(null);
    }, [companyId]);

    // Load poster data when tab becomes active
    useEffect(() => {
        if (activeTab !== 'posters') return;
        const loadPosters = async () => {
            setPostersLoading(true);
            try {
                const [postersData, ordersData] = await Promise.all([
                    api.posters.getAvailable(),
                    api.posters.listOrders(),
                ]);
                setAvailablePosters(postersData);
                setPosterOrders(ordersData.orders);
            } catch (err) {
                console.error('Failed to load posters:', err);
            } finally {
                setPostersLoading(false);
            }
        };
        loadPosters();
    }, [activeTab]);

    const { data: requirements, isLoading: loadingRequirements } = useQuery({
        queryKey: ['compliance-requirements', selectedLocationId, companyId],
        queryFn: () => selectedLocationId ? complianceAPI.getRequirements(selectedLocationId, undefined, companyId) : Promise.resolve([]),
        enabled: !!selectedLocationId
    });

    const { data: alerts, isLoading: loadingAlerts } = useQuery({
        queryKey: ['compliance-alerts', companyId],
        queryFn: () => complianceAPI.getAlerts(undefined, companyId),
        enabled: !isAdmin || !!companyId,
    });

    const { data: upcomingLegislation } = useQuery({
        queryKey: ['compliance-upcoming', selectedLocationId, companyId],
        queryFn: () => selectedLocationId ? complianceAPI.getUpcomingLegislation(selectedLocationId, companyId) : Promise.resolve([]),
        enabled: !!selectedLocationId
    });

    const { data: checkLog } = useQuery({
        queryKey: ['compliance-check-log', selectedLocationId, companyId],
        queryFn: () => selectedLocationId ? complianceAPI.getCheckLog(selectedLocationId, 10, companyId) : Promise.resolve([]),
        enabled: !!selectedLocationId
    });

    const showJurisdictionPicker = (isClient || isAdmin) && !editingLocation && !useManualEntry;

    const { data: jurisdictions } = useQuery({
        queryKey: ['compliance-jurisdictions'],
        queryFn: complianceAPI.getJurisdictions,
        enabled: isClient || isAdmin,
    });

    const jurisdictionsByState = useMemo(() => {
        if (!jurisdictions) return {};
        const grouped: Record<string, JurisdictionOption[]> = {};
        for (const j of jurisdictions) {
            if (!grouped[j.state]) grouped[j.state] = [];
            grouped[j.state].push(j);
        }
        return grouped;
    }, [jurisdictions]);

    const filteredJurisdictions = useMemo(() => {
        if (!jurisdictions) return {};
        const search = jurisdictionSearch.toLowerCase().trim();
        if (!search) return jurisdictionsByState;
        const filtered: Record<string, JurisdictionOption[]> = {};
        for (const [state, items] of Object.entries(jurisdictionsByState)) {
            const stateLabel = US_STATES.find(s => s.value === state)?.label || state;
            const matches = items.filter(j =>
                j.city.toLowerCase().includes(search) ||
                state.toLowerCase().includes(search) ||
                stateLabel.toLowerCase().includes(search)
            );
            if (matches.length > 0) filtered[state] = matches;
        }
        return filtered;
    }, [jurisdictions, jurisdictionSearch, jurisdictionsByState]);

    const makeJurisdictionKey = (j: JurisdictionOption) => `${j.city}|${j.state}|${j.county || ''}`;

    const createLocationMutation = useMutation({
        mutationFn: (data: LocationCreate) => complianceAPI.createLocation(data, companyId),
        onSuccess: (newLocation) => {
            queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
            queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
            setShowAddModal(false);
            setFormData(emptyFormData);
            setUseManualEntry(false);
            setSelectedLocationId(newLocation.id);
        }
    });

    const updateLocationMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: LocationCreate }) => complianceAPI.updateLocation(id, data, companyId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
            setEditingLocation(null);
            setFormData(emptyFormData);
        }
    });

    const deleteLocationMutation = useMutation({
        mutationFn: (id: string) => complianceAPI.deleteLocation(id, companyId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
            queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
            if (selectedLocationId === deleteLocationMutation.variables) {
                setSelectedLocationId(null);
            }
        }
    });

    const markAlertReadMutation = useMutation({
        mutationFn: (id: string) => complianceAPI.markAlertRead(id, companyId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-alerts', companyId] });
            queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
        }
    });

    const dismissAlertMutation = useMutation({
        mutationFn: (id: string) => complianceAPI.dismissAlert(id, companyId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-alerts', companyId] });
            queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
        }
    });

    const requirementsByCategory = useMemo(() => {
        if (!requirements) return {};
        return requirements.reduce((acc, req) => {
            const category = normalizeCategoryKey(req.category || 'other');
            if (!acc[category]) acc[category] = [];
            acc[category].push({ ...req, category });
            return acc;
        }, {} as Record<string, ComplianceRequirement[]>);
    }, [requirements]);

    const orderedRequirementCategories = useMemo(() => {
        const orderIndex = new Map(REQUIREMENT_CATEGORY_ORDER.map((cat, idx) => [cat, idx]));
        const categories = new Set(Object.keys(requirementsByCategory));
        CORE_REQUIREMENT_SECTIONS.forEach(category => categories.add(category));

        return Array.from(categories)
            .sort((a, b) => {
                const aIdx = orderIndex.get(a);
                const bIdx = orderIndex.get(b);
                if (aIdx !== undefined && bIdx !== undefined) return aIdx - bIdx;
                if (aIdx !== undefined) return -1;
                if (bIdx !== undefined) return 1;
                return a.localeCompare(b);
            })
            .map((category) => [category, requirementsByCategory[category] || []] as [string, ComplianceRequirement[]]);
    }, [requirementsByCategory]);

    const toggleCategory = (category: string) => {
        setExpandedCategories(prev => {
            const next = new Set(prev);
            if (next.has(category)) {
                next.delete(category);
            } else {
                next.add(category);
            }
            return next;
        });
    };

    const handleSubmitLocation = (e: React.FormEvent) => {
        e.preventDefault();
        if (!formData.city || !formData.state) return;
        if (!isClient && !isAdmin && !formData.zipcode) return;

        const data: LocationCreate = {
            name: formData.name || undefined,
            address: formData.address || undefined,
            city: formData.city,
            state: formData.state,
            county: formData.county || undefined,
            zipcode: formData.zipcode || undefined,
        };

        if (editingLocation) {
            updateLocationMutation.mutate({ id: editingLocation.id, data });
        } else {
            createLocationMutation.mutate(data);
        }
    };

    const openEditModal = (location: BusinessLocation) => {
        setEditingLocation(location);
        setJurisdictionSearch('');
        setFormData({
            name: location.name || '',
            address: location.address || '',
            city: location.city,
            state: location.state,
            county: location.county || '',
            zipcode: location.zipcode,
            jurisdictionKey: `${location.city}|${location.state}|${location.county || ''}`,
        });
    };

    const getCategoryJurisdiction = (reqs: ComplianceRequirement[]) => {
        const hasCityLevel = reqs.some(r => r.jurisdiction_level === 'city');
        if (hasCityLevel) {
            const cityReq = reqs.find(r => r.jurisdiction_level === 'city');
            return { label: `${cityReq?.jurisdiction_name} Local`, type: 'local' as const };
        }
        const hasCountyLevel = reqs.some(r => r.jurisdiction_level === 'county');
        if (hasCountyLevel) {
            const countyReq = reqs.find(r => r.jurisdiction_level === 'county');
            return { label: countyReq?.jurisdiction_name ?? 'County', type: 'county' as const };
        }
        const stateReq = reqs.find(r => r.jurisdiction_level === 'state');
        return { label: stateReq?.jurisdiction_name ?? 'State', type: 'state' as const };
    };

    const getSeverityStyles = (severity: string) => {
        switch (severity) {
            case 'critical':
                return 'bg-red-500/10 text-red-400 border-red-500/20';
            case 'warning':
                return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
            default:
                return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
        }
    };

    const toggleAlertSources = (alertId: string) => {
        setExpandedAlertSources(prev => {
            const next = new Set(prev);
            if (next.has(alertId)) next.delete(alertId);
            else next.add(alertId);
            return next;
        });
    };

    const getConfidenceBadge = (score: number | null) => {
        if (score === null || score === undefined) return null;
        const pct = Math.round(score * 100);
        if (score >= 0.6) return { label: `${pct}%`, color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30', tag: 'Verified' };
        if (score >= 0.3) return { label: `${pct}%`, color: 'bg-amber-500/20 text-amber-400 border-amber-500/30', tag: 'Unverified' };
        return { label: `${pct}%`, color: 'bg-red-500/20 text-red-400 border-red-500/30', tag: 'Low Confidence' };
    };

    const getAlertTypeIcon = (alertType: string | null) => {
        switch (alertType) {
            case 'upcoming_legislation': return <Calendar size={14} className="text-purple-400" />;
            case 'deadline_approaching': return <Clock size={14} className="text-red-400" />;
            case 'new_requirement': return <Zap size={14} className="text-blue-400" />;
            default: return <AlertTriangle size={14} />;
        }
    };

    const selectedLocation = locations?.find(l => l.id === selectedLocationId);
    const locationAlerts = alerts?.filter(a => a.location_id === selectedLocationId && a.status !== 'dismissed') || [];
    const unreadAlertsCount = locationAlerts.filter(a => a.status === 'unread').length;

    return (
        <div className="max-w-7xl mx-auto space-y-10 pb-24">
            <div className="flex items-center justify-between border-b border-white/5 pb-8">
                <div className="flex items-center gap-8">
                    <div>
                        <div className="flex items-center gap-3">
                            <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Compliance</h1>
                            <FeatureGuideTrigger guideId="compliance" />
                        </div>
                        <div className="flex items-center gap-2 mt-2">
                            <ShieldCheck size={12} className="text-matcha-500" />
                            <p className="text-[10px] text-zinc-500 font-mono tracking-widest uppercase">
                                Algorithmic Enforcement Node
                            </p>
                        </div>
                    </div>
                    {isAdmin && companies?.companies && companies.companies.length > 0 && (
                        <div className="flex flex-col gap-1.5 pl-8 border-l border-white/5">
                            <span className="text-[8px] font-bold uppercase tracking-widest text-zinc-600">Company Context</span>
                            <select
                                data-tour="compliance-company-select"
                                value={selectedCompanyId || ''}
                                onChange={e => setSelectedCompanyId(e.target.value)}
                                className="bg-zinc-950 border border-white/5 text-white text-[10px] font-mono uppercase tracking-[0.2em] focus:outline-none focus:border-white/20 transition-all px-3 py-1.5 rounded-sm min-w-[220px]"
                            >
                                {companies.companies.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                        </div>
                    )}
                </div>
                <div className="flex items-center gap-3">
                    {wizardReturnPath && (
                        <button
                            onClick={() => navigate(wizardReturnPath)}
                            className="px-5 py-2.5 border border-white/5 text-zinc-400 hover:text-white hover:bg-white/5 text-[10px] font-bold uppercase tracking-[0.2em] transition-all rounded-sm"
                        >
                            Return To Handbook
                        </button>
                    )}
                    <button
                        data-tour="compliance-add-btn"
                        onClick={() => {
                            setFormData(emptyFormData);
                            setEditingLocation(null);
                            setJurisdictionSearch('');
                            setShowAddModal(true);
                        }}
                        className="flex items-center gap-2 px-6 py-2.5 bg-white text-black hover:bg-[#4ADE80] text-[10px] font-bold uppercase tracking-[0.2em] transition-all rounded-sm shadow-xl"
                    >
                        <Plus size={14} />
                        Add Location
                    </button>
                </div>
            </div>

            <ComplianceCycleWizard locations={locations} alerts={alerts} />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                <div data-tour="compliance-locations" className="lg:col-span-1 space-y-6">
                    <div className="flex items-center justify-between border-b border-white/5 pb-2">
                        <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.25em]">
                            Endpoints
                        </h2>
                        <span className="text-[9px] font-mono text-zinc-700">[{locations?.length || 0}]</span>
                    </div>

                    {syncStates.size > 0 && (
                        <div className="border border-amber-500/30 bg-amber-500/10 px-4 py-3 rounded-sm text-xs text-amber-200 space-y-1">
                            <p className="font-medium uppercase tracking-wider">Handbook requires compliance sync</p>
                            <p>
                                Run <strong>Sync Compliance</strong> for each highlighted location below, then return to your handbook.
                            </p>
                        </div>
                    )}

                    {syncStates.size > 0 && (() => {
                        const coveredStates = new Set((locations || []).map(l => (l.state || '').toUpperCase()));
                        const missingStates = [...syncStates].filter(s => !coveredStates.has(s));
                        if (missingStates.length === 0) return null;
                        return (
                            <div className="border border-red-500/30 bg-red-500/10 px-4 py-3 rounded-sm text-xs text-red-200 space-y-1 mt-2">
                                <p className="font-medium uppercase tracking-wider">Location required for compliance sync</p>
                                <p>
                                    Add a location in <strong>{missingStates.join(', ')}</strong> to your compliance dashboard,
                                    then run <strong>Sync Compliance</strong> to populate handbook coverage data.{' '}
                                    <button
                                        onClick={() => setShowAddModal(true)}
                                        className="underline underline-offset-2 decoration-red-400/50 hover:text-red-100 transition-colors"
                                    >
                                        Add Location
                                    </button>
                                </p>
                            </div>
                        );
                    })()}

                    {loadingLocations ? (
                        <div className="space-y-2">
                            {[1, 2, 3].map(i => (
                                <div key={i} className="bg-zinc-900/40 border border-white/5 rounded-sm p-4 animate-pulse h-20" />
                            ))}
                        </div>
                    ) : locations?.length === 0 ? (
                        <div className="bg-zinc-900/20 border border-dashed border-white/5 rounded-sm py-16 px-8 text-center">
                            <div className="w-12 h-12 mx-auto mb-6 rounded-full bg-zinc-900 border border-white/5 flex items-center justify-center opacity-40">
                                <MapPin size={20} className="text-zinc-500" />
                            </div>
                            <h3 className="text-zinc-400 text-[10px] font-bold uppercase tracking-widest mb-2">Zero Endpoints</h3>
                            <p className="text-zinc-600 text-[10px] mb-6 leading-relaxed uppercase tracking-tighter">
                                Register business locations to initialize monitoring.
                            </p>
                            <button
                                onClick={() => setShowAddModal(true)}
                                className="text-white text-[10px] font-bold hover:text-[#4ADE80] uppercase tracking-[0.2em] underline underline-offset-8 decoration-white/10"
                            >
                                Register First Node
                            </button>
                        </div>
                    ) : (
                    <div className="space-y-1.5">
                        {locations?.map(location => (
                            <motion.div
                                layout
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                key={location.id}
                                onClick={() => setSelectedLocationId(location.id)}
                                className={`border rounded-sm p-3.5 cursor-pointer transition-all duration-300 group relative overflow-hidden ${
                                    selectedLocationId === location.id
                                        ? 'border-matcha-500/40 bg-matcha-500/[0.03] shadow-[0_0_20px_rgba(0,0,0,0.4)]'
                                        : syncStates.has((location.state || '').toUpperCase())
                                            ? 'border-amber-500/40 bg-amber-500/[0.04] hover:border-amber-500/60'
                                            : 'border-white/5 bg-zinc-900/40 hover:border-white/10 hover:bg-zinc-900/60'
                                }`}
                            >
                                {selectedLocationId === location.id && (
                                    <motion.div 
                                        layoutId="active-location-indicator"
                                        className="absolute left-0 top-0 bottom-0 w-0.5 bg-matcha-500" 
                                    />
                                )}
                                <div className="flex items-start justify-between">
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2">
                                            <h3 className={`font-bold text-xs truncate uppercase tracking-widest ${
                                                selectedLocationId === location.id ? 'text-white' : 'text-zinc-400'
                                            }`}>
                                                {location.name || `${location.city}, ${location.state}`}
                                            </h3>
                                            {location.has_local_ordinance && (
                                                <span className="text-[7px] px-1 py-0.5 bg-white/5 text-zinc-500 border border-white/10 rounded-xs uppercase tracking-widest">Local</span>
                                            )}
                                        </div>
                                        <p className="text-zinc-600 text-[10px] truncate mt-1 font-mono uppercase tracking-tighter">
                                            {location.city}, {location.state} {location.zipcode}
                                        </p>
                                        <div className="flex items-center gap-4 mt-3">
                                            <span className="text-[9px] font-bold uppercase tracking-[0.15em] text-zinc-500/80">
                                                {location.requirements_count} Nodes
                                            </span>
                                            {location.unread_alerts_count > 0 && (
                                                <span className="text-amber-500 flex items-center gap-1 text-[9px] font-bold uppercase tracking-[0.15em] animate-pulse">
                                                    <Bell size={8} />
                                                    {location.unread_alerts_count} Alerts
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                openEditModal(location);
                                                setShowAddModal(true);
                                            }}
                                            className="p-1.5 text-zinc-600 hover:text-white rounded transition-colors"
                                            title="Edit"
                                        >
                                            <Edit2 size={11} />
                                        </button>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (confirm('Delete this location?')) {
                                                    deleteLocationMutation.mutate(location.id);
                                                }
                                            }}
                                            className="p-1.5 text-zinc-600 hover:text-red-500 rounded transition-colors"
                                            title="Delete"
                                        >
                                            <Trash2 size={11} />
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                    )}
                </div>

                <div data-tour="compliance-content" className="lg:col-span-2">
                    {selectedLocationId && selectedLocation ? (
                        <div className="bg-zinc-900/20 border border-white/5 rounded-sm overflow-hidden min-h-[600px] flex flex-col shadow-2xl">
                            <div className="p-6 md:p-8 border-b border-white/5 bg-zinc-900/40">
                                <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                                    <div className="flex items-center gap-5">
                                        <div className="w-12 h-12 rounded-sm bg-white/5 border border-white/10 flex items-center justify-center shadow-inner">
                                            <Building2 size={24} className="text-zinc-400" />
                                        </div>
                                        <div>
                                            <h2 className="text-xl font-bold text-white uppercase tracking-tighter">
                                                {selectedLocation.name || `${selectedLocation.city}, ${selectedLocation.state}`}
                                            </h2>
                                            <div className="flex items-center gap-3 mt-1.5">
                                                <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-widest">
                                                    {selectedLocation.city}, {selectedLocation.state} {selectedLocation.zipcode}
                                                </span>
                                                {selectedLocation.last_compliance_check && (
                                                    <>
                                                        <div className="w-1 h-1 rounded-full bg-white/10" />
                                                        <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest">
                                                            Last Sync: {new Date(selectedLocation.last_compliance_check).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                                        </span>
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <button
                                        disabled={checkInProgress}
                                        onClick={async () => {
                                            if (!selectedLocationId || checkInProgress) return;
                                            setCheckInProgress(true);
                                            setCheckMessages([]);
                                            try {
                                                const response = await complianceAPI.checkCompliance(selectedLocationId, companyId);
                                                const reader = response.body?.getReader();
                                                if (!reader) throw new Error('No response body');
                                                const decoder = new TextDecoder();
                                                let buffer = '';
                                                while (true) {
                                                    const { done, value } = await reader.read();
                                                    if (done) break;
                                                    buffer += decoder.decode(value, { stream: true });
                                                    const lines = buffer.split('\n');
                                                    buffer = lines.pop() || '';
                                                    for (const line of lines) {
                                                        const trimmed = line.trim();
                                                        if (!trimmed.startsWith('data: ')) continue;
                                                        const payload = trimmed.slice(6);
                                                        if (payload === '[DONE]') continue;
                                                        try {
                                                            const event = JSON.parse(payload);
                                                            setCheckMessages(prev => [...prev, event]);
                                                        } catch { /* skip malformed */ }
                                                    }
                                                }
                                                queryClient.invalidateQueries({ queryKey: ['compliance-requirements', selectedLocationId, companyId] });
                                                queryClient.invalidateQueries({ queryKey: ['compliance-alerts', companyId] });
                                                queryClient.invalidateQueries({ queryKey: ['compliance-locations', companyId] });
                                                queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
                                            } catch (error) {
                                                console.error('Compliance check failed:', error);
                                                setCheckMessages(prev => [...prev, { type: 'error', message: 'Failed to run compliance check' }]);
                                            } finally {
                                                setCheckInProgress(false);
                                            }
                                        }}
                                        className="relative group px-6 py-3 bg-white text-black text-[10px] font-bold uppercase tracking-[0.2em] transition-all duration-500 hover:bg-[#4ADE80] disabled:opacity-50 overflow-hidden rounded-sm"
                                    >
                                        <div className="relative z-10 flex items-center gap-2">
                                            {checkInProgress ? (
                                                <><Loader2 size={12} className="animate-spin" /> Initializing Scan</>
                                            ) : (
                                                <><Zap size={12} /> Sync Compliance</>
                                            )}
                                        </div>
                                    </button>
                                </div>
                            </div>

                            {checkMessages.length > 0 && (
                                <motion.div 
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    className="border-b border-white/5 bg-black/40 overflow-hidden"
                                >
                                    <div className="flex items-center gap-4 px-8 py-3 border-b border-white/5 text-[8px] uppercase tracking-[0.3em] font-bold text-zinc-600">
                                        <div className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]" /> New</div>
                                        <div className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-amber-500" /> Delta</div>
                                        <div className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-zinc-700" /> Nominal</div>
                                    </div>
                                    <div className="px-8 py-4 space-y-2 max-h-48 overflow-y-auto font-mono">
                                        {checkMessages.map((msg, i) => (
                                            <div key={i} className="flex items-start gap-3 text-[10px] leading-relaxed">
                                                {msg.type === 'result' ? (
                                                    <span className={`flex-shrink-0 mt-0.5 px-1.5 py-0.5 rounded-xs font-bold border ${
                                                        msg.status === 'new' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' :
                                                        msg.status === 'updated' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                                        'bg-white/5 text-zinc-600 border-white/5'
                                                    }`}>
                                                        {msg.status?.toUpperCase()}
                                                    </span>
                                                ) : (
                                                    <div className="w-1.5 h-1.5 rounded-full bg-zinc-800 mt-1.5 flex-shrink-0" />
                                                )}
                                                <span className={
                                                    msg.type === 'error' ? 'text-red-400' :
                                                    msg.type === 'completed' ? 'text-white font-bold' :
                                                    'text-zinc-500'
                                                }>
                                                    {msg.type === 'completed'
                                                        ? `SYNC COMPLETE // ${msg.new} NEW // ${msg.updated} UPDATED`
                                                        : msg.message || msg.location || msg.type}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                </motion.div>
                            )}

                            <div data-tour="compliance-tabs" className="flex border-b border-white/5 bg-zinc-900/20 px-4">
                                {[
                                    { id: 'requirements', label: 'Matrix', count: requirements?.length },
                                    { id: 'alerts', label: 'Alerts', count: locationAlerts.length, badge: unreadAlertsCount },
                                    { id: 'upcoming', label: 'Future', count: upcomingLegislation?.length },
                                    { id: 'history', label: 'Log' },
                                    { id: 'posters', label: 'Vault' },
                                ].map((tab) => (
                                    <button
                                        key={tab.id}
                                        onClick={() => setActiveTab(tab.id as any)}
                                        className={`px-6 py-4 text-[10px] font-bold uppercase tracking-[0.2em] transition-all relative ${
                                            activeTab === tab.id
                                                ? 'text-white'
                                                : 'text-zinc-600 hover:text-zinc-400'
                                        }`}
                                    >
                                        <span className="flex items-center gap-2">
                                            {tab.label}
                                            {tab.count !== undefined && (
                                                <span className="text-[8px] opacity-40 font-mono">[{tab.count}]</span>
                                            )}
                                            {tab.badge ? (
                                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]" />
                                            ) : null}
                                        </span>
                                        {activeTab === tab.id && (
                                            <motion.div 
                                                layoutId="active-tab-indicator"
                                                className="absolute bottom-0 left-6 right-6 h-0.5 bg-white" 
                                            />
                                        )}
                                    </button>
                                ))}
                            </div>

                            {selectedLocation?.has_local_ordinance === false && (
                                <div className="mx-6 mt-4 px-4 py-3 bg-blue-500/10 border border-blue-500/20 rounded-sm flex items-start gap-3">
                                    <Info size={14} className="text-blue-400 mt-0.5 flex-shrink-0" />
                                    <p className="text-[10px] text-blue-300 leading-relaxed uppercase tracking-tight">
                                        <span className="font-bold">{selectedLocation.city}</span> does not have local labor ordinances.
                                        Requirements inherited from {selectedLocation.county ? `${selectedLocation.county} County / ` : ''}{selectedLocation.state} State law.
                                    </p>
                                </div>
                            )}

                            <div className="p-6 flex-1 bg-zinc-950 overflow-y-auto">
                                {activeTab === 'posters' ? (
                                    postersLoading ? (
                                        <div className="space-y-4">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className="h-16 bg-zinc-900 border border-zinc-800 rounded animate-pulse" />
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="space-y-6">
                                            {/* Available posters by location */}
                                            <div>
                                                <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-4 pb-2 border-b border-white/5">Available Posters</h3>
                                                {availablePosters.length === 0 ? (
                                                    <p className="text-zinc-600 text-[10px] font-mono uppercase tracking-widest">No templates generated for this endpoint context.</p>
                                                ) : (
                                                    <div className="space-y-2">
                                                        {availablePosters.map(poster => (
                                                            <div key={poster.location_id} className="bg-zinc-900/40 border border-white/5 rounded-sm p-5 flex items-center justify-between group hover:bg-zinc-900/60 transition-colors">
                                                                <div>
                                                                    <div className="text-xs font-bold text-white uppercase tracking-widest">
                                                                        {poster.location_city}, {poster.location_state}
                                                                        {poster.location_name && <span className="text-zinc-500 ml-2 font-light">({poster.location_name})</span>}
                                                                    </div>
                                                                    {poster.template_title && (
                                                                        <div className="text-[9px] text-zinc-500 mt-1.5 font-mono uppercase tracking-tighter">
                                                                            {poster.template_title}
                                                                            {poster.template_version && <span className="text-zinc-600 ml-2 font-bold">v{poster.template_version}</span>}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                <div className="flex items-center gap-3">
                                                                    {poster.template_status === 'generated' && poster.template_id && (
                                                                        <>
                                                                            <button
                                                                                onClick={async () => {
                                                                                    try {
                                                                                        const data = await api.posters.getPreview(poster.template_id!);
                                                                                        window.open(data.pdf_url, '_blank');
                                                                                    } catch (err) {
                                                                                        console.error('Preview failed:', err);
                                                                                    }
                                                                                }}
                                                                                className="px-4 py-2 text-[9px] font-bold uppercase tracking-widest bg-zinc-800 hover:bg-white hover:text-black text-zinc-300 rounded-xs transition-all"
                                                                            >
                                                                                Preview PDF
                                                                            </button>
                                                                            {!poster.has_active_order && (
                                                                                <button
                                                                                    disabled={posterOrderLoading === poster.location_id}
                                                                                    onClick={async () => {
                                                                                        setPosterOrderLoading(poster.location_id);
                                                                                        try {
                                                                                            await api.posters.createOrder({
                                                                                                location_id: poster.location_id,
                                                                                                template_ids: [poster.template_id!],
                                                                                            });
                                                                                            // Refresh poster data
                                                                                            const [p, o] = await Promise.all([
                                                                                                api.posters.getAvailable(),
                                                                                                api.posters.listOrders(),
                                                                                            ]);
                                                                                            setAvailablePosters(p);
                                                                                            setPosterOrders(o.orders);
                                                                                        } catch (err) {
                                                                                            console.error('Order failed:', err);
                                                                                        } finally {
                                                                                            setPosterOrderLoading(null);
                                                                                        }
                                                                                    }}
                                                                                    className="px-4 py-2 text-[9px] font-bold uppercase tracking-widest bg-emerald-600 hover:bg-emerald-500 text-white rounded-xs transition-all disabled:opacity-50"
                                                                                >
                                                                                    {posterOrderLoading === poster.location_id ? 'Ordering...' : 'Order Poster'}
                                                                                </button>
                                                                            )}
                                                                            {poster.has_active_order && (
                                                                                <span className="px-2.5 py-1 text-[8px] font-bold uppercase tracking-widest bg-blue-500/10 text-blue-400 rounded-xs border border-blue-500/20">
                                                                                    Order Logged
                                                                                </span>
                                                                            )}
                                                                        </>
                                                                    )}
                                                                    {poster.template_status === 'pending' && (
                                                                        <span className="px-2.5 py-1 text-[8px] font-bold uppercase tracking-widest bg-amber-500/10 text-amber-400 rounded-xs border border-amber-500/20 animate-pulse">
                                                                            Synthesis Pending
                                                                        </span>
                                                                    )}
                                                                    {!poster.template_id && (
                                                                        <span className="text-[9px] text-zinc-700 font-mono uppercase tracking-widest">Unavailable</span>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>

                                            {/* Order history */}
                                            {posterOrders.length > 0 && (
                                                <div>
                                                    <h3 className="text-[10px] font-bold uppercase tracking-widest text-zinc-500 mb-4 pb-2 border-b border-white/5">Vault History</h3>
                                                    <div className="space-y-2">
                                                        {posterOrders.map(order => (
                                                            <div key={order.id} className="bg-zinc-900/20 border border-white/5 rounded-sm p-5 hover:bg-zinc-900/40 transition-colors">
                                                                <div className="flex items-center justify-between">
                                                                    <div>
                                                                        <div className="text-xs font-bold text-zinc-300 uppercase tracking-widest">
                                                                            {order.location_city}, {order.location_state}
                                                                            {order.location_name && <span className="text-zinc-600 ml-2">({order.location_name})</span>}
                                                                        </div>
                                                                        <div className="text-[9px] text-zinc-600 mt-1.5 font-mono uppercase tracking-tighter">
                                                                            {order.items.map(i => i.template_title || i.jurisdiction_name).join(' // ')}
                                                                            {' \u00b7 '}{order.created_at ? new Date(order.created_at).toLocaleDateString() : ''}
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex items-center gap-3">
                                                                        <span className={`px-2 py-1 text-[8px] font-bold uppercase tracking-widest rounded-xs border ${
                                                                            order.status === 'delivered' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' :
                                                                            order.status === 'shipped' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                                                            order.status === 'cancelled' ? 'bg-zinc-800 text-zinc-500 border-zinc-700' :
                                                                            'bg-blue-500/10 text-blue-400 border-blue-500/20'
                                                                        }`}>
                                                                            {order.status}
                                                                        </span>
                                                                        {order.tracking_number && (
                                                                            <span className="text-[9px] text-zinc-600 font-mono tracking-tighter">#{order.tracking_number}</span>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                                {order.quote_amount != null && (
                                                                    <div className="text-[9px] text-zinc-600 mt-3 font-mono uppercase tracking-widest">Settlement: ${order.quote_amount.toFixed(2)}</div>
                                                                )}
                                                                {order.admin_notes && (
                                                                    <div className="text-[9px] text-zinc-700 mt-1.5 italic font-serif">Note: {order.admin_notes}</div>
                                                                )}
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )
                                ) : activeTab === 'upcoming' ? (
                                    !upcomingLegislation || upcomingLegislation.length === 0 ? (
                                        <div className="text-center py-24 border border-dashed border-white/5 bg-white/[0.01]">
                                            <div className="w-12 h-12 mx-auto mb-6 rounded-full bg-zinc-900 border border-white/5 flex items-center justify-center opacity-40">
                                                <Calendar size={20} className="text-zinc-500" />
                                            </div>
                                            <p className="text-zinc-600 text-[10px] font-mono uppercase tracking-[0.2em]">Zero Future Deltas Detected</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {upcomingLegislation.map(leg => {
                                                const statusColors: Record<string, string> = {
                                                    proposed: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
                                                    passed: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
                                                    signed: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
                                                    effective_soon: 'bg-red-500/10 text-red-400 border-red-500/20',
                                                    effective: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
                                                    dismissed: 'bg-zinc-800 text-zinc-500 border-zinc-700',
                                                };
                                                const isEffectiveNow = leg.days_until_effective !== null && leg.days_until_effective <= 0;
                                                const displayStatus = isEffectiveNow ? 'effective' : leg.current_status;
                                                return (
                                                    <div key={leg.id} className="border border-white/5 rounded-sm p-6 bg-zinc-900/40 hover:bg-zinc-900/60 transition-colors">
                                                        <div className="flex items-start justify-between gap-6">
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-3 flex-wrap mb-2">
                                                                    <h4 className="text-sm font-bold text-white uppercase tracking-tight truncate">{leg.title}</h4>
                                                                    <span className={`text-[8px] px-1.5 py-0.5 border rounded-xs font-bold uppercase tracking-widest ${statusColors[displayStatus] || 'bg-zinc-800 text-zinc-500 border-zinc-700'}`}>
                                                                        {displayStatus.replace('_', ' ')}
                                                                    </span>
                                                                    {leg.category && (
                                                                        <span className="text-[8px] px-1.5 py-0.5 bg-white/5 text-zinc-500 border border-white/10 rounded-xs uppercase tracking-widest">
                                                                            {COMPLIANCE_CATEGORY_LABELS[leg.category] || leg.category}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                {leg.description && (
                                                                    <p className="text-[11px] text-zinc-500 leading-relaxed mb-4 font-light">{leg.description}</p>
                                                                )}
                                                                {leg.impact_summary && (
                                                                    <div className="p-3 bg-amber-500/[0.03] border-l-2 border-amber-500/20 mb-4">
                                                                        <p className="text-[10px] text-amber-200/70 leading-relaxed">
                                                                            <span className="font-bold uppercase tracking-wider text-[8px] mr-2">Impact Analysis:</span> {leg.impact_summary}
                                                                        </p>
                                                                    </div>
                                                                )}
                                                                <div className="flex items-center gap-6 text-[9px] font-mono text-zinc-600 uppercase tracking-widest">
                                                                    {leg.expected_effective_date && (
                                                                        <span className="flex items-center gap-2">
                                                                            <Calendar size={10} className="opacity-40" />
                                                                            {new Date(leg.expected_effective_date).toLocaleDateString()}
                                                                            {leg.days_until_effective !== null && (
                                                                                <span className={`ml-1 font-bold ${
                                                                                    leg.days_until_effective <= 30 ? 'text-red-500' :
                                                                                    leg.days_until_effective <= 90 ? 'text-amber-500' :
                                                                                    'text-zinc-500'
                                                                                }`}>
                                                                                    ({leg.days_until_effective <= 0 ? 'ENFORCED' : `${leg.days_until_effective}D REMAINING`})
                                                                                </span>
                                                                            )}
                                                                        </span>
                                                                    )}
                                                                    {leg.confidence !== null && (
                                                                        <span>Confidence: {Math.round(leg.confidence * 100)}%</span>
                                                                    )}
                                                                    {leg.source_url && (
                                                                        <a href={leg.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-white flex items-center gap-1.5 transition-colors">
                                                                            Authority <ExternalLink size={10} />
                                                                        </a>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            {leg.days_until_effective !== null && leg.days_until_effective <= 90 && (
                                                                <div className={`text-right flex-shrink-0 ${
                                                                    leg.days_until_effective <= 0 ? 'text-red-500' :
                                                                    leg.days_until_effective <= 30 ? 'text-red-500' :
                                                                    'text-amber-500'
                                                                }`}>
                                                                    <div className="text-3xl font-bold tracking-tighter">
                                                                        {leg.days_until_effective <= 0 ? 'ACT' : leg.days_until_effective}
                                                                    </div>
                                                                    {leg.days_until_effective > 0 && (
                                                                        <div className="text-[8px] font-bold uppercase tracking-[0.3em]">Days</div>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    )
                                ) : activeTab === 'history' ? (
                                    !checkLog || checkLog.length === 0 ? (
                                        <div className="text-center py-24 border border-dashed border-white/5 bg-white/[0.01]">
                                            <div className="w-12 h-12 mx-auto mb-6 rounded-full bg-zinc-900 border border-white/5 flex items-center justify-center opacity-40">
                                                <History size={20} className="text-zinc-500" />
                                            </div>
                                            <p className="text-zinc-600 text-[10px] font-mono uppercase tracking-[0.2em]">Zero Sync Events</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-1.5">
                                            {checkLog.map(entry => (
                                                <div key={entry.id} className="flex items-center gap-6 p-4 border border-white/5 rounded-sm bg-zinc-900/40 hover:bg-zinc-900/60 transition-colors group">
                                                    <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 shadow-sm ${
                                                        entry.status === 'completed' ? 'bg-emerald-500 shadow-emerald-500/20' :
                                                        entry.status === 'failed' ? 'bg-red-500 shadow-red-500/20' :
                                                        'bg-amber-500 animate-pulse'
                                                    }`} />
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-4">
                                                            <span className={`text-[8px] px-1.5 py-0.5 rounded-xs border font-bold uppercase tracking-widest ${
                                                                entry.check_type === 'scheduled' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                                                entry.check_type === 'proactive' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                                                'bg-white/5 text-zinc-500 border-white/10'
                                                            }`}>
                                                                {entry.check_type}
                                                            </span>
                                                            <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-tighter">
                                                                {new Date(entry.started_at).toLocaleString(undefined, {
                                                                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                                                                })}
                                                            </span>
                                                        </div>
                                                        {entry.status === 'completed' && (
                                                            <p className="text-[9px] text-zinc-600 mt-1.5 font-mono uppercase tracking-tighter">
                                                                {entry.new_count} New Nodes // {entry.updated_count} Delta Updates // {entry.alert_count} Protocol Alerts
                                                            </p>
                                                        )}
                                                        {entry.error_message && (
                                                            <p className="text-[9px] text-red-400/70 mt-1.5 truncate font-mono uppercase tracking-tighter">Err: {entry.error_message}</p>
                                                        )}
                                                    </div>
                                                    <span className={`text-[9px] uppercase tracking-widest font-bold ${
                                                        entry.status === 'completed' ? 'text-emerald-500/60' :
                                                        entry.status === 'failed' ? 'text-red-500/60' :
                                                        'text-amber-500/60'
                                                    }`}>
                                                        {entry.status}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )
                                ) : activeTab === 'requirements' ? (
                                    loadingRequirements ? (
                                        <div className="space-y-4">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className="h-16 bg-zinc-900 border border-zinc-800 rounded animate-pulse" />
                                            ))}
                                        </div>
                                    ) : orderedRequirementCategories.length === 0 ? (
                                        <div className="text-center py-24 text-zinc-600 text-[10px] font-mono uppercase tracking-[0.2em] border border-dashed border-white/5 bg-white/[0.01]">
                                            Zero Nodes Detected
                                        </div>
                                    ) : (
                                        <div className="space-y-px bg-white/5 border border-white/5">
                                            {orderedRequirementCategories.map(([category, reqs]) => (
                                                <div key={category} className="bg-zinc-950/20">
                                                    <button
                                                        onClick={() => toggleCategory(category)}
                                                        className="w-full flex items-center justify-between p-5 bg-zinc-900/40 hover:bg-zinc-900/60 transition-colors border-b border-white/[0.02]"
                                                    >
                                                        <div className="flex items-center gap-4">
                                                            <div className="flex flex-col items-start">
                                                                <span className="text-white text-[11px] font-bold uppercase tracking-widest">
                                                                    {COMPLIANCE_CATEGORY_LABELS[category] || category}
                                                                </span>
                                                                <span className="text-[8px] text-zinc-600 font-mono uppercase tracking-[0.2em] mt-0.5">
                                                                    {reqs.length} Active Node{reqs.length !== 1 ? 's' : ''}
                                                                </span>
                                                            </div>
                                                            {reqs.length > 0 ? (
                                                                (() => {
                                                                    const source = getCategoryJurisdiction(reqs);
                                                                    return (
                                                                        <span className={`px-2 py-0.5 text-[8px] rounded-xs border font-bold uppercase tracking-[0.2em] ${
                                                                            source.type === 'local'
                                                                                ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                                                                                : 'bg-blue-500/10 text-blue-500 border-blue-500/20'
                                                                        }`}>
                                                                            {source.label}
                                                                        </span>
                                                                    );
                                                                })()
                                                            ) : (
                                                                <span className="px-2 py-0.5 text-[8px] rounded-xs border font-bold uppercase tracking-[0.2em] bg-zinc-900 text-zinc-500 border-zinc-800">
                                                                    Coverage Pending
                                                                </span>
                                                            )}
                                                        </div>
                                                        <motion.div
                                                            animate={{ rotate: expandedCategories.has(category) ? 180 : 0 }}
                                                            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                                                        >
                                                            <ChevronDown size={14} className="text-zinc-600" />
                                                        </motion.div>
                                                    </button>

                                                    <AnimatePresence initial={false}>
                                                        {expandedCategories.has(category) && (
                                                            <motion.div
                                                                initial={{ height: 0, opacity: 0 }}
                                                                animate={{ height: 'auto', opacity: 1 }}
                                                                exit={{ height: 0, opacity: 0 }}
                                                                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                                                                className="overflow-hidden bg-zinc-950/40"
                                                            >
                                                                <div className="divide-y divide-white/5 px-2">
                                                                    {reqs.length === 0 ? (
                                                                        <div className="p-6 text-zinc-500 text-xs leading-relaxed font-light">
                                                                            {getRequirementEmptyStateCopy(category)}
                                                                        </div>
                                                                    ) : (
                                                                        reqs.map(req => (
                                                                            <div key={req.id} className="p-6 hover:bg-white/[0.02] transition-colors rounded-sm">
                                                                                <div className="flex items-start justify-between mb-4 gap-6">
                                                                                    <div className="flex-1">
                                                                                        <h4 className="text-white text-xs font-bold uppercase tracking-wide mb-2">
                                                                                            {req.title}
                                                                                        </h4>
                                                                                        <div className="flex items-center gap-3">
                                                                                            <span className="px-1.5 py-0.5 bg-zinc-900 border border-white/5 text-[8px] uppercase tracking-widest text-zinc-500 font-bold rounded-xs">
                                                                                                {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                                                                                            </span>
                                                                                            {req.category === 'minimum_wage' && req.rate_type && (
                                                                                                <span className="px-1.5 py-0.5 bg-zinc-900 border border-white/5 text-[8px] uppercase tracking-widest text-zinc-400 font-bold rounded-xs">
                                                                                                    {RATE_TYPE_LABELS[req.rate_type] || req.rate_type.replace(/_/g, ' ')}
                                                                                                </span>
                                                                                            )}
                                                                                            <span className="text-zinc-600 text-[9px] font-mono uppercase tracking-tighter">
                                                                                                Node: {req.jurisdiction_name}
                                                                                            </span>
                                                                                        </div>
                                                                                    </div>
                                                                                    {req.current_value && (
                                                                                        <span className="text-emerald-400 font-mono text-xs bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-sm shadow-inner">
                                                                                            {req.current_value}
                                                                                        </span>
                                                                                    )}
                                                                                </div>
                                                                                {req.description && (
                                                                                    <p className="text-zinc-500 text-xs leading-relaxed mb-6 max-w-2xl font-light">
                                                                                        {req.description}
                                                                                    </p>
                                                                                )}
                                                                                <div className="flex items-center justify-between pt-4 border-t border-white/[0.03]">
                                                                                    <div className="flex items-center gap-4">
                                                                                        {req.effective_date && (
                                                                                            <div className="flex items-center gap-2 text-[8px] text-zinc-600 uppercase tracking-widest font-mono">
                                                                                                <Calendar size={10} className="opacity-40" />
                                                                                                Enforced: {new Date(req.effective_date).toLocaleDateString()}
                                                                                            </div>
                                                                                        )}
                                                                                    </div>
                                                                                    {req.source_url && (
                                                                                        <a
                                                                                            href={req.source_url}
                                                                                            target="_blank"
                                                                                            rel="noopener noreferrer"
                                                                                            className="text-[9px] font-bold uppercase tracking-widest text-zinc-500 hover:text-white flex items-center gap-1.5 transition-colors"
                                                                                        >
                                                                                            Authority <ExternalLink size={10} />
                                                                                        </a>
                                                                                    )}
                                                                                </div>
                                                                            </div>
                                                                        ))
                                                                    )}
                                                                </div>
                                                            </motion.div>
                                                        )}
                                                    </AnimatePresence>
                                                </div>
                                            ))}
                                        </div>
                                    )
                                ) : activeTab === 'alerts' ? (
                                    loadingAlerts ? (
                                        <div className="space-y-3">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className="h-20 bg-zinc-900 border border-zinc-800 rounded animate-pulse" />
                                            ))}
                                        </div>
                                    ) : locationAlerts.length === 0 ? (
                                        <div className="text-center py-24 border border-dashed border-white/5 bg-white/[0.01]">
                                            <div className="w-12 h-12 mx-auto mb-6 rounded-full bg-zinc-900 border border-white/5 flex items-center justify-center">
                                                <CheckCircle size={20} className="text-zinc-700" />
                                            </div>
                                            <p className="text-zinc-600 text-[10px] font-mono uppercase tracking-[0.2em]">All Systems Nominal</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-2">
                                            {locationAlerts.map(alert => {
                                                const confidence = getConfidenceBadge(alert.confidence_score);
                                                return (
                                                <motion.div
                                                    layout
                                                    initial={{ opacity: 0, y: 10 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    key={alert.id}
                                                    className={`border rounded-sm p-5 transition-all ${getSeverityStyles(alert.severity)} ${
                                                        alert.status === 'unread' ? 'bg-opacity-10 border-opacity-30' : 'opacity-50 bg-zinc-900/40 border-white/5'
                                                    }`}
                                                >
                                                    <div className="flex items-start justify-between gap-6">
                                                        <div className="flex items-start gap-4 min-w-0">
                                                            <div className="mt-1 flex-shrink-0 opacity-60">
                                                                {getAlertTypeIcon(alert.alert_type)}
                                                            </div>
                                                            <div className="min-w-0">
                                                                <div className="flex items-center gap-3 flex-wrap mb-2">
                                                                    <h4 className="text-xs font-bold uppercase tracking-widest text-white">{alert.title}</h4>
                                                                    {alert.alert_type && alert.alert_type !== 'change' && (
                                                                        <span className="text-[8px] px-1.5 py-0.5 bg-white/5 border border-white/10 rounded-xs uppercase tracking-widest font-bold text-zinc-400">
                                                                            {alert.alert_type.replace('_', ' ')}
                                                                        </span>
                                                                    )}
                                                                    {confidence && (
                                                                        <span className={`text-[8px] px-1.5 py-0.5 border rounded-xs font-bold uppercase tracking-widest ${confidence.color}`}>
                                                                            {confidence.tag} {confidence.label}
                                                                        </span>
                                                                    )}
                                                                    {alert.created_at && (
                                                                        <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-tighter">
                                                                            {new Date(alert.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <p className="text-xs text-zinc-400 leading-relaxed font-light">{linkifyText(alert.message)}</p>
                                                                
                                                                <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mt-4">
                                                                    {alert.effective_date && (
                                                                        <div className="text-[9px] font-mono text-purple-400 uppercase tracking-widest flex items-center gap-2">
                                                                            <Calendar size={10} className="opacity-50" /> Enforce: {new Date(alert.effective_date).toLocaleDateString()}
                                                                        </div>
                                                                    )}
                                                                    {(alert.source_url || alert.source_name) && (
                                                                        <div className="text-[9px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-2">
                                                                            <span className="opacity-40">Source:</span>
                                                                            {alert.source_url ? (
                                                                                <a href={alert.source_url} target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-white underline decoration-white/10 underline-offset-2 transition-colors">
                                                                                    {alert.source_name || 'Authority'}
                                                                                </a>
                                                                            ) : (
                                                                                <span>{alert.source_name}</span>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </div>

                                                                {alert.verification_sources && alert.verification_sources.length > 0 && (
                                                                    <div className="mt-4">
                                                                        <button
                                                                            onClick={() => toggleAlertSources(alert.id)}
                                                                            className="text-[8px] uppercase tracking-[0.2em] text-zinc-600 hover:text-zinc-400 flex items-center gap-2 transition-colors"
                                                                        >
                                                                            <Eye size={10} />
                                                                            {expandedAlertSources.has(alert.id) ? 'Hide' : 'Resolve'} {alert.verification_sources.length} Evidence Node(s)
                                                                        </button>
                                                                        {expandedAlertSources.has(alert.id) && (
                                                                            <div className="mt-3 space-y-2 pl-4 border-l border-white/5">
                                                                                {alert.verification_sources.map((src, idx) => (
                                                                                    <div key={idx} className="text-[9px]">
                                                                                        <div className="flex items-center gap-2 mb-1">
                                                                                            <span className={`px-1 py-0.5 rounded-xs uppercase tracking-widest font-bold text-[7px] ${
                                                                                                src.type === 'official' ? 'bg-emerald-500/10 text-emerald-400' :
                                                                                                src.type === 'news' ? 'bg-blue-500/10 text-blue-400' :
                                                                                                'bg-zinc-800 text-zinc-500'
                                                                                            }`}>
                                                                                                {src.type}
                                                                                            </span>
                                                                                            {src.url ? (
                                                                                                <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-white truncate max-w-xs transition-colors">
                                                                                                    {src.name || src.url}
                                                                                                </a>
                                                                                            ) : (
                                                                                                <span className="text-zinc-500">{src.name}</span>
                                                                                            )}
                                                                                        </div>
                                                                                        {src.snippet && (
                                                                                            <p className="text-zinc-600 italic leading-relaxed pl-2 border-l border-white/[0.02]">{src.snippet}</p>
                                                                                        )}
                                                                                    </div>
                                                                                ))}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                )}
                                                                {alert.action_required && (
                                                                    <div className="mt-4 p-3 bg-white/5 border border-white/5 rounded-sm">
                                                                        <span className="text-[8px] font-bold uppercase tracking-[0.3em] text-zinc-500 block mb-1">Mandatory Action</span>
                                                                        <span className="text-[10px] text-white font-bold uppercase tracking-wide">{alert.action_required}</span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-1 opacity-40 hover:opacity-100 transition-opacity">
                                                            {alert.status === 'unread' && (
                                                                <button
                                                                    onClick={() => markAlertReadMutation.mutate(alert.id)}
                                                                    className="p-2 hover:bg-white/5 rounded-full transition-colors text-zinc-400 hover:text-emerald-500"
                                                                    title="Acknowledge"
                                                                >
                                                                    <CheckCircle size={14} />
                                                                </button>
                                                            )}
                                                            {alert.status !== 'dismissed' && (
                                                                <button
                                                                    onClick={() => dismissAlertMutation.mutate(alert.id)}
                                                                    className="p-2 hover:bg-white/5 rounded-full transition-colors text-zinc-400 hover:text-red-500"
                                                                    title="Dismiss"
                                                                >
                                                                    <X size={14} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                </motion.div>
                                                );
                                            })}
                                        </div>
                                    )
                                ) : (
                                    loadingAlerts ? (
                                        <div className="space-y-3">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className="h-20 bg-zinc-900 border border-zinc-800 rounded animate-pulse" />
                                            ))}
                                        </div>
                                    ) : locationAlerts.length === 0 ? (
                                        <div className="text-center py-24 border border-dashed border-white/5 bg-white/[0.01]">
                                            <div className="w-12 h-12 mx-auto mb-6 rounded-full bg-zinc-900 border border-white/5 flex items-center justify-center">
                                                <CheckCircle size={20} className="text-zinc-700" />
                                            </div>
                                            <p className="text-zinc-600 text-[10px] font-mono uppercase tracking-[0.2em]">All Systems Nominal</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-2">
                                            {locationAlerts.map(alert => {
                                                const confidence = getConfidenceBadge(alert.confidence_score);
                                                return (
                                                <motion.div
                                                    layout
                                                    initial={{ opacity: 0, y: 10 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    key={alert.id}
                                                    className={`border rounded-sm p-5 transition-all ${getSeverityStyles(alert.severity)} ${
                                                        alert.status === 'unread' ? 'bg-opacity-10 border-opacity-30' : 'opacity-50 bg-zinc-900/40 border-white/5'
                                                    }`}
                                                >
                                                    <div className="flex items-start justify-between gap-6">
                                                        <div className="flex items-start gap-4 min-w-0">
                                                            <div className="mt-1 flex-shrink-0 opacity-60">
                                                                {getAlertTypeIcon(alert.alert_type)}
                                                            </div>
                                                            <div className="min-w-0">
                                                                <div className="flex items-center gap-3 flex-wrap mb-2">
                                                                    <h4 className="text-xs font-bold uppercase tracking-widest text-white">{alert.title}</h4>
                                                                    {alert.alert_type && alert.alert_type !== 'change' && (
                                                                        <span className="text-[8px] px-1.5 py-0.5 bg-white/5 border border-white/10 rounded-xs uppercase tracking-widest font-bold text-zinc-400">
                                                                            {alert.alert_type.replace('_', ' ')}
                                                                        </span>
                                                                    )}
                                                                    {confidence && (
                                                                        <span className={`text-[8px] px-1.5 py-0.5 border rounded-xs font-bold uppercase tracking-widest ${confidence.color}`}>
                                                                            {confidence.tag} {confidence.label}
                                                                        </span>
                                                                    )}
                                                                    {alert.created_at && (
                                                                        <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-tighter">
                                                                            {new Date(alert.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <p className="text-xs text-zinc-400 leading-relaxed font-light">{linkifyText(alert.message)}</p>
                                                                
                                                                <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mt-4">
                                                                    {alert.effective_date && (
                                                                        <div className="text-[9px] font-mono text-purple-400 uppercase tracking-widest flex items-center gap-2">
                                                                            <Calendar size={10} className="opacity-50" /> Enforce: {new Date(alert.effective_date).toLocaleDateString()}
                                                                        </div>
                                                                    )}
                                                                    {(alert.source_url || alert.source_name) && (
                                                                        <div className="text-[9px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-2">
                                                                            <span className="opacity-40">Source:</span>
                                                                            {alert.source_url ? (
                                                                                <a href={alert.source_url} target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-white underline decoration-white/10 underline-offset-2 transition-colors">
                                                                                    {alert.source_name || 'Authority'}
                                                                                </a>
                                                                            ) : (
                                                                                <span>{alert.source_name}</span>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </div>

                                                                {alert.verification_sources && alert.verification_sources.length > 0 && (
                                                                    <div className="mt-4">
                                                                        <button
                                                                            onClick={() => toggleAlertSources(alert.id)}
                                                                            className="text-[8px] uppercase tracking-[0.2em] text-zinc-600 hover:text-zinc-400 flex items-center gap-2 transition-colors"
                                                                        >
                                                                            <Eye size={10} />
                                                                            {expandedAlertSources.has(alert.id) ? 'Hide' : 'Resolve'} {alert.verification_sources.length} Evidence Node(s)
                                                                        </button>
                                                                        {expandedAlertSources.has(alert.id) && (
                                                                            <div className="mt-3 space-y-2 pl-4 border-l border-white/5">
                                                                                {alert.verification_sources.map((src, idx) => (
                                                                                    <div key={idx} className="text-[9px]">
                                                                                        <div className="flex items-center gap-2 mb-1">
                                                                                            <span className={`px-1 py-0.5 rounded-xs uppercase tracking-widest font-bold text-[7px] ${
                                                                                                src.type === 'official' ? 'bg-emerald-500/10 text-emerald-400' :
                                                                                                src.type === 'news' ? 'bg-blue-500/10 text-blue-400' :
                                                                                                'bg-zinc-800 text-zinc-500'
                                                                                            }`}>
                                                                                                {src.type}
                                                                                            </span>
                                                                                            {src.url ? (
                                                                                                <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-zinc-400 hover:text-white truncate max-w-xs transition-colors">
                                                                                                    {src.name || src.url}
                                                                                                </a>
                                                                                            ) : (
                                                                                                <span className="text-zinc-500">{src.name}</span>
                                                                                            )}
                                                                                        </div>
                                                                                        {src.snippet && (
                                                                                            <p className="text-zinc-600 italic leading-relaxed pl-2 border-l border-white/[0.02]">{src.snippet}</p>
                                                                                        )}
                                                                                    </div>
                                                                                ))}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                )}
                                                                {alert.action_required && (
                                                                    <div className="mt-4 p-3 bg-white/5 border border-white/5 rounded-sm">
                                                                        <span className="text-[8px] font-bold uppercase tracking-[0.3em] text-zinc-500 block mb-1">Mandatory Action</span>
                                                                        <span className="text-[10px] text-white font-bold uppercase tracking-wide">{alert.action_required}</span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-1 opacity-40 hover:opacity-100 transition-opacity">
                                                            {alert.status === 'unread' && (
                                                                <button
                                                                    onClick={() => markAlertReadMutation.mutate(alert.id)}
                                                                    className="p-2 hover:bg-white/5 rounded-full transition-colors text-zinc-400 hover:text-emerald-500"
                                                                    title="Acknowledge"
                                                                >
                                                                    <CheckCircle size={14} />
                                                                </button>
                                                            )}
                                                            {alert.status !== 'dismissed' && (
                                                                <button
                                                                    onClick={() => dismissAlertMutation.mutate(alert.id)}
                                                                    className="p-2 hover:bg-white/5 rounded-full transition-colors text-zinc-400 hover:text-red-500"
                                                                    title="Dismiss"
                                                                >
                                                                    <X size={14} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                </motion.div>
                                                );
                                            })}
                                        </div>
                                    )
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="bg-zinc-900/30 border border-white/5 rounded-sm p-12 text-center h-full flex flex-col items-center justify-center min-h-[400px]">
                            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-zinc-900 border border-white/5 flex items-center justify-center opacity-40">
                                <MapPin size={24} className="text-zinc-600" />
                            </div>
                            <h3 className="text-white font-bold uppercase tracking-[0.2em] text-[10px] mb-2">Select Global Endpoint</h3>
                            <p className="text-zinc-600 text-[10px] max-w-sm font-mono uppercase tracking-tight">
                                Choose a location from the matrix to initialize compliance telemetry and alert protocols.
                            </p>
                        </div>
                    )}
                </div>
            </div>

            <AnimatePresence>
                {showAddModal && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/90 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                        onClick={() => {
                            setShowAddModal(false);
                            setEditingLocation(null);
                            setFormData(emptyFormData);
                            setJurisdictionSearch('');
                            setUseManualEntry(false);
                        }}
                    >
                        <motion.div
                            initial={{ scale: 0.98, opacity: 0, y: 10 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.98, opacity: 0, y: 10 }}
                            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                            className="bg-zinc-950 border border-white/10 shadow-2xl rounded-sm p-10 w-full max-w-md relative overflow-hidden"
                            onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        >
                            <div className="absolute top-0 left-0 w-full h-0.5 bg-white/5" />
                            <div className="flex items-center justify-between mb-10">
                                <div className="space-y-1">
                                    <h2 className="text-2xl font-bold text-white uppercase tracking-tighter">
                                        {editingLocation ? 'Edit Endpoint' : 'Register Node'}
                                    </h2>
                                    <p className="text-[9px] text-zinc-500 font-mono uppercase tracking-[0.2em]">Location Configuration</p>
                                </div>
                                <button
                                    onClick={() => {
                                        setShowAddModal(false);
                                        setEditingLocation(null);
                                        setFormData(emptyFormData);
                                        setJurisdictionSearch('');
                                        setUseManualEntry(false);
                                    }}
                                    className="p-2 text-zinc-600 hover:text-white transition-colors"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleSubmitLocation} className="space-y-6">
                                <div>
                                    <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2 font-bold font-mono">
                                        Logical Identifier (optional)
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.name}
                                        onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                        placeholder="e.g. SF HEADQUARTERS"
                                        className="w-full px-4 py-3 bg-white/5 border border-white/5 text-white text-sm focus:outline-none focus:border-white/20 transition-all rounded-sm placeholder-zinc-800 font-mono uppercase tracking-tight"
                                    />
                                </div>

                                {showJurisdictionPicker ? (
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between">
                                            <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 font-bold font-mono">
                                                Jurisdiction Scan
                                            </label>
                                            <button
                                                type="button"
                                                onClick={() => { setUseManualEntry(true); setFormData(prev => ({ ...prev, jurisdictionKey: '' })); }}
                                                className="text-[8px] text-zinc-600 hover:text-zinc-400 uppercase tracking-widest transition-colors font-bold"
                                            >
                                                Manual Override
                                            </button>
                                        </div>
                                        <div className="relative">
                                            <input
                                                type="text"
                                                value={jurisdictionSearch}
                                                onChange={e => setJurisdictionSearch(e.target.value)}
                                                placeholder="SEARCH CITIES..."
                                                className="w-full px-4 py-3 bg-white/5 border border-white/5 text-white text-sm focus:outline-none focus:border-white/20 transition-all rounded-sm placeholder-zinc-800 font-mono uppercase tracking-widest"
                                            />
                                        </div>
                                        <div className="max-h-40 overflow-y-auto border border-white/5 rounded-sm bg-black/40 no-scrollbar">
                                            {Object.keys(filteredJurisdictions).length === 0 ? (
                                                <div className="px-4 py-8 text-center text-zinc-700 text-[9px] font-mono uppercase tracking-widest">
                                                    {jurisdictionSearch ? 'Zero Matches' : 'Initializing Matrix...'}
                                                </div>
                                            ) : (
                                                Object.entries(filteredJurisdictions).map(([state, items]) => {
                                                    const stateLabel = US_STATES.find(s => s.value === state)?.label || state;
                                                    return (
                                                        <div key={state}>
                                                            <div className="px-4 py-2 bg-zinc-950 text-[8px] text-zinc-600 font-bold uppercase tracking-[0.3em] sticky top-0 border-b border-white/5">
                                                                {stateLabel}
                                                            </div>
                                                            {items.map(j => {
                                                                const key = makeJurisdictionKey(j);
                                                                const isSelected = formData.jurisdictionKey === key;
                                                                return (
                                                                    <button
                                                                        key={key}
                                                                        type="button"
                                                                        onClick={() => {
                                                                            setFormData(prev => ({
                                                                                ...prev,
                                                                                city: j.city,
                                                                                state: j.state,
                                                                                county: j.county || '',
                                                                                jurisdictionKey: key,
                                                                            }));
                                                                        }}
                                                                        className={`w-full text-left px-4 py-2.5 text-[11px] transition-all flex items-center justify-between border-b border-white/[0.02] last:border-0 ${
                                                                            isSelected
                                                                                ? 'bg-white/10 text-white font-bold'
                                                                                : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300'
                                                                        }`}
                                                                    >
                                                                        <span className="uppercase tracking-tight">{j.city}, {j.state}</span>
                                                                        {j.has_local_ordinance && (
                                                                            <span className="text-[7px] px-1.5 py-0.5 bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 rounded-xs uppercase tracking-widest font-bold">
                                                                                Ordinance
                                                                            </span>
                                                                        )}
                                                                    </button>
                                                                );
                                                            })}
                                                        </div>
                                                    );
                                                })
                                            )}
                                        </div>
                                        {formData.jurisdictionKey && (
                                            <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-sm">
                                                <div className="text-[8px] text-emerald-500 font-bold uppercase tracking-widest mb-1">Matrix Resolution</div>
                                                <div className="text-xs text-zinc-300 font-mono uppercase tracking-tighter">
                                                    {formData.city}, {formData.state}
                                                    {formData.county && <span className="text-zinc-600 ml-2 font-light">[{formData.county} County]</span>}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <>
                                        {(isClient || isAdmin) && !editingLocation && useManualEntry && (
                                            <button
                                                type="button"
                                                onClick={() => { setUseManualEntry(false); setFormData(emptyFormData); }}
                                                className="text-[8px] text-zinc-600 hover:text-zinc-400 uppercase tracking-widest transition-colors font-bold"
                                            >
                                                Revert to Matrix Search
                                            </button>
                                        )}
                                        <div>
                                            <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2 font-bold font-mono">
                                                Street Address
                                            </label>
                                            <input
                                                type="text"
                                                value={formData.address}
                                                onChange={e => setFormData(prev => ({ ...prev, address: e.target.value }))}
                                                placeholder="PHYSICAL LOCATION"
                                                className="w-full px-4 py-3 bg-white/5 border border-white/5 text-white text-sm focus:outline-none focus:border-white/20 transition-all rounded-sm placeholder-zinc-800 font-mono uppercase tracking-tight"
                                            />
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2 font-bold font-mono">
                                                    City
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.city}
                                                    onChange={e => setFormData(prev => ({ ...prev, city: e.target.value }))}
                                                    required
                                                    className="w-full px-4 py-3 bg-white/5 border border-white/5 text-white text-sm focus:outline-none focus:border-white/20 transition-all rounded-sm font-mono uppercase tracking-tight"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2 font-bold font-mono">
                                                    State
                                                </label>
                                                <select
                                                    value={formData.state}
                                                    onChange={e => setFormData(prev => ({ ...prev, state: e.target.value }))}
                                                    required
                                                    className="w-full px-4 py-3 bg-zinc-900 border border-white/5 text-white text-sm focus:outline-none focus:border-white/20 transition-all rounded-sm font-mono uppercase tracking-tight"
                                                >
                                                    <option value="">--</option>
                                                    {US_STATES.map(state => (
                                                        <option key={state.value} value={state.value}>
                                                            {state.value}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2 font-bold font-mono">
                                                    County
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.county}
                                                    onChange={e => setFormData(prev => ({ ...prev, county: e.target.value }))}
                                                    className="w-full px-4 py-3 bg-white/5 border border-white/5 text-white text-sm focus:outline-none focus:border-white/20 transition-all rounded-sm font-mono uppercase tracking-tight"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-[9px] tracking-[0.2em] uppercase text-zinc-500 mb-2 font-bold font-mono">
                                                    ZIP Code
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.zipcode}
                                                    onChange={e => setFormData(prev => ({ ...prev, zipcode: e.target.value }))}
                                                    required={!isClient && !isAdmin}
                                                    maxLength={10}
                                                    className="w-full px-4 py-3 bg-white/5 border border-white/5 text-white text-sm focus:outline-none focus:border-white/20 transition-all rounded-sm font-mono uppercase tracking-tight"
                                                />
                                            </div>
                                        </div>
                                    </>
                                )}

                                <div className="flex gap-4 pt-8">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowAddModal(false);
                                            setEditingLocation(null);
                                            setFormData(emptyFormData);
                                            setJurisdictionSearch('');
                                            setUseManualEntry(false);
                                        }}
                                        className="flex-1 px-6 py-3.5 bg-transparent border border-white/5 text-zinc-500 hover:text-white hover:bg-white/5 rounded-sm text-[10px] font-bold uppercase tracking-[0.2em] transition-all"
                                    >
                                        Abort
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={createLocationMutation.isPending || updateLocationMutation.isPending || (showJurisdictionPicker && !formData.jurisdictionKey)}
                                        className="flex-1 px-6 py-3.5 bg-white hover:bg-[#4ADE80] text-black rounded-sm text-[10px] font-bold uppercase tracking-[0.2em] transition-all disabled:opacity-50 shadow-lg"
                                    >
                                        {createLocationMutation.isPending || updateLocationMutation.isPending
                                            ? 'Syncing...'
                                            : editingLocation
                                                ? 'Update Logic'
                                                : 'Authorize Node'}
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

export default Compliance;
