import { useState, useMemo, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import type { BusinessLocation, ComplianceRequirement, LocationCreate, JurisdictionOption } from '../api/compliance';
import {
    COMPLIANCE_CATEGORY_LABELS,
    JURISDICTION_LEVEL_LABELS
} from '../api/compliance';
import { adminOverview, api } from '../api/client';
import type { AvailablePoster, PosterOrder } from '../types';
import { useAuth } from '../context/AuthContext';
import {
    MapPin, Trash2, Edit2, X,
    ChevronDown, AlertTriangle, Bell, CheckCircle,
    ExternalLink, Building2, Loader2, Clock, Calendar,
    History, Eye, Zap, Info, Users, Layers, LayoutList, Pin
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { Tabs } from '../components/Tabs';
import { ContentCard } from '../components/ContentCard';
import { baseLT } from '../theme';
import { useCompliance, useComplianceRequirements, useJurisdictionSearch, useComplianceCheck } from '../hooks/compliance';
import type { CategoryGroup } from '../generated/complianceCategories';

const GROUP_FILTER_OPTIONS: { value: 'all' | CategoryGroup; label: string }[] = [
    { value: 'all', label: 'All Categories' },
    { value: 'labor', label: 'Labor' },
    { value: 'supplementary', label: 'Supplementary' },
    { value: 'healthcare', label: 'Healthcare' },
    { value: 'oncology', label: 'Oncology' },
    { value: 'medical_compliance', label: 'Medical Compliance' },
];

function EmployeesTooltip({ names, count, children }: { names?: string[] | null; count: number; children: React.ReactNode }) {
    const [show, setShow] = useState(false);
    if (!names?.length) return <>{children}</>;
    return (
        <span className="relative" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
            {children}
            {show && (
                <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 pointer-events-none">
                    <span className="flex flex-col gap-0.5 bg-zinc-900 border border-white/10 rounded px-2.5 py-2 shadow-xl min-w-[120px]">
                        {names.map((n, i) => (
                            <span key={i} className="text-[10px] text-zinc-200 font-medium whitespace-nowrap">{n}</span>
                        ))}
                        {count > names.length && (
                            <span className="text-[9px] text-zinc-500 font-mono mt-0.5">+{count - names.length} more</span>
                        )}
                    </span>
                    <span className="block w-2 h-2 bg-zinc-900 border-r border-b border-white/10 rotate-45 mx-auto -mt-1" />
                </span>
            )}
        </span>
    );
}

function linkifyText(text: string, linkClass: string) {
    const splitRegex = /(https?:\/\/[^\s,)]+)/g;
    const parts = text.split(splitRegex);
    if (parts.length === 1) return text;
    return parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
            <a key={i} href={part} target="_blank" rel="noopener noreferrer" className={`${linkClass} decoration-current/20 underline-offset-2`}>{part}</a>
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

function getRequirementEmptyStateCopy(category: string, sourceCoverageMissing: boolean = false): string {
    const sourceCoverageCopy = 'Source-of-truth is currently missing this category for this jurisdiction. Run Admin > Jurisdictions research refresh, then sync this location again.';
    if (sourceCoverageMissing) {
        switch (category) {
            case 'minimum_wage':
                return `Coverage pending. This section should include general minimum wage, tipped/tip-credit treatment, and the exempt salary threshold. ${sourceCoverageCopy}`;
            case 'final_pay':
                return `Coverage pending. This section should capture final pay timing for voluntary and involuntary separations, including payout rules for accrued sick/vacation balances. ${sourceCoverageCopy}`;
            case 'minor_work_permit':
                return `Coverage pending. This section should capture minor work permit/certificate requirements and any age- or hour-based limits. ${sourceCoverageCopy}`;
            case 'scheduling_reporting':
                return `Coverage pending. This section should capture fair-workweek/scheduling-notice and reporting-time rules when they apply. ${sourceCoverageCopy}`;
            default:
                return `Coverage pending. ${sourceCoverageCopy}`;
        }
    }
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

const COMPLIANCE_CYCLE_STEPS = [
  {
    id: 1,
    icon: 'locations' as const,
    title: 'Locations',
    description: 'Map applicable laws by pinning business sites.',
    action: 'Click "Add Location" to register a site.',
  },
  {
    id: 2,
    icon: 'research' as const,
    title: 'Research',
    description: 'AI scans federal, state, and local ordinances.',
    action: 'Select a location and click "Check for Updates".',
  },
  {
    id: 3,
    icon: 'alerts' as const,
    title: 'Monitor',
    description: 'Track changes and detected requirements.',
    action: 'Review the "Alerts" tab for attention items.',
  },
  {
    id: 4,
    icon: 'posters' as const,
    title: 'Posters',
    description: 'Order or download mandatory compliance signage.',
    action: 'Navigate to "Posters" for downloads.',
  },
  {
    id: 5,
    icon: 'audit' as const,
    title: 'Audit',
    description: 'Maintain verifiable records of all checks.',
    action: 'View the "Log" for a full audit trail.',
  },
];

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  ...baseLT,
  // ── compliance-specific (light) ───────────────────────────────────────────
  pageBg: 'bg-stone-300',
  cardLight: 'bg-stone-100 rounded-xl',
  cardDark: 'bg-zinc-900 rounded-xl',
  cardDarkHover: 'hover:bg-zinc-800',
  labelOnDark: 'text-xs text-zinc-500 font-semibold',
  livePill: 'bg-stone-200 text-stone-600',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  innerElAlt: 'bg-stone-50',
  alertSync: 'border border-amber-300 bg-amber-50 text-amber-700',
  alertSyncError: 'border border-red-300 bg-red-50 text-red-700',
  alertSyncLink: 'decoration-red-400/50 hover:text-red-800',
  dot: 'bg-stone-300',
  checkBg: 'bg-stone-50',
  dotNominal: 'bg-stone-300',
  dotNominalSmall: 'bg-stone-200',
  emptyBg: 'bg-stone-50',
  contentBg: 'bg-stone-50',
  expandedBg: 'bg-stone-50',
  requirementDivider: 'bg-stone-200',
  requirementItemBg: 'bg-stone-50',
  alertDismissed: 'opacity-50 bg-stone-50 border-stone-200',
  alertActionBg: 'bg-stone-100 border border-stone-200',
  alertBtnHover: 'hover:bg-stone-100',
  neutralBadge: 'bg-stone-100 text-stone-500 border border-stone-200',
  legDismissed: 'bg-stone-100 text-stone-400 border-stone-200',
  posterCancelled: 'bg-stone-100 text-stone-400 border-stone-200',
  authorityLink: 'text-blue-600 hover:text-blue-800',
  impactBg: 'bg-amber-50 border-l-2 border-amber-300',
  impactText: 'text-amber-700',
  coverageMissingBorder: 'border-amber-300',
  coverageMissingBg: 'bg-amber-50',
  coverageMissingTitle: 'text-amber-700',
  coverageMissingText: 'text-amber-800',
  localInfoBg: 'bg-blue-50 border border-blue-200',
  localInfoIcon: 'text-blue-500',
  localInfoText: 'text-blue-700',
  checkManual: 'bg-stone-50 text-stone-500 border-stone-200',
  sourceTypeFallback: 'bg-stone-100 text-stone-500',
  borderInline: 'border-stone-100',
  sourceLinkDecor: 'decoration-stone-300',
  coveragePendingBorder: 'border-stone-200',
  badgeCoverage: 'bg-amber-50 text-amber-600 border-amber-300',
  confidenceHigh: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  confidenceMed: 'bg-amber-50 text-amber-600 border-amber-200',
  confidenceLow: 'bg-red-50 text-red-600 border-red-200',
  legislationProposed: 'bg-blue-50 text-blue-600 border-blue-200',
  legislationPassed: 'bg-amber-50 text-amber-600 border-amber-200',
  legislationEffectiveSoon: 'bg-red-50 text-red-600 border-red-200',
  legislationEffective: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  // modal
  modalBg: 'bg-stone-100 rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  modalAccent: 'bg-stone-300',
  pageInput: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  pageSelect: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',
  dropdownBg: 'bg-stone-50',
  dropdownHeader: 'bg-stone-100',
  listItemSelected: 'bg-stone-200 text-zinc-900',
  listItemHoverText: 'hover:text-zinc-900',
  pageRowHover: 'hover:bg-stone-50',
} as const;

export function Compliance() {
    const t = LT;
    const { user } = useAuth();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const isClient = user?.role === 'client';
    const isAdmin = user?.role === 'admin';

    // Local state for UI-specific interactions
    const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
    const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);

    // Hook instantiation
    const { data: companies } = useQuery({
        queryKey: ['admin-overview'],
        queryFn: () => adminOverview.get(),
        enabled: isAdmin,
    });

    const complianceHook = useCompliance(selectedCompanyId, selectedLocationId, isAdmin);
    const complianceCheckHook = useComplianceCheck(selectedLocationId, selectedCompanyId, () => {});
    const selectedCompanyIndustry = isAdmin
        ? companies?.companies?.find(c => c.id === selectedCompanyId)?.industry ?? undefined
        : undefined;
    const complianceReqHook = useComplianceRequirements(complianceHook.requirements || [], selectedCompanyIndustry);
    const jurisdictionSearchHook = useJurisdictionSearch(complianceHook.jurisdictions || []);

    // Aliases for easier access
    const {
        locations, loadingLocations, requirements, loadingRequirements, alerts, loadingAlerts,
        upcomingLegislation, checkLog, createLocationMutation,
        updateLocationMutation, deleteLocationMutation, markAlertReadMutation, dismissAlertMutation,
        showAddModal, setShowAddModal, editingLocation, setEditingLocation, formData, setFormData,
        useManualEntry, setUseManualEntry, mutationError, setMutationError
    } = complianceHook;

    const { checkInProgress, checkMessages, runComplianceCheck } = complianceCheckHook;
    const { orderedRequirementCategories, sectionedCategories } = complianceReqHook;
    const [sectionedView, setSectionedView] = useState(true);
    const [groupFilter, setGroupFilter] = useState<'all' | CategoryGroup>('all');

    const filteredSections = useMemo(() => {
        if (groupFilter === 'all') return sectionedCategories;
        return sectionedCategories.filter(s => s.id === groupFilter);
    }, [sectionedCategories, groupFilter]);

    const filteredFlatCategories = useMemo(() => {
        if (groupFilter === 'all') return orderedRequirementCategories;
        // Use the filtered sections to get the right categories in order
        const sectionCats = filteredSections.flatMap(s => s.categories);
        return sectionCats;
    }, [groupFilter, orderedRequirementCategories, filteredSections]);
    const { jurisdictionSearch, setJurisdictionSearch, filteredJurisdictions } = jurisdictionSearchHook;
    const latestMissingCoverageCategories = useMemo(() => {
        for (let index = checkMessages.length - 1; index >= 0; index -= 1) {
            const msg = checkMessages[index];
            if (!Array.isArray(msg.missing_categories) || msg.missing_categories.length === 0) continue;
            const normalized = msg.missing_categories
                .map((cat) => normalizeCategoryKey(String(cat)))
                .filter(Boolean);
            if (normalized.length > 0) {
                return Array.from(new Set(normalized));
            }
        }
        return [] as string[];
    }, [checkMessages]);
    const missingCoverageCategorySet = useMemo(
        () => new Set(latestMissingCoverageCategories),
        [latestMissingCoverageCategories],
    );
    const latestMissingCoverageLabel = useMemo(
        () => latestMissingCoverageCategories
            .map((cat) => COMPLIANCE_CATEGORY_LABELS[cat] || cat)
            .join(', '),
        [latestMissingCoverageCategories],
    );

    // UI-specific state (not in hooks)
    const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
    const [activeTab, setActiveTab] = useState<'requirements' | 'alerts' | 'upcoming' | 'history' | 'posters' | 'employees'>('requirements');
    const [expandedAlertSources, setExpandedAlertSources] = useState<Set<string>>(new Set());
    const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
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

    useEffect(() => {
        if (isAdmin && companies?.companies?.length && !selectedCompanyId) {
            setSelectedCompanyId(companies.companies[0].id);
        }
    }, [isAdmin, companies, selectedCompanyId]);

    // Reset selected location when company changes
    useEffect(() => {
        setSelectedLocationId(null);
    }, [selectedCompanyId]);

    // ── Deep-link support ────────────────────────────────────────────────────
    // Honour ?location_id=<uuid>&tab=upcoming&legislation_id=<uuid> so that
    // clicking a dashboard item lands on the exact compliance context.
    const deepLinkApplied = useState(false);
    useEffect(() => {
        if (deepLinkApplied[0]) return;
        if (!locations || locations.length === 0) return;

        const paramLocationId = searchParams.get('location_id');
        const paramTab = searchParams.get('tab') as typeof activeTab | null;
        const paramLegislationId = searchParams.get('legislation_id');

        if (!paramLocationId) return;
        const match = locations.find(l => l.id === paramLocationId);
        if (!match) return;

        deepLinkApplied[1](true);
        setSelectedLocationId(paramLocationId);

        if (paramTab === 'upcoming' || paramTab === 'alerts' || paramTab === 'requirements' || paramTab === 'history' || paramTab === 'posters') {
            setActiveTab(paramTab);
        }

        if (paramLegislationId) {
            // Scroll to the legislation card after a short render delay
            setTimeout(() => {
                const el = document.getElementById(`legislation-${paramLegislationId}`);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.classList.add('ring-1', 'ring-emerald-500/50');
                    setTimeout(() => el.classList.remove('ring-1', 'ring-emerald-500/50'), 3000);
                }
            }, 400);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [locations]);

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

    const showJurisdictionPicker = (isClient || isAdmin) && !editingLocation && !useManualEntry;
    const makeJurisdictionKey = (j: JurisdictionOption) => `${j.city}|${j.state}|${j.county || ''}`;

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

    const renderCategoryAccordion = (category: string, reqs: ComplianceRequirement[]) => (
        <div key={category} className={t.requirementItemBg}>
            <button
                onClick={() => toggleCategory(category)}
                className={`w-full flex items-center justify-between p-5 ${t.cardBg} ${t.rowHover} transition-colors ${t.cardHeader}`}
            >
                <div className="flex items-center gap-4">
                    <div className="flex flex-col items-start">
                        <span className={`${t.textMain} text-[11px] font-bold uppercase tracking-widest`}>
                            {COMPLIANCE_CATEGORY_LABELS[category] || category}
                        </span>
                        <span className={`text-[8px] ${t.textFaint} font-mono uppercase tracking-[0.2em] mt-0.5`}>
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
                        <span className={`px-2 py-0.5 text-[8px] rounded-xs border font-bold uppercase tracking-[0.2em] ${
                            missingCoverageCategorySet.has(category)
                                ? t.badgeCoverage
                                : `${t.cardBg} ${t.textMuted} ${t.coveragePendingBorder}`
                        }`}>
                            {missingCoverageCategorySet.has(category) ? 'Missing Source Coverage' : 'Coverage Pending'}
                        </span>
                    )}
                </div>
                <motion.div
                    animate={{ rotate: expandedCategories.has(category) ? 180 : 0 }}
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                >
                    <ChevronDown size={14} className={t.textFaint} />
                </motion.div>
            </button>

            <AnimatePresence initial={false}>
                {expandedCategories.has(category) && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                        className={`overflow-hidden ${t.expandedBg}`}
                    >
                        <div className={`divide-y ${t.divide} px-2`}>
                            {reqs.length === 0 ? (
                                <div className={`p-6 ${t.textMuted} text-xs leading-relaxed font-light`}>
                                    {getRequirementEmptyStateCopy(category, missingCoverageCategorySet.has(category))}
                                </div>
                            ) : (
                                reqs.map(req => (
                                    <div key={req.id} className={`p-6 ${t.rowHover} transition-colors rounded-lg`}>
                                        <div className="flex items-start justify-between mb-4 gap-6">
                                            <div className="flex-1">
                                                <h4 className={`${t.textMain} text-xs font-bold uppercase tracking-wide mb-2`}>
                                                    {req.title}
                                                </h4>
                                                <div className="flex items-center gap-3">
                                                    <span className={`px-1.5 py-0.5 ${t.cardBg} border ${t.border} text-[8px] uppercase tracking-widest ${t.textMuted} font-bold rounded-xs`}>
                                                        {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                                                    </span>
                                                    {req.category === 'minimum_wage' && req.rate_type && (
                                                        <span className={`px-1.5 py-0.5 ${t.cardBg} border ${t.border} text-[8px] uppercase tracking-widest ${t.textDim} font-bold rounded-xs`}>
                                                            {RATE_TYPE_LABELS[req.rate_type] || req.rate_type.replace(/_/g, ' ')}
                                                        </span>
                                                    )}
                                                    {req.applicable_industries?.includes('healthcare') && (
                                                        <span className="px-1.5 py-0.5 bg-cyan-50 border border-cyan-200 text-[8px] uppercase tracking-widest text-cyan-700 font-bold rounded-xs">
                                                            Medical
                                                        </span>
                                                    )}
                                                    {(req.affected_employee_count ?? 0) > 0 && (
                                                        <EmployeesTooltip names={req.affected_employee_names} count={req.affected_employee_count!}>
                                                            <span className="px-1.5 py-0.5 bg-violet-50 border border-violet-200 text-[8px] uppercase tracking-widest text-violet-600 font-bold rounded-xs cursor-default">
                                                                {req.affected_employee_count} employee{req.affected_employee_count !== 1 ? 's' : ''}
                                                            </span>
                                                        </EmployeesTooltip>
                                                    )}
                                                    {(req.min_wage_violation_count ?? 0) > 0 && (
                                                        <span className="px-1.5 py-0.5 bg-red-50 border border-red-200 text-[8px] uppercase tracking-widest text-red-600 font-bold rounded-xs">
                                                            {req.min_wage_violation_count} below threshold
                                                        </span>
                                                    )}
                                                    <span className={`${t.textFaint} text-[9px] font-mono uppercase tracking-tighter`}>
                                                        Node: {req.jurisdiction_name}
                                                    </span>
                                                </div>
                                            </div>
                                            {req.current_value && (
                                                <span className={`${t.statusOk} font-mono text-xs bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-lg`}>
                                                    {req.current_value}
                                                </span>
                                            )}
                                        </div>
                                        {req.description && (
                                            <p className={`${t.textMuted} text-xs leading-relaxed mb-6 max-w-2xl font-light`}>
                                                {req.description}
                                            </p>
                                        )}
                                        <div className={`flex items-center justify-between pt-4 border-t ${t.borderInline}`}>
                                            <div className="flex items-center gap-4">
                                                {req.effective_date && (
                                                    <div className={`flex items-center gap-2 text-[8px] ${t.textFaint} uppercase tracking-widest font-mono`}>
                                                        <Calendar size={10} className="opacity-40" />
                                                        Enforced: {new Date(req.effective_date).toLocaleDateString()}
                                                    </div>
                                                )}
                                                <button
                                                    onClick={() => complianceHook.pinRequirementMutation.mutate({ id: req.id, isPinned: !req.is_pinned })}
                                                    title={req.is_pinned ? 'Unpin from dashboard' : 'Pin to dashboard'}
                                                    className={`flex items-center gap-1.5 text-[8px] uppercase tracking-widest font-mono transition-colors ${req.is_pinned ? 'text-amber-500' : `${t.textFaint} hover:text-amber-500`}`}
                                                >
                                                    <Pin size={10} className={req.is_pinned ? 'fill-amber-500' : 'opacity-40'} />
                                                    {req.is_pinned ? 'Pinned' : 'Pin'}
                                                </button>
                                            </div>
                                            {req.source_url && (
                                                <a
                                                    href={req.source_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className={`text-[9px] font-bold uppercase tracking-widest ${t.textMuted} ${t.linkHover} flex items-center gap-1.5 transition-colors`}
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
    );

    const getSeverityStyles = (severity: string) => {
        if (!isLight) {
            switch (severity) {
                case 'critical':  return 'bg-red-500/10 text-red-400 border-red-500/20';
                case 'warning':   return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
                default:          return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
            }
        }
        switch (severity) {
            case 'critical':  return 'bg-red-50 text-red-600 border-red-200';
            case 'warning':   return 'bg-amber-50 text-amber-600 border-amber-200';
            default:          return 'bg-blue-50 text-blue-600 border-blue-200';
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
        if (score >= 0.6) return { label: `${pct}%`, color: t.confidenceHigh, tag: 'Verified' };
        if (score >= 0.3) return { label: `${pct}%`, color: t.confidenceMed, tag: 'Unverified' };
        return { label: `${pct}%`, color: t.confidenceLow, tag: 'Low Confidence' };
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

    const totalRequirements = locations?.reduce((s, l) => s + (l.requirements_count || 0), 0) ?? 0;
    const totalAlerts = locations?.reduce((s, l) => s + (l.unread_alerts_count || 0), 0) ?? 0;
    const totalEmployees = locations?.reduce((s, l) => s + (l.employee_count || 0), 0) ?? 0;

    return (
        <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="max-w-7xl mx-auto space-y-5 pb-24">

            {/* Header */}
            <div className="flex justify-between items-start pb-6">
                <div>
                    <div className="flex items-center gap-3">
                        <h1 className={`text-3xl font-bold tracking-tight ${t.textMain}`}>
                            Compliance <FeatureGuideTrigger guideId="compliance" />
                        </h1>
                        <div className={`px-2.5 py-0.5 ${t.livePill} text-[10px] font-bold rounded-full`}>
                            {locations?.length ?? 0} Locations
                        </div>
                    </div>
                    <p className={`text-[10px] ${t.textMuted} mt-1.5 font-mono tracking-wide`}>Regulatory Monitoring</p>
                    {isAdmin && companies?.companies && companies.companies.length > 0 && (
                        <div className="mt-2 flex items-center gap-2">
                            <span className="text-xs text-stone-500">Company:</span>
                            <select
                                data-tour="compliance-company-select"
                                value={selectedCompanyId || ''}
                                onChange={e => setSelectedCompanyId(e.target.value)}
                                className="text-xs bg-white border border-stone-300 rounded-lg text-zinc-900 px-2 py-1 focus:outline-none focus:border-stone-400"
                            >
                                {companies.companies.map(c => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                ))}
                            </select>
                        </div>
                    )}
                </div>
                <div className="flex gap-2">
                    {wizardReturnPath && (
                        <button
                            onClick={() => navigate(wizardReturnPath)}
                            className={`px-4 py-2 ${t.btnSecondary} rounded-lg text-[10px] font-bold transition-all`}
                        >
                            Return to Handbook
                        </button>
                    )}
                    <button
                        onClick={() => setShowAddModal(true)}
                        className={`px-4 py-2 ${t.btnPrimary} rounded-lg text-[10px] font-bold transition-all flex items-center gap-1.5`}
                    >
                        <MapPin size={12} />
                        Add Location
                    </button>
                </div>
            </div>

            {/* Stat Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                    { label: 'Locations', value: locations?.length ?? 0, icon: MapPin, change: 'business sites' },
                    { label: 'Requirements', value: totalRequirements, icon: Layers, change: 'tracked nodes' },
                    { label: 'Alerts', value: totalAlerts, icon: Bell, change: 'need attention', urgent: totalAlerts > 0 },
                    { label: 'Employees', value: totalEmployees, icon: Users, change: 'covered' },
                ].map((stat) => (
                    <div key={stat.label} className={`${t.cardDark} p-5 relative overflow-hidden`}>
                        <div className="absolute top-0 right-0 p-3 text-zinc-800">
                            <stat.icon className="w-8 h-8" strokeWidth={0.5} />
                        </div>
                        <div className="relative z-10">
                            <div className={`${t.labelOnDark} mb-2`}>{stat.label}</div>
                            <div className={`text-3xl font-light font-mono mb-0.5 tabular-nums ${stat.urgent ? 'text-amber-400' : 'text-zinc-50'}`}>
                                {stat.value}
                            </div>
                            <div className="text-[9px] text-zinc-500 font-mono">{stat.change}</div>
                        </div>
                    </div>
                ))}
            </div>

            <LifecycleWizard
              steps={COMPLIANCE_CYCLE_STEPS}
              activeStep={
                (locations && locations.some(l => (l.unread_alerts_count || 0) > 0)) ? 3
                : (locations && locations.some(l => (l.requirements_count || 0) > 0)) ? 2
                : (locations && locations.length > 0) ? 2
                : 1
              }
              storageKey="compliance-wizard-collapsed-v1"
              title="Compliance Lifecycle"
            />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div data-tour="compliance-locations" className="lg:col-span-1">
                    <div className={`${t.cardLight} p-3`}>
                    <div className={`${t.label} mb-3 px-1`}>Locations <span className="font-mono normal-case">[{locations?.length || 0}]</span></div>

                    {syncStates.size > 0 && (
                        <div className={`${t.alertSync} px-3 py-2 rounded-lg text-xs space-y-1 mb-2`}>
                            <p className="font-medium uppercase tracking-wider">Handbook requires compliance sync</p>
                            <p>
                                Run <strong>Sync Compliance</strong> for each highlighted location below, then return to your handbook.
                            </p>
                        </div>
                    )}

                    {syncStates.size > 0 && !loadingLocations && (() => {
                        const coveredStates = new Set((locations || []).map(l => (l.state || '').toUpperCase()));
                        const missingStates = [...syncStates].filter(s => !coveredStates.has(s));
                        if (missingStates.length === 0) return null;
                        return (
                            <div className={`${t.alertSyncError} px-3 py-2 rounded-lg text-xs space-y-1 mb-2`}>
                                <p className="font-medium uppercase tracking-wider">Location required for compliance sync</p>
                                <p>
                                    Add a location in <strong>{missingStates.join(', ')}</strong> to your compliance dashboard,
                                    then run <strong>Sync Compliance</strong> to populate handbook coverage data.{' '}
                                    <button
                                        onClick={() => setShowAddModal(true)}
                                        className={`underline underline-offset-2 ${t.alertSyncLink} transition-colors`}
                                    >
                                        Add Location
                                    </button>
                                </p>
                            </div>
                        );
                    })()}

                    {loadingLocations ? (
                        <div className="space-y-1">
                            {[1, 2, 3].map(i => (
                                <div key={i} className={`${t.innerEl} p-4 animate-pulse h-16`} />
                            ))}
                        </div>
                    ) : locations?.length === 0 ? (
                        <div className="py-12 px-4 text-center">
                            <div className={`w-10 h-10 mx-auto mb-4 rounded-full ${t.innerEl} flex items-center justify-center opacity-40`}>
                                <MapPin size={16} className={t.textMuted} />
                            </div>
                            <h3 className={`${t.textDim} text-[10px] font-bold uppercase tracking-widest mb-1`}>No Locations Yet</h3>
                            <p className={`${t.textFaint} text-[10px] leading-relaxed`}>
                                Locations are created automatically when employees are onboarded.
                            </p>
                        </div>
                    ) : (
                    <div className="space-y-1">
                        {locations?.map(location => (
                            <motion.div
                                layout
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                key={location.id}
                                onClick={() => setSelectedLocationId(location.id)}
                                className={`rounded-lg p-2.5 cursor-pointer transition-all duration-200 group relative overflow-hidden ${
                                    selectedLocationId === location.id
                                        ? 'bg-stone-300'
                                        : syncStates.has((location.state || '').toUpperCase())
                                            ? 'bg-amber-100 hover:bg-amber-200'
                                            : t.innerHover
                                }`}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="min-w-0 flex-1">
                                        {/* Row 1: name + badges + employee count */}
                                        <div className="flex items-center gap-1.5 flex-wrap">
                                            <h3 className={`font-bold text-xs truncate uppercase tracking-widest ${
                                                selectedLocationId === location.id ? t.textMain : t.textDim
                                            }`}>
                                                {location.name || `${location.city}, ${location.state}`}
                                            </h3>
                                            {location.has_local_ordinance && (
                                                <span className={`text-[7px] px-1 py-0.5 ${t.neutralBadge} rounded-xs uppercase tracking-widest`}>Local</span>
                                            )}
                                            {location.source === 'employee_derived' && (
                                                <span className={`text-[7px] px-1 py-0.5 rounded ${t.badgeBlue} uppercase tracking-widest`}>
                                                    Auto
                                                </span>
                                            )}
                                            {location.coverage_status === 'pending_review' && (
                                                <span className={`text-[7px] px-1 py-0.5 rounded ${t.badgeAmber} uppercase tracking-widest`}
                                                      title="Platform admin is reviewing this jurisdiction">
                                                    Pending
                                                </span>
                                            )}
                                            <EmployeesTooltip names={location.employee_names} count={location.employee_count ?? 0}>
                                                <span className={`ml-auto flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-bold ${t.textMuted} cursor-default hover:text-zinc-200 transition-colors`}>
                                                    <Users size={12} />
                                                    {location.employee_count ?? 0}
                                                </span>
                                            </EmployeesTooltip>
                                        </div>
                                        {/* Row 2: stats — only show city/state subtext when name differs */}
                                        {location.name && location.name !== `${location.city}, ${location.state}` && (
                                            <p className={`${t.textFaint} text-[9px] truncate font-mono uppercase tracking-tighter leading-none mt-0.5`}>
                                                {location.city}, {location.state}
                                            </p>
                                        )}
                                        <div className="flex items-center gap-2.5 mt-1">
                                            <span className={`text-[8px] font-bold uppercase tracking-[0.15em] ${t.textMuted}`}>
                                                {location.requirements_count} Nodes
                                            </span>
                                            {location.unread_alerts_count > 0 && (
                                                <span className="text-amber-500 flex items-center gap-0.5 text-[8px] font-bold uppercase tracking-[0.15em] animate-pulse">
                                                    <Bell size={7} />
                                                    {location.unread_alerts_count}
                                                </span>
                                            )}
                                            {location.data_status === 'needs_research' && (
                                                <span className={`text-[7px] px-1 py-0.5 rounded ${t.badgeRed} uppercase tracking-wider font-bold`}>
                                                    Research
                                                </span>
                                            )}
                                            {location.data_status === 'available' && (
                                                <span className={`text-[7px] px-1 py-0.5 rounded ${t.badgeEmerald} uppercase tracking-wider font-bold`}>
                                                    Ready
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                        {confirmDeleteId === location.id ? (
                                            (location.employee_count && location.employee_count > 0) ? (
                                                <>
                                                    <span className="text-[9px] text-amber-400 font-mono uppercase tracking-wider mr-1">
                                                        {location.employee_count} employee{location.employee_count > 1 ? 's' : ''} linked
                                                    </span>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setConfirmDeleteId(null);
                                                        }}
                                                        className={`px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ${t.textMuted} border ${t.border} rounded transition-colors`}
                                                    >
                                                        OK
                                                    </button>
                                                </>
                                            ) : (
                                            <>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        deleteLocationMutation.mutate(location.id);
                                                        setConfirmDeleteId(null);
                                                    }}
                                                    className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-red-400 border border-red-500/30 rounded hover:bg-red-500/10 transition-colors"
                                                >
                                                    Delete
                                                </button>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setConfirmDeleteId(null);
                                                    }}
                                                    className={`px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ${t.textMuted} border ${t.border} rounded transition-colors`}
                                                >
                                                    Cancel
                                                </button>
                                            </>
                                            )
                                        ) : (
                                            <>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        openEditModal(location);
                                                        setShowAddModal(true);
                                                    }}
                                                    className={`p-1.5 ${t.textFaint} ${t.btnGhost} rounded transition-colors`}
                                                    title="Edit"
                                                >
                                                    <Edit2 size={11} />
                                                </button>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setConfirmDeleteId(location.id);
                                                    }}
                                                    className={`p-1.5 ${t.textFaint} hover:text-red-500 rounded transition-colors`}
                                                    title={location.employee_count && location.employee_count > 0 ? `Cannot delete: ${location.employee_count} employee(s) linked` : 'Delete'}
                                                >
                                                    <Trash2 size={11} />
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                    )}
                    </div>{/* end cardLight */}
                </div>

                <div data-tour="compliance-content" className="lg:col-span-2">
                    {mutationError && (
                        <div className={`mb-4 flex items-center justify-between gap-4 px-4 py-3 ${t.badgeRed} rounded-lg text-[10px] font-mono uppercase tracking-widest`}>
                            <span>{mutationError}</span>
                            <button onClick={() => setMutationError(null)} className={`${t.statusErr} hover:opacity-70 transition-colors`}>
                                <X size={12} />
                            </button>
                        </div>
                    )}
                    {selectedLocationId && selectedLocation ? (
                        <ContentCard className="min-h-[600px] flex flex-col">
                            <div className={`px-5 py-3 ${t.cardHeader} ${t.cardBg} flex items-center justify-between gap-4`}>
                                <div className="flex items-center gap-3 min-w-0">
                                    <div className={`w-7 h-7 rounded-lg ${t.innerEl} border ${t.border} flex items-center justify-center flex-shrink-0`}>
                                        <Building2 size={13} className={t.textDim} />
                                    </div>
                                    <div className="min-w-0">
                                        <h2 className={`text-[13px] font-bold ${t.textMain} uppercase tracking-tight leading-none`}>
                                            {selectedLocation.name || `${selectedLocation.city}, ${selectedLocation.state}`}
                                        </h2>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className={`text-[9px] ${t.textMuted} font-mono uppercase tracking-widest`}>
                                                {selectedLocation.city}, {selectedLocation.state}{selectedLocation.zipcode ? ` ${selectedLocation.zipcode}` : ''}
                                            </span>
                                            {selectedLocation.last_compliance_check && (
                                                <>
                                                    <div className={`w-1 h-1 rounded-full ${t.dot} flex-shrink-0`} />
                                                    <span className={`text-[9px] ${t.textFaint} font-mono uppercase tracking-widest`}>
                                                        Synced {new Date(selectedLocation.last_compliance_check).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
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
                                        await runComplianceCheck();
                                    }}
                                    className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 ${t.btnPrimary} text-[9px] font-bold uppercase tracking-[0.2em] transition-all disabled:opacity-50 rounded-lg`}
                                >
                                    {checkInProgress ? (
                                        <><Loader2 size={10} className="animate-spin" /> Scanning</>
                                    ) : (
                                        <><Zap size={10} /> Sync</>
                                    )}
                                </button>
                            </div>

                            {checkMessages.length > 0 && (
                                <motion.div
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    className={`${t.cardHeader} ${t.checkBg} overflow-hidden`}
                                >
                                    <div className={`flex items-center gap-4 px-8 py-3 ${t.cardHeader} text-[8px] uppercase tracking-[0.3em] font-bold ${t.textFaint}`}>
                                        <div className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> New</div>
                                        <div className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-amber-500" /> Delta</div>
                                        <div className="flex items-center gap-1.5"><div className={`w-1.5 h-1.5 rounded-full ${t.dotNominal}`} /> Nominal</div>
                                    </div>
                                    <div className="px-8 py-4 space-y-2 max-h-48 overflow-y-auto font-mono">
                                        {checkMessages.map((msg, i) => (
                                            <div key={i} className="flex items-start gap-3 text-[10px] leading-relaxed">
                                                {msg.type === 'result' ? (
                                                    <span className={`flex-shrink-0 mt-0.5 px-1.5 py-0.5 rounded-xs font-bold border ${
                                                        msg.status === 'new' ? t.badgeNew :
                                                        msg.status === 'updated' ? t.badgeUpdated :
                                                        t.badgeNominal
                                                    }`}>
                                                        {msg.status?.toUpperCase()}
                                                    </span>
                                                ) : (
                                                    <div className={`w-1.5 h-1.5 rounded-full ${t.dotNominalSmall} mt-1.5 flex-shrink-0`} />
                                                )}
                                                <span className={
                                                    msg.type === 'error' ? t.statusErr :
                                                    msg.type === 'completed' ? `${t.textMain} font-bold` :
                                                    t.textMuted
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

                            <div data-tour="compliance-tabs" className={`${t.cardHeader} ${t.cardBg} px-4 pt-2`}>
                                <Tabs
                                    tabs={[
                                        { id: 'requirements', label: 'Matrix', count: requirements?.length },
                                        { id: 'alerts', label: 'Alerts', count: locationAlerts.length, badge: !!unreadAlertsCount },
                                        { id: 'upcoming', label: 'Future', count: upcomingLegislation?.length },
                                        { id: 'history', label: 'Log' },
                                        { id: 'posters', label: 'Vault' },
                                        { id: 'employees', label: 'Employees', count: selectedLocation?.employee_count ?? 0 },
                                    ]}
                                    activeTab={activeTab}
                                    onTabChange={(id) => setActiveTab(id as typeof activeTab)}
                                    variant="light"
                                    controls={activeTab === 'requirements' ? (
                                        <>
                                            <select
                                                value={groupFilter}
                                                onChange={e => setGroupFilter(e.target.value as 'all' | CategoryGroup)}
                                                className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1.5 rounded-lg border ${t.border} ${t.cardBg} ${t.textMuted} bg-transparent cursor-pointer focus:outline-none`}
                                            >
                                                {GROUP_FILTER_OPTIONS.map(opt => (
                                                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                                                ))}
                                            </select>
                                            {sectionedCategories.length > 1 && (
                                                <button
                                                    onClick={() => setSectionedView(v => !v)}
                                                    className={`p-2 rounded-lg border ${t.border} ${t.cardBg} ${t.rowHover} transition-colors flex-shrink-0`}
                                                    title={sectionedView ? 'Switch to flat view' : 'Switch to sectioned view'}
                                                >
                                                    {sectionedView
                                                        ? <LayoutList size={13} className={t.textMuted} />
                                                        : <Layers size={13} className={t.textMuted} />
                                                    }
                                                </button>
                                            )}
                                        </>
                                    ) : undefined}
                                >
                                    {() => <></>}
                                </Tabs>
                            </div>

                            {selectedLocation?.has_local_ordinance === false && (
                                <div className={`px-5 py-1 flex items-center gap-2 border-b ${t.border}`}>
                                    <Info size={10} className={`${t.localInfoIcon} flex-shrink-0`} />
                                    <span className={`text-[9px] font-bold uppercase tracking-[0.15em] ${t.localInfoText}`}>
                                        State-inherited · No local ordinances
                                        {(selectedLocation.county || selectedLocation.state) && (
                                            <span className={`font-normal ${t.textFaint} ml-1`}>
                                                — {selectedLocation.county ? `${selectedLocation.county} County / ` : ''}{selectedLocation.state}
                                            </span>
                                        )}
                                    </span>
                                </div>
                            )}

                            <div className={`p-4 flex-1 ${t.contentBg} overflow-y-auto`}>
                                {activeTab === 'employees' ? (
                                    <div className="space-y-2">
                                        {(selectedLocation?.employee_names?.length ?? 0) === 0 ? (
                                            <p className={`${t.textFaint} text-[10px] font-mono uppercase tracking-widest py-8 text-center`}>No employees assigned to this location.</p>
                                        ) : (
                                            selectedLocation!.employee_names!.map((name, i) => (
                                                <div key={i} className={`${t.cardBg} border ${t.border} rounded-lg px-5 py-3 flex items-center gap-3`}>
                                                    <div className={`w-7 h-7 rounded-full bg-violet-500/10 border border-violet-500/20 flex items-center justify-center flex-shrink-0`}>
                                                        <span className="text-[10px] font-bold text-violet-400">{name.charAt(0).toUpperCase()}</span>
                                                    </div>
                                                    <span className={`text-xs font-medium ${t.textMain}`}>{name}</span>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                ) : activeTab === 'posters' ? (
                                    postersLoading ? (
                                        <div className="space-y-4">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className={`h-16 ${t.cardBg} border ${t.border} rounded animate-pulse`} />
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="space-y-6">
                                            {/* Available posters by location */}
                                            <div>
                                                <h3 className={`text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-4 pb-2 ${t.cardHeader}`}>Available Posters</h3>
                                                {availablePosters.length === 0 ? (
                                                    <p className={`${t.textFaint} text-[10px] font-mono uppercase tracking-widest`}>No templates generated for this endpoint context.</p>
                                                ) : (
                                                    <div className="space-y-2">
                                                        {availablePosters.map(poster => (
                                                            <div key={poster.location_id} className={`${t.cardBg} border ${t.border} rounded-lg p-5 flex items-center justify-between group ${t.rowHover} transition-colors`}>
                                                                <div>
                                                                    <div className={`text-xs font-bold ${t.textMain} uppercase tracking-widest`}>
                                                                        {poster.location_city}, {poster.location_state}
                                                                        {poster.location_name && <span className={`${t.textMuted} ml-2 font-light`}>({poster.location_name})</span>}
                                                                    </div>
                                                                    {poster.template_title && (
                                                                        <div className={`text-[9px] ${t.textMuted} mt-1.5 font-mono uppercase tracking-tighter`}>
                                                                            {poster.template_title}
                                                                            {poster.template_version && <span className={`${t.textFaint} ml-2 font-bold`}>v{poster.template_version}</span>}
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
                                                                                className={`px-4 py-2 text-[9px] font-bold uppercase tracking-widest ${t.innerEl} ${t.textDim} rounded-xs transition-all`}
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
                                                                                <span className={`px-2.5 py-1 text-[8px] font-bold uppercase tracking-widest ${t.badgeBlue} rounded-xs border`}>
                                                                                    Order Logged
                                                                                </span>
                                                                            )}
                                                                        </>
                                                                    )}
                                                                    {poster.template_status === 'pending' && (
                                                                        <span className={`px-2.5 py-1 text-[8px] font-bold uppercase tracking-widest ${t.badgeAmber} rounded-xs border animate-pulse`}>
                                                                            Synthesis Pending
                                                                        </span>
                                                                    )}
                                                                    {!poster.template_id && (
                                                                        <span className={`text-[9px] ${t.textDim} font-mono uppercase tracking-widest`}>Unavailable</span>
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
                                                    <h3 className={`text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-4 pb-2 ${t.cardHeader}`}>Vault History</h3>
                                                    <div className="space-y-2">
                                                        {posterOrders.map(order => (
                                                            <div key={order.id} className={`${t.cardBg} border ${t.border} rounded-lg p-5 ${t.rowHover} transition-colors`}>
                                                                <div className="flex items-center justify-between">
                                                                    <div>
                                                                        <div className={`text-xs font-bold ${t.textDim} uppercase tracking-widest`}>
                                                                            {order.location_city}, {order.location_state}
                                                                            {order.location_name && <span className={`${t.textFaint} ml-2`}>({order.location_name})</span>}
                                                                        </div>
                                                                        <div className={`text-[9px] ${t.textFaint} mt-1.5 font-mono uppercase tracking-tighter`}>
                                                                            {order.items.map(i => i.template_title || i.jurisdiction_name).join(' // ')}
                                                                            {' \u00b7 '}{order.created_at ? new Date(order.created_at).toLocaleDateString() : ''}
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex items-center gap-3">
                                                                        <span className={`px-2 py-1 text-[8px] font-bold uppercase tracking-widest rounded-xs border ${
                                                                            order.status === 'delivered' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' :
                                                                            order.status === 'shipped' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                                                            order.status === 'cancelled' ? t.posterCancelled :
                                                                            t.badgeBlue
                                                                        }`}>
                                                                            {order.status}
                                                                        </span>
                                                                        {order.tracking_number && (
                                                                            <span className={`text-[9px] ${t.textFaint} font-mono tracking-tighter`}>#{order.tracking_number}</span>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                                {order.quote_amount != null && (
                                                                    <div className={`text-[9px] ${t.textFaint} mt-3 font-mono uppercase tracking-widest`}>Settlement: ${order.quote_amount.toFixed(2)}</div>
                                                                )}
                                                                {order.admin_notes && (
                                                                    <div className={`text-[9px] ${t.textFaint} mt-1.5 italic font-serif`}>Note: {order.admin_notes}</div>
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
                                        <div className={`text-center py-24 border border-dashed ${t.border} ${t.emptyBg}`}>
                                            <div className={`w-12 h-12 mx-auto mb-6 rounded-full ${t.cardBg} border ${t.border} flex items-center justify-center opacity-40`}>
                                                <Calendar size={20} className={t.textMuted} />
                                            </div>
                                            <p className={`${t.textFaint} text-[10px] font-mono uppercase tracking-[0.2em]`}>Zero Future Deltas Detected</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {upcomingLegislation.map(leg => {
                                                const statusColors: Record<string, string> = {
                                                    proposed: t.legislationProposed,
                                                    passed: t.legislationPassed,
                                                    signed: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
                                                    effective_soon: t.legislationEffectiveSoon,
                                                    effective: t.legislationEffective,
                                                    dismissed: t.legDismissed,
                                                };
                                                const isEffectiveNow = leg.days_until_effective !== null && leg.days_until_effective <= 0;
                                                const displayStatus = isEffectiveNow ? 'effective' : leg.current_status;
                                                return (
                                                    <div key={leg.id} id={`legislation-${leg.id}`} className={`border ${t.border} rounded-lg p-6 ${t.cardBg} ${t.rowHover} transition-colors`}>
                                                        <div className="flex items-start justify-between gap-6">
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-3 flex-wrap mb-2">
                                                                    <h4 className={`text-sm font-bold ${t.textMain} uppercase tracking-tight truncate`}>{leg.title}</h4>
                                                                    <span className={`text-[8px] px-1.5 py-0.5 border rounded-xs font-bold uppercase tracking-widest ${statusColors[displayStatus] || t.legDismissed}`}>
                                                                        {displayStatus.replace('_', ' ')}
                                                                    </span>
                                                                    {leg.category && (
                                                                        <span className={`text-[8px] px-1.5 py-0.5 ${t.neutralBadge} rounded-xs uppercase tracking-widest`}>
                                                                            {COMPLIANCE_CATEGORY_LABELS[leg.category] || leg.category}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                {leg.description && (
                                                                    <p className={`text-[11px] ${t.textMuted} leading-relaxed mb-4 font-light`}>{leg.description}</p>
                                                                )}
                                                                {leg.impact_summary && (
                                                                    <div className={`p-3 ${t.impactBg} mb-4`}>
                                                                        <p className={`text-[10px] ${t.impactText} leading-relaxed`}>
                                                                            <span className="font-bold uppercase tracking-wider text-[8px] mr-2">Impact Analysis:</span> {leg.impact_summary}
                                                                        </p>
                                                                    </div>
                                                                )}
                                                                <div className={`flex items-center gap-6 text-[9px] font-mono ${t.textFaint} uppercase tracking-widest`}>
                                                                    {leg.expected_effective_date && (
                                                                        <span className="flex items-center gap-2">
                                                                            <Calendar size={10} className="opacity-40" />
                                                                            {new Date(leg.expected_effective_date).toLocaleDateString()}
                                                                            {leg.days_until_effective !== null && (
                                                                                <span className={`ml-1 font-bold ${
                                                                                    leg.days_until_effective <= 30 ? 'text-red-500' :
                                                                                    leg.days_until_effective <= 90 ? 'text-amber-500' :
                                                                                    t.textMuted
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
                                                                        <a href={leg.source_url} target="_blank" rel="noopener noreferrer" className={`${t.authorityLink} flex items-center gap-1.5 transition-colors`}>
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
                                        <div className={`text-center py-24 border border-dashed ${t.border} ${t.emptyBg}`}>
                                            <div className={`w-12 h-12 mx-auto mb-6 rounded-full ${t.cardBg} border ${t.border} flex items-center justify-center opacity-40`}>
                                                <History size={20} className={t.textMuted} />
                                            </div>
                                            <p className={`${t.textFaint} text-[10px] font-mono uppercase tracking-[0.2em]`}>Zero Sync Events</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-1.5">
                                            {checkLog.map(entry => (
                                                <div key={entry.id} className={`flex items-center gap-6 p-4 border ${t.border} rounded-lg ${t.cardBg} ${t.rowHover} transition-colors group`}>
                                                    <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 shadow-sm ${
                                                        entry.status === 'completed' ? 'bg-emerald-500 shadow-emerald-500/20' :
                                                        entry.status === 'failed' ? 'bg-red-500 shadow-red-500/20' :
                                                        'bg-amber-500 animate-pulse'
                                                    }`} />
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-4">
                                                            <span className={`text-[8px] px-1.5 py-0.5 rounded-xs border font-bold uppercase tracking-widest ${
                                                                entry.check_type === 'scheduled' ? t.badgeBlue :
                                                                entry.check_type === 'proactive' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                                                t.checkManual
                                                            }`}>
                                                                {entry.check_type}
                                                            </span>
                                                            <span className={`text-[10px] ${t.textMuted} font-mono uppercase tracking-tighter`}>
                                                                {new Date(entry.started_at).toLocaleString(undefined, {
                                                                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                                                                })}
                                                            </span>
                                                        </div>
                                                        {entry.status === 'completed' && (
                                                            <p className={`text-[9px] ${t.textFaint} mt-1.5 font-mono uppercase tracking-tighter`}>
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
                                    <>
                                    {latestMissingCoverageCategories.length > 0 && (
                                        <div className={`mb-4 p-4 border ${t.coverageMissingBorder} ${t.coverageMissingBg} rounded-lg`}>
                                            <p className={`text-[10px] font-bold uppercase tracking-[0.2em] ${t.coverageMissingTitle}`}>
                                                Source Coverage Missing
                                            </p>
                                            <p className={`mt-2 text-[11px] ${t.coverageMissingText} leading-relaxed`}>
                                                This jurisdiction is still missing verified source-of-truth coverage for: <span className="font-semibold">{latestMissingCoverageLabel}</span>. Run Admin &gt; Jurisdictions research refresh, then sync this location again.
                                            </p>
                                        </div>
                                    )}
                                    {loadingRequirements ? (
                                        <div className="space-y-4">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className={`h-16 ${t.cardBg} border ${t.border} rounded animate-pulse`} />
                                            ))}
                                        </div>
                                    ) : orderedRequirementCategories.length === 0 ? (
                                        <div className={`text-center py-24 ${t.textFaint} text-[10px] font-mono uppercase tracking-[0.2em] border border-dashed ${t.border} ${t.emptyBg}`}>
                                            Zero Nodes Detected
                                        </div>
                                    ) : sectionedView ? (
                                        <div className="space-y-6">
                                            {filteredSections.map((section) => (
                                                <div key={section.id}>
                                                    {filteredSections.length > 1 && (
                                                        <div className="flex items-center gap-3 mb-2">
                                                            <div className={`flex-1 h-px ${t.border} border-t`} />
                                                            <span className={`text-[9px] font-bold uppercase tracking-[0.25em] ${t.textFaint} flex-shrink-0`}>
                                                                {section.label}
                                                                {section.requirementCount > 0 && (
                                                                    <span className={`ml-1.5 font-normal ${t.textFaint}`}>
                                                                        ({section.requirementCount} {section.requirementCount === 1 ? 'requirement' : 'requirements'})
                                                                    </span>
                                                                )}
                                                            </span>
                                                            <div className={`flex-1 h-px ${t.border} border-t`} />
                                                        </div>
                                                    )}
                                                    <div className={`space-y-px ${t.requirementDivider} border ${t.border}`}>
                                                        {section.categories.map(([category, reqs]) => renderCategoryAccordion(category, reqs))}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className={`space-y-px ${t.requirementDivider} border ${t.border}`}>
                                            {filteredFlatCategories.map(([category, reqs]) => renderCategoryAccordion(category, reqs))}
                                        </div>
                                    )}
                                    </>
                                ) : activeTab === 'alerts' ? (
                                    loadingAlerts ? (
                                        <div className="space-y-3">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className={`h-20 ${t.cardBg} border ${t.border} rounded animate-pulse`} />
                                            ))}
                                        </div>
                                    ) : locationAlerts.length === 0 ? (
                                        <div className={`text-center py-24 border border-dashed ${t.border} ${t.emptyBg}`}>
                                            <div className={`w-12 h-12 mx-auto mb-6 rounded-full ${t.cardBg} border ${t.border} flex items-center justify-center`}>
                                                <CheckCircle size={20} className={t.textFaint} />
                                            </div>
                                            <p className={`${t.textFaint} text-[10px] font-mono uppercase tracking-[0.2em]`}>All Systems Nominal</p>
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
                                                    className={`border rounded-lg p-5 transition-all ${getSeverityStyles(alert.severity)} ${
                                                        alert.status === 'unread' ? 'bg-opacity-10 border-opacity-30' : t.alertDismissed
                                                    }`}
                                                >
                                                    <div className="flex items-start justify-between gap-6">
                                                        <div className="flex items-start gap-4 min-w-0">
                                                            <div className="mt-1 flex-shrink-0 opacity-60">
                                                                {getAlertTypeIcon(alert.alert_type)}
                                                            </div>
                                                            <div className="min-w-0">
                                                                <div className="flex items-center gap-3 flex-wrap mb-2">
                                                                    <h4 className={`text-xs font-bold uppercase tracking-widest ${t.textMain}`}>{alert.title}</h4>
                                                                    {alert.alert_type && alert.alert_type !== 'change' && (
                                                                        <span className={`text-[8px] px-1.5 py-0.5 ${t.neutralBadge} rounded-xs uppercase tracking-widest font-bold`}>
                                                                            {alert.alert_type.replace('_', ' ')}
                                                                        </span>
                                                                    )}
                                                                    {confidence && (
                                                                        <span className={`text-[8px] px-1.5 py-0.5 border rounded-xs font-bold uppercase tracking-widest ${confidence.color}`}>
                                                                            {confidence.tag} {confidence.label}
                                                                        </span>
                                                                    )}
                                                                    {(alert.affected_employee_count ?? 0) > 0 && (
                                                                        <span className="text-[8px] px-1.5 py-0.5 bg-violet-500/10 border border-violet-500/20 rounded-xs font-bold uppercase tracking-widest text-violet-400">
                                                                            {alert.affected_employee_count} employee{alert.affected_employee_count !== 1 ? 's' : ''}
                                                                        </span>
                                                                    )}
                                                                    {alert.created_at && (
                                                                        <span className={`text-[9px] ${t.textFaint} font-mono uppercase tracking-tighter`}>
                                                                            {new Date(alert.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <p className={`text-xs ${t.textDim} leading-relaxed font-light`}>{linkifyText(alert.message, t.linkify)}</p>
                                                                
                                                                <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mt-4">
                                                                    {alert.effective_date && (
                                                                        <div className="text-[9px] font-mono text-purple-400 uppercase tracking-widest flex items-center gap-2">
                                                                            <Calendar size={10} className="opacity-50" /> Enforce: {new Date(alert.effective_date).toLocaleDateString()}
                                                                        </div>
                                                                    )}
                                                                    {(alert.source_url || alert.source_name) && (
                                                                        <div className={`text-[9px] ${t.textMuted} uppercase tracking-widest font-bold flex items-center gap-2`}>
                                                                            <span className="opacity-40">Source:</span>
                                                                            {alert.source_url ? (
                                                                                <a href={alert.source_url} target="_blank" rel="noopener noreferrer" className={`${t.textDim} ${t.linkHover} ${t.sourceLinkDecor} underline underline-offset-2 transition-colors`}>
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
                                                                            className={`text-[8px] uppercase tracking-[0.2em] ${t.textFaint} ${t.linkHover} flex items-center gap-2 transition-colors`}
                                                                        >
                                                                            <Eye size={10} />
                                                                            {expandedAlertSources.has(alert.id) ? 'Hide' : 'Resolve'} {alert.verification_sources.length} Evidence Node(s)
                                                                        </button>
                                                                        {expandedAlertSources.has(alert.id) && (
                                                                            <div className={`mt-3 space-y-2 pl-4 border-l ${t.border}`}>
                                                                                {alert.verification_sources.map((src, idx) => (
                                                                                    <div key={idx} className="text-[9px]">
                                                                                        <div className="flex items-center gap-2 mb-1">
                                                                                            <span className={`px-1 py-0.5 rounded-xs uppercase tracking-widest font-bold text-[7px] ${
                                                                                                src.type === 'official' ? `bg-emerald-500/10 ${t.statusOk}` :
                                                                                                src.type === 'news' ? t.badgeBlue :
                                                                                                t.sourceTypeFallback
                                                                                            }`}>
                                                                                                {src.type}
                                                                                            </span>
                                                                                            {src.url ? (
                                                                                                <a href={src.url} target="_blank" rel="noopener noreferrer" className={`${t.textDim} ${t.linkHover} truncate max-w-xs transition-colors`}>
                                                                                                    {src.name || src.url}
                                                                                                </a>
                                                                                            ) : (
                                                                                                <span className={t.textMuted}>{src.name}</span>
                                                                                            )}
                                                                                        </div>
                                                                                        {src.snippet && (
                                                                                            <p className={`${t.textFaint} italic leading-relaxed pl-2 border-l ${t.border}`}>{src.snippet}</p>
                                                                                        )}
                                                                                    </div>
                                                                                ))}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                )}
                                                                {alert.action_required && (
                                                                    <div className={`mt-4 p-3 ${t.alertActionBg} rounded-lg`}>
                                                                        <span className={`text-[8px] font-bold uppercase tracking-[0.3em] ${t.textMuted} block mb-1`}>Mandatory Action</span>
                                                                        <span className={`text-[10px] ${t.textMain} font-bold uppercase tracking-wide`}>{alert.action_required}</span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-1 opacity-40 hover:opacity-100 transition-opacity">
                                                            {alert.status === 'unread' && (
                                                                <button
                                                                    onClick={() => markAlertReadMutation.mutate(alert.id)}
                                                                    className={`p-2 ${t.alertBtnHover} rounded-full transition-colors ${t.textDim} hover:text-emerald-500`}
                                                                    title="Acknowledge"
                                                                >
                                                                    <CheckCircle size={14} />
                                                                </button>
                                                            )}
                                                            {alert.status !== 'dismissed' && (
                                                                <button
                                                                    onClick={() => dismissAlertMutation.mutate(alert.id)}
                                                                    className={`p-2 ${t.alertBtnHover} rounded-full transition-colors ${t.textDim} hover:text-red-500`}
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
                                ) : null}
                            </div>
                        </ContentCard>
                    ) : (
                        <ContentCard className="p-12 text-center h-full flex flex-col items-center justify-center min-h-[400px]">
                            <div className={`w-16 h-16 mx-auto mb-6 rounded-full ${t.cardBg} border ${t.border} flex items-center justify-center opacity-40`}>
                                <MapPin size={24} className={t.textFaint} />
                            </div>
                            <h3 className={`${t.textMain} font-semibold text-sm mb-2`}>Select a Location</h3>
                            <p className={`${t.textFaint} text-xs max-w-sm`}>
                                Choose a location from the list to view compliance requirements and alerts.
                            </p>
                        </ContentCard>
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
                            className={`${t.modalBg} shadow-2xl p-10 w-full max-w-md relative overflow-hidden`}
                            onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        >
                            <div className={`absolute top-0 left-0 w-full h-0.5 ${t.modalAccent}`} />
                            <div className="flex items-center justify-between mb-10">
                                <div className="space-y-1">
                                    <h2 className={`text-2xl font-bold ${t.pageText} uppercase tracking-tighter`}>
                                        {editingLocation ? 'Edit Endpoint' : 'Register Node'}
                                    </h2>
                                    <p className={`text-[9px] ${t.pageMuted} font-mono uppercase tracking-[0.2em]`}>Location Configuration</p>
                                </div>
                                <button
                                    onClick={() => {
                                        setShowAddModal(false);
                                        setEditingLocation(null);
                                        setFormData(emptyFormData);
                                        setJurisdictionSearch('');
                                        setUseManualEntry(false);
                                    }}
                                    className={`p-2 ${t.closeBtnCls}`}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleSubmitLocation} className="space-y-6">
                                <div>
                                    <label className={`block text-[9px] tracking-[0.2em] uppercase ${t.pageMuted} mb-2 font-bold font-mono`}>
                                        Logical Identifier (optional)
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.name}
                                        onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                        placeholder="e.g. SF HEADQUARTERS"
                                        className={`w-full px-4 py-3 ${t.pageInput} text-sm focus:outline-none transition-all rounded-lg font-mono uppercase tracking-tight`}
                                    />
                                </div>

                                {showJurisdictionPicker ? (
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between">
                                            <label className={`block text-[9px] tracking-[0.2em] uppercase ${t.pageMuted} font-bold font-mono`}>
                                                Jurisdiction Scan
                                            </label>
                                            <button
                                                type="button"
                                                onClick={() => { setUseManualEntry(true); setFormData(prev => ({ ...prev, jurisdictionKey: '' })); }}
                                                className={`text-[8px] ${t.pageFaint} ${t.pageLinkHover} uppercase tracking-widest transition-colors font-bold`}
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
                                                className={`w-full px-4 py-3 ${t.pageInput} text-sm focus:outline-none transition-all rounded-lg font-mono uppercase tracking-widest`}
                                            />
                                        </div>
                                        <div className={`max-h-40 overflow-y-auto border ${t.pageBorder} rounded-lg ${t.dropdownBg} no-scrollbar`}>
                                            {Object.keys(filteredJurisdictions).length === 0 ? (
                                                <div className={`px-4 py-8 text-center ${t.pageFaint} text-[9px] font-mono uppercase tracking-widest`}>
                                                    {jurisdictionSearch ? 'Zero Matches' : 'Initializing Matrix...'}
                                                </div>
                                            ) : (
                                                Object.entries(filteredJurisdictions).map(([state, items]) => {
                                                    const stateLabel = US_STATES.find(s => s.value === state)?.label || state;
                                                    return (
                                                        <div key={state}>
                                                            <div className={`px-4 py-2 ${t.dropdownHeader} text-[8px] ${t.pageFaint} font-bold uppercase tracking-[0.3em] sticky top-0 ${t.modalHeader}`}>
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
                                                                        className={`w-full text-left px-4 py-2.5 text-[11px] transition-all flex items-center justify-between border-b ${t.pageBorder} last:border-0 ${
                                                                            isSelected
                                                                                ? `${t.listItemSelected} font-bold`
                                                                                : `${t.pageMuted} ${t.pageRowHover} ${t.listItemHoverText}`
                                                                        }`}
                                                                    >
                                                                        <span className="uppercase tracking-tight">{j.city}, {j.state}</span>
                                                                        {j.has_local_ordinance && (
                                                                            <span className={`text-[7px] px-1.5 py-0.5 bg-emerald-500/10 ${t.statusOk} border border-emerald-500/20 rounded-xs uppercase tracking-widest font-bold`}>
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
                                            <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-lg">
                                                <div className={`text-[8px] ${t.statusOk} font-bold uppercase tracking-widest mb-1`}>Matrix Resolution</div>
                                                <div className={`text-xs ${t.pageDim} font-mono uppercase tracking-tighter`}>
                                                    {formData.city}, {formData.state}
                                                    {formData.county && <span className={`${t.pageFaint} ml-2 font-light`}>[{formData.county} County]</span>}
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
                                                className={`text-[8px] ${t.pageFaint} ${t.pageLinkHover} uppercase tracking-widest transition-colors font-bold`}
                                            >
                                                Revert to Matrix Search
                                            </button>
                                        )}
                                        <div>
                                            <label className={`block text-[9px] tracking-[0.2em] uppercase ${t.pageMuted} mb-2 font-bold font-mono`}>
                                                Street Address
                                            </label>
                                            <input
                                                type="text"
                                                value={formData.address}
                                                onChange={e => setFormData(prev => ({ ...prev, address: e.target.value }))}
                                                placeholder="PHYSICAL LOCATION"
                                                className={`w-full px-4 py-3 ${t.pageInput} text-sm focus:outline-none transition-all rounded-lg font-mono uppercase tracking-tight`}
                                            />
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className={`block text-[9px] tracking-[0.2em] uppercase ${t.pageMuted} mb-2 font-bold font-mono`}>
                                                    City
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.city}
                                                    onChange={e => setFormData(prev => ({ ...prev, city: e.target.value }))}
                                                    required
                                                    className={`w-full px-4 py-3 ${t.pageInput} text-sm focus:outline-none transition-all rounded-lg font-mono uppercase tracking-tight`}
                                                />
                                            </div>
                                            <div>
                                                <label className={`block text-[9px] tracking-[0.2em] uppercase ${t.pageMuted} mb-2 font-bold font-mono`}>
                                                    State
                                                </label>
                                                <select
                                                    value={formData.state}
                                                    onChange={e => setFormData(prev => ({ ...prev, state: e.target.value }))}
                                                    required
                                                    className={`w-full px-4 py-3 ${t.pageSelect} text-sm focus:outline-none transition-all rounded-lg font-mono uppercase tracking-tight`}
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
                                                <label className={`block text-[9px] tracking-[0.2em] uppercase ${t.pageMuted} mb-2 font-bold font-mono`}>
                                                    County
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.county}
                                                    onChange={e => setFormData(prev => ({ ...prev, county: e.target.value }))}
                                                    className={`w-full px-4 py-3 ${t.pageInput} text-sm focus:outline-none transition-all rounded-lg font-mono uppercase tracking-tight`}
                                                />
                                            </div>
                                            <div>
                                                <label className={`block text-[9px] tracking-[0.2em] uppercase ${t.pageMuted} mb-2 font-bold font-mono`}>
                                                    ZIP Code
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.zipcode}
                                                    onChange={e => setFormData(prev => ({ ...prev, zipcode: e.target.value }))}
                                                    required={!isClient && !isAdmin}
                                                    maxLength={10}
                                                    className={`w-full px-4 py-3 ${t.pageInput} text-sm focus:outline-none transition-all rounded-lg font-mono uppercase tracking-tight`}
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
                                        className={`flex-1 px-6 py-3.5 ${t.cancelBtn} rounded-lg text-[10px] font-bold uppercase tracking-[0.2em] transition-all`}
                                    >
                                        Abort
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={createLocationMutation.isPending || updateLocationMutation.isPending || (showJurisdictionPicker && !formData.jurisdictionKey)}
                                        className={`flex-1 px-6 py-3.5 ${t.pageBtnPrimary} rounded-lg text-[10px] font-bold uppercase tracking-[0.2em] transition-all disabled:opacity-50 shadow-lg`}
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
        </div>
    );
}

export default Compliance;
