import { useState, useMemo, useEffect } from 'react';
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
    ChevronDown, ChevronRight, AlertTriangle, Bell, CheckCircle,
    ExternalLink, Building2, Loader2, Clock, Calendar, Shield,
    History, Eye, Zap, Info
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

function linkifyText(text: string) {
    const splitRegex = /(https?:\/\/[^\s,)]+)/g;
    const parts = text.split(splitRegex);
    if (parts.length === 1) return text;
    return parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
            <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-emerald-300 hover:text-emerald-200 underline break-all">{part}</a>
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

export function Compliance() {
    const { user } = useAuth();
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




    const requirementsByCategory = requirements?.reduce((acc, req) => {
        if (!acc[req.category]) {
            acc[req.category] = [];
        }
        acc[req.category].push(req);
        return acc;
    }, {} as Record<string, ComplianceRequirement[]>) || {};

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
        <div className="max-w-7xl mx-auto space-y-8">
            <div className="flex items-center justify-between border-b border-white/10 pb-8">
                <div className="flex items-center gap-6">
                    <div>
                        <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Compliance</h1>
                        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
                            Monitor labor laws, tax rates, and posting requirements
                        </p>
                    </div>
                    {isAdmin && companies?.companies && companies.companies.length > 0 && (
                        <select
                            value={selectedCompanyId || ''}
                            onChange={e => setSelectedCompanyId(e.target.value)}
                            className="px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-xs font-mono uppercase tracking-wider focus:outline-none focus:border-white/20 transition-colors min-w-[200px]"
                        >
                            {companies.companies.map(c => (
                                <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                        </select>
                    )}
                </div>
                <button
                    onClick={() => {
                        setFormData(emptyFormData);
                        setEditingLocation(null);
                        setJurisdictionSearch('');
                        setShowAddModal(true);
                    }}
                    className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
                >
                    <Plus size={14} />
                    Add Location
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-1 space-y-4">
                    <h2 className="text-xs font-bold text-white uppercase tracking-wider pb-2 border-b border-white/10">
                        Locations
                    </h2>

                    {loadingLocations ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map(i => (
                                <div key={i} className="bg-zinc-900 border border-zinc-800 rounded p-4 animate-pulse h-20" />
                            ))}
                        </div>
                    ) : locations?.length === 0 ? (
                        <div className="bg-zinc-900/50 border border-dashed border-zinc-800 rounded p-8 text-center">
                            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                                <MapPin size={20} className="text-zinc-500" />
                            </div>
                            <h3 className="text-white text-sm font-bold mb-1">No Locations</h3>
                            <p className="text-zinc-500 text-xs mb-4">
                                Add business locations to track compliance.
                            </p>
                            <button
                                onClick={() => setShowAddModal(true)}
                                className="text-white text-xs font-bold hover:text-zinc-300 uppercase tracking-wider underline underline-offset-4"
                            >
                                Add Location
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {locations?.map(location => (
                                <div
                                    key={location.id}
                                    onClick={() => setSelectedLocationId(location.id)}
                                    className={`border rounded p-4 cursor-pointer transition-all group ${
                                        selectedLocationId === location.id
                                            ? 'border-white bg-zinc-900 shadow-sm'
                                            : 'border-zinc-800 bg-zinc-950 hover:border-zinc-700'
                                    }`}
                                >
                                    <div className="flex items-start justify-between">
                                        <div className="min-w-0 flex-1">
                                            <h3 className={`font-bold text-sm truncate uppercase tracking-wide ${
                                                selectedLocationId === location.id ? 'text-white' : 'text-zinc-400'
                                            }`}>
                                                {location.name || `${location.city}, ${location.state}`}
                                            </h3>
                                            <p className="text-zinc-600 text-xs truncate mt-1 font-mono">
                                                {location.address ? `${location.address}, ` : ''}{location.city}, {location.state} {location.zipcode}
                                            </p>
                                            <div className="flex items-center gap-4 mt-3 text-[10px] uppercase tracking-wider">
                                                <span className="text-zinc-500">
                                                    {location.requirements_count} reqs
                                                </span>
                                                {location.unread_alerts_count > 0 && (
                                                    <span className="text-amber-500 flex items-center gap-1 font-bold">
                                                        <Bell size={10} />
                                                        {location.unread_alerts_count} alerts
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
                                                className="p-1.5 text-zinc-500 hover:text-white rounded transition-colors"
                                                title="Edit"
                                            >
                                                <Edit2 size={12} />
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    if (confirm('Delete this location?')) {
                                                        deleteLocationMutation.mutate(location.id);
                                                    }
                                                }}
                                                className="p-1.5 text-zinc-500 hover:text-red-500 rounded transition-colors"
                                                title="Delete"
                                            >
                                                <Trash2 size={12} />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="lg:col-span-2">
                    {selectedLocationId && selectedLocation ? (
                        <div className="bg-zinc-950 border border-white/10 rounded overflow-hidden min-h-[600px] flex flex-col">
                            <div className="p-6 border-b border-white/10 bg-zinc-900/50">
                                <div className="flex items-center justify-between">
                                <div className="flex items-center gap-4">
                                    <div className="w-10 h-10 rounded bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                                        <Building2 size={20} className="text-white" />
                                    </div>
                                    <div>
                                        <h2 className="text-lg font-bold text-white uppercase tracking-tight">
                                            {selectedLocation.name || `${selectedLocation.city}, ${selectedLocation.state}`}
                                        </h2>
                                        <p className="text-xs text-zinc-500 font-mono mt-0.5">
                                            {selectedLocation.city}, {selectedLocation.state} {selectedLocation.zipcode}
                                            {selectedLocation.last_compliance_check && (
                                                <span className="ml-3 text-zinc-600">
                                                    Updated {new Date(selectedLocation.last_compliance_check).toLocaleString('en-US', { timeZone: 'America/Chicago', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })}
                                                </span>
                                            )}
                                        </p>
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
                                    className="text-[10px] uppercase tracking-wider font-bold text-zinc-500 hover:text-white transition-colors flex items-center gap-1.5 border border-zinc-800 px-3 py-1.5 bg-zinc-900 hover:border-zinc-600 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {checkInProgress ? (
                                        <><Loader2 size={12} className="animate-spin" /> Checking...</>
                                    ) : (
                                        <><Bell size={12} /> Check for Updates</>
                                    )}
                                </button>
                                </div>



                            </div>

                            {checkMessages.length > 0 && (
                                <div className="border-b border-white/10 bg-zinc-900/30">
                                    {checkMessages.some(m => m.type === 'result') && (
                                        <div className="flex items-center gap-3 px-6 pt-3 pb-2 border-b border-white/5 text-[10px] uppercase tracking-wider font-bold text-zinc-600">
                                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" /> New</span>
                                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400 inline-block" /> Updated</span>
                                            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-zinc-600 inline-block" /> Same</span>
                                        </div>
                                    )}
                                    <div className="px-6 py-3 space-y-1.5 max-h-40 overflow-y-auto">
                                    {checkMessages.map((msg, i) => (
                                        <div key={i} className="flex items-center gap-2 text-xs font-mono">
                                            {msg.type === 'jurisdiction_info' ? (
                                                <Info size={12} className="text-blue-400 flex-shrink-0" />
                                            ) : msg.type === 'error' ? (
                                                <X size={12} className="text-red-400 flex-shrink-0" />
                                            ) : msg.type === 'completed' ? (
                                                <CheckCircle size={12} className="text-emerald-400 flex-shrink-0" />
                                            ) : msg.type === 'result' ? (
                                                <CheckCircle size={12} className={
                                                    msg.status === 'new' ? 'text-emerald-400 flex-shrink-0' :
                                                    msg.status === 'updated' ? 'text-amber-400 flex-shrink-0' :
                                                    'text-zinc-600 flex-shrink-0'
                                                } />
                                            ) : checkInProgress && i === checkMessages.length - 1 ? (
                                                <Loader2 size={12} className="text-blue-400 animate-spin flex-shrink-0" />
                                            ) : (
                                                <CheckCircle size={12} className="text-zinc-600 flex-shrink-0" />
                                            )}
                                            {msg.type === 'result' && msg.status && (
                                                <span className={`text-[10px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded ${
                                                    msg.status === 'new' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                                                    msg.status === 'updated' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                                                    'bg-zinc-800 text-zinc-500 border border-zinc-700'
                                                }`}>
                                                    {msg.status === 'unchanged' ? 'same' : msg.status}
                                                </span>
                                            )}
                                            <span className={
                                                msg.type === 'jurisdiction_info' ? 'text-blue-300' :
                                                msg.type === 'error' ? 'text-red-400' :
                                                msg.type === 'completed' ? 'text-emerald-400' :
                                                msg.type === 'result' && msg.status === 'new' ? 'text-emerald-300' :
                                                msg.type === 'result' && msg.status === 'updated' ? 'text-amber-300' :
                                                i === checkMessages.length - 1 && checkInProgress ? 'text-zinc-300' :
                                                'text-zinc-600'
                                            }>
                                                {msg.type === 'completed'
                                                    ? `Done — ${msg.new} new, ${msg.updated} updated, ${msg.alerts} alerts`
                                                    : msg.message || msg.location || msg.type}
                                            </span>
                                        </div>
                                    ))}
                                    </div>
                                </div>
                            )}

                            <div className="flex border-b border-white/10">
                                <button
                                    onClick={() => setActiveTab('requirements')}
                                    className={`flex-1 px-4 py-3 text-xs font-bold uppercase tracking-wider transition-colors ${
                                        activeTab === 'requirements'
                                            ? 'text-white border-b-2 border-white bg-zinc-900'
                                            : 'text-zinc-500 hover:text-zinc-300 bg-zinc-950 hover:bg-zinc-900'
                                    }`}
                                >
                                    Requirements ({requirements?.length || 0})
                                </button>
                                <button
                                    onClick={() => setActiveTab('alerts')}
                                    className={`flex-1 px-4 py-3 text-xs font-bold uppercase tracking-wider transition-colors flex items-center justify-center gap-2 ${
                                        activeTab === 'alerts'
                                            ? 'text-white border-b-2 border-white bg-zinc-900'
                                            : 'text-zinc-500 hover:text-zinc-300 bg-zinc-950 hover:bg-zinc-900'
                                    }`}
                                >
                                    Alerts ({locationAlerts.length})
                                    {unreadAlertsCount > 0 && (
                                        <span className="px-1.5 py-0.5 bg-amber-500/20 text-amber-400 text-[10px] rounded-full font-bold border border-amber-500/30">
                                            {unreadAlertsCount}
                                        </span>
                                    )}
                                </button>
                                <button
                                    onClick={() => setActiveTab('upcoming')}
                                    className={`flex-1 px-4 py-3 text-xs font-bold uppercase tracking-wider transition-colors flex items-center justify-center gap-2 ${
                                        activeTab === 'upcoming'
                                            ? 'text-white border-b-2 border-white bg-zinc-900'
                                            : 'text-zinc-500 hover:text-zinc-300 bg-zinc-950 hover:bg-zinc-900'
                                    }`}
                                >
                                    <Calendar size={12} />
                                    Upcoming ({upcomingLegislation?.length || 0})
                                </button>
                                <button
                                    onClick={() => setActiveTab('history')}
                                    className={`flex-1 px-4 py-3 text-xs font-bold uppercase tracking-wider transition-colors flex items-center justify-center gap-2 ${
                                        activeTab === 'history'
                                            ? 'text-white border-b-2 border-white bg-zinc-900'
                                            : 'text-zinc-500 hover:text-zinc-300 bg-zinc-950 hover:bg-zinc-900'
                                    }`}
                                >
                                    <History size={12} />
                                    Log
                                </button>
                                <button
                                    onClick={() => setActiveTab('posters')}
                                    className={`flex-1 px-4 py-3 text-xs font-bold uppercase tracking-wider transition-colors flex items-center justify-center gap-2 ${
                                        activeTab === 'posters'
                                            ? 'text-white border-b-2 border-white bg-zinc-900'
                                            : 'text-zinc-500 hover:text-zinc-300 bg-zinc-950 hover:bg-zinc-900'
                                    }`}
                                >
                                    <Shield size={12} />
                                    Posters
                                </button>
                            </div>

                            {selectedLocation?.has_local_ordinance === false && (
                                <div className="mx-6 mt-4 px-4 py-3 bg-blue-500/10 border border-blue-500/20 rounded-lg flex items-start gap-3">
                                    <Info size={14} className="text-blue-400 mt-0.5 flex-shrink-0" />
                                    <p className="text-xs text-blue-300 leading-relaxed">
                                        <span className="font-semibold">{selectedLocation.city}</span> does not have its own local labor ordinances.
                                        All requirements shown are from {selectedLocation.county ? `${selectedLocation.county} County / ` : ''}{selectedLocation.state} state law.
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
                                                <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-3">Available Posters</h3>
                                                {availablePosters.length === 0 ? (
                                                    <p className="text-zinc-500 text-sm">No poster templates available for your locations yet.</p>
                                                ) : (
                                                    <div className="space-y-2">
                                                        {availablePosters.map(poster => (
                                                            <div key={poster.location_id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 flex items-center justify-between">
                                                                <div>
                                                                    <div className="text-sm font-medium text-white">
                                                                        {poster.location_city}, {poster.location_state}
                                                                        {poster.location_name && <span className="text-zinc-500 ml-1">({poster.location_name})</span>}
                                                                    </div>
                                                                    {poster.template_title && (
                                                                        <div className="text-xs text-zinc-400 mt-1">
                                                                            {poster.template_title}
                                                                            {poster.template_version && <span className="text-zinc-600 ml-1">v{poster.template_version}</span>}
                                                                            {poster.categories_included && (
                                                                                <span className="text-zinc-600 ml-2">
                                                                                    ({poster.categories_included.join(', ')})
                                                                                </span>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                <div className="flex items-center gap-2">
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
                                                                                className="px-3 py-1.5 text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded transition-colors"
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
                                                                                    className="px-3 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white rounded transition-colors disabled:opacity-50"
                                                                                >
                                                                                    {posterOrderLoading === poster.location_id ? 'Ordering...' : 'Order Poster'}
                                                                                </button>
                                                                            )}
                                                                            {poster.has_active_order && (
                                                                                <span className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider bg-blue-500/20 text-blue-400 rounded-full border border-blue-500/30">
                                                                                    Order Active
                                                                                </span>
                                                                            )}
                                                                        </>
                                                                    )}
                                                                    {poster.template_status === 'pending' && (
                                                                        <span className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider bg-amber-500/20 text-amber-400 rounded-full border border-amber-500/30">
                                                                            Pending
                                                                        </span>
                                                                    )}
                                                                    {!poster.template_id && (
                                                                        <span className="text-xs text-zinc-600">No poster available</span>
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
                                                    <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-3">Order History</h3>
                                                    <div className="space-y-2">
                                                        {posterOrders.map(order => (
                                                            <div key={order.id} className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
                                                                <div className="flex items-center justify-between">
                                                                    <div>
                                                                        <div className="text-sm text-white">
                                                                            {order.location_city}, {order.location_state}
                                                                            {order.location_name && <span className="text-zinc-500 ml-1">({order.location_name})</span>}
                                                                        </div>
                                                                        <div className="text-xs text-zinc-500 mt-1">
                                                                            {order.items.map(i => i.template_title || i.jurisdiction_name).join(', ')}
                                                                            {' \u00b7 '}{order.created_at ? new Date(order.created_at).toLocaleDateString() : ''}
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex items-center gap-2">
                                                                        <span className={`px-2 py-1 text-[10px] font-bold uppercase tracking-wider rounded-full border ${
                                                                            order.status === 'delivered' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
                                                                            order.status === 'shipped' ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' :
                                                                            order.status === 'cancelled' ? 'bg-zinc-700 text-zinc-400 border-zinc-600' :
                                                                            'bg-blue-500/20 text-blue-400 border-blue-500/30'
                                                                        }`}>
                                                                            {order.status}
                                                                        </span>
                                                                        {order.tracking_number && (
                                                                            <span className="text-xs text-zinc-500">#{order.tracking_number}</span>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                                {order.quote_amount != null && (
                                                                    <div className="text-xs text-zinc-500 mt-2">Quote: ${order.quote_amount.toFixed(2)}</div>
                                                                )}
                                                                {order.admin_notes && (
                                                                    <div className="text-xs text-zinc-500 mt-1 italic">Note: {order.admin_notes}</div>
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
                                        <div className="text-center py-12">
                                            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                                                <Calendar size={20} className="text-zinc-500" />
                                            </div>
                                            <p className="text-zinc-500 text-sm font-mono uppercase tracking-wider">No upcoming legislation detected.</p>
                                            <p className="text-zinc-600 text-xs mt-2">Run a compliance check to scan for upcoming changes.</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {upcomingLegislation.map(leg => {
                                                const statusColors: Record<string, string> = {
                                                    proposed: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
                                                    passed: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
                                                    signed: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
                                                    effective_soon: 'bg-red-500/20 text-red-400 border-red-500/30',
                                                };
                                                return (
                                                    <div key={leg.id} className="border border-white/10 rounded-lg p-4 bg-zinc-900/50">
                                                        <div className="flex items-start justify-between">
                                                            <div className="flex-1">
                                                                <div className="flex items-center gap-2 flex-wrap mb-1">
                                                                    <h4 className="text-sm font-bold text-white uppercase tracking-wide">{leg.title}</h4>
                                                                    <span className={`text-[10px] px-1.5 py-0.5 border rounded font-bold uppercase tracking-wider ${statusColors[leg.current_status] || 'bg-zinc-700 text-zinc-400 border-zinc-600'}`}>
                                                                        {leg.current_status.replace('_', ' ')}
                                                                    </span>
                                                                    {leg.category && (
                                                                        <span className="text-[10px] px-1.5 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700 rounded">
                                                                            {COMPLIANCE_CATEGORY_LABELS[leg.category] || leg.category}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                {leg.description && (
                                                                    <p className="text-xs text-zinc-400 leading-relaxed mb-2">{leg.description}</p>
                                                                )}
                                                                {leg.impact_summary && (
                                                                    <p className="text-xs text-amber-300/80 leading-relaxed mb-2">
                                                                        <span className="font-bold uppercase tracking-wider text-[10px]">Impact:</span> {leg.impact_summary}
                                                                    </p>
                                                                )}
                                                                <div className="flex items-center gap-4 text-[10px] text-zinc-500">
                                                                    {leg.expected_effective_date && (
                                                                        <span className="flex items-center gap-1 font-mono">
                                                                            <Calendar size={10} />
                                                                            {new Date(leg.expected_effective_date).toLocaleDateString()}
                                                                            {leg.days_until_effective !== null && (
                                                                                <span className={`ml-1 font-bold ${
                                                                                    leg.days_until_effective <= 30 ? 'text-red-400' :
                                                                                    leg.days_until_effective <= 90 ? 'text-amber-400' :
                                                                                    'text-zinc-400'
                                                                                }`}>
                                                                                    ({leg.days_until_effective <= 0 ? 'NOW' : `${leg.days_until_effective}d`})
                                                                                </span>
                                                                            )}
                                                                        </span>
                                                                    )}
                                                                    {leg.confidence !== null && (
                                                                        <span>Confidence: {Math.round(leg.confidence * 100)}%</span>
                                                                    )}
                                                                    {leg.source_url && (
                                                                        <a href={leg.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 flex items-center gap-1">
                                                                            Source <ExternalLink size={10} />
                                                                        </a>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            {leg.days_until_effective !== null && leg.days_until_effective <= 90 && (
                                                                <div className={`text-right ml-4 ${
                                                                    leg.days_until_effective <= 0 ? 'text-red-400' :
                                                                    leg.days_until_effective <= 30 ? 'text-red-400' :
                                                                    'text-amber-400'
                                                                }`}>
                                                                    <div className="text-2xl font-bold font-mono">
                                                                        {leg.days_until_effective <= 0 ? 'NOW' : leg.days_until_effective}
                                                                    </div>
                                                                    {leg.days_until_effective > 0 && (
                                                                        <div className="text-[10px] uppercase tracking-wider">days</div>
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
                                        <div className="text-center py-12">
                                            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                                                <History size={20} className="text-zinc-500" />
                                            </div>
                                            <p className="text-zinc-500 text-sm font-mono uppercase tracking-wider">No check history yet.</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-2">
                                            {checkLog.map(entry => (
                                                <div key={entry.id} className="flex items-center gap-4 p-3 border border-white/5 rounded bg-zinc-900/30">
                                                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                                                        entry.status === 'completed' ? 'bg-emerald-400' :
                                                        entry.status === 'failed' ? 'bg-red-400' :
                                                        'bg-amber-400 animate-pulse'
                                                    }`} />
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold uppercase tracking-wider ${
                                                                entry.check_type === 'scheduled' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
                                                                entry.check_type === 'proactive' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' :
                                                                'bg-zinc-800 text-zinc-400 border-zinc-700'
                                                            }`}>
                                                                {entry.check_type}
                                                            </span>
                                                            <span className="text-xs text-zinc-400 font-mono">
                                                                {new Date(entry.started_at).toLocaleString(undefined, {
                                                                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                                                                })}
                                                            </span>
                                                        </div>
                                                        {entry.status === 'completed' && (
                                                            <p className="text-[10px] text-zinc-500 mt-1 font-mono">
                                                                {entry.new_count} new, {entry.updated_count} updated, {entry.alert_count} alerts
                                                            </p>
                                                        )}
                                                        {entry.error_message && (
                                                            <p className="text-[10px] text-red-400 mt-1 truncate">{entry.error_message}</p>
                                                        )}
                                                    </div>
                                                    <span className={`text-[10px] uppercase tracking-wider font-bold ${
                                                        entry.status === 'completed' ? 'text-emerald-400' :
                                                        entry.status === 'failed' ? 'text-red-400' :
                                                        'text-amber-400'
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
                                    ) : Object.keys(requirementsByCategory).length === 0 ? (
                                        <div className="text-center py-12 text-zinc-500 text-sm font-mono uppercase tracking-wider">
                                            No requirements found for this jurisdiction.
                                        </div>
                                    ) : (
                                        <div className="space-y-px bg-white/10 border border-white/10">
                                            {Object.entries(requirementsByCategory).map(([category, reqs]) => (
                                                <div key={category} className="bg-zinc-950">
                                                    <button
                                                        onClick={() => toggleCategory(category)}
                                                        className="w-full flex items-center justify-between p-4 bg-zinc-900 hover:bg-zinc-800 transition-colors"
                                                    >
                                                        <div className="flex items-center gap-3">
                                                            <span className="text-white text-sm font-bold uppercase tracking-wider">
                                                                {COMPLIANCE_CATEGORY_LABELS[category] || category}
                                                            </span>
                                                            <span className="px-2 py-0.5 bg-zinc-800 border border-zinc-700 text-zinc-400 text-[10px] rounded-full font-mono">
                                                                {reqs.length}
                                                            </span>
                                                            {(() => {
                                                                const source = getCategoryJurisdiction(reqs);
                                                                return (
                                                                    <span className={`px-1.5 py-0.5 text-[10px] rounded border font-bold uppercase tracking-wider ${
                                                                        source.type === 'local'
                                                                            ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                                                                            : 'bg-blue-500/15 text-blue-400 border-blue-500/30'
                                                                    }`}>
                                                                        {source.label}
                                                                    </span>
                                                                );
                                                            })()}
                                                        </div>
                                                        {expandedCategories.has(category) ? (
                                                            <ChevronDown size={16} className="text-zinc-500" />
                                                        ) : (
                                                            <ChevronRight size={16} className="text-zinc-500" />
                                                        )}
                                                    </button>

                                                    <AnimatePresence initial={false}>
                                                        {expandedCategories.has(category) && (
                                                            <motion.div
                                                                initial={{ height: 0, opacity: 0 }}
                                                                animate={{ height: 'auto', opacity: 1 }}
                                                                exit={{ height: 0, opacity: 0 }}
                                                                transition={{ duration: 0.2 }}
                                                                className="overflow-hidden bg-zinc-950 border-t border-white/5"
                                                            >
                                                                <div className="divide-y divide-white/5">
                                                                    {reqs.map(req => (
                                                                        <div key={req.id} className="p-6 hover:bg-white/5 transition-colors">
                                                                            <div className="flex items-start justify-between mb-3">
                                                                                <div>
                                                                                    <h4 className="text-white text-sm font-bold mb-1">
                                                                                        {req.title}
                                                                                    </h4>
                                                                                    <div className="flex items-center gap-2">
                                                                                        <span className="px-1.5 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700 text-[10px] uppercase tracking-wide rounded">
                                                                                            {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                                                                                        </span>
                                                                                        <span className="text-zinc-500 text-xs font-mono">
                                                                                            {req.jurisdiction_name}
                                                                                        </span>
                                                                                    </div>
                                                                                </div>
                                                                                {req.current_value && (
                                                                                    <span className="text-emerald-400 font-mono text-sm bg-emerald-900/20 border border-emerald-900/50 px-2 py-1 rounded">
                                                                                        {req.current_value}
                                                                                    </span>
                                                                                )}
                                                                            </div>
                                                                            {req.description && (
                                                                                <p className="text-zinc-400 text-xs leading-relaxed mb-4 max-w-2xl">
                                                                                    {req.description}
                                                                                </p>
                                                                            )}
                                                                            <div className="flex items-center justify-between text-[10px] text-zinc-500 uppercase tracking-widest">
                                                                                <div className="flex items-center gap-3">
                                                                                    {req.effective_date && (
                                                                                        <span>
                                                                                            Effective: {new Date(req.effective_date).toLocaleDateString()}
                                                                                        </span>
                                                                                    )}
                                                                                </div>
                                                                                {req.source_url && (
                                                                                    <a
                                                                                        href={req.source_url}
                                                                                        target="_blank"
                                                                                        rel="noopener noreferrer"
                                                                                        className="text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
                                                                                    >
                                                                                        Source <ExternalLink size={10} />
                                                                                    </a>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            </motion.div>
                                                        )}
                                                    </AnimatePresence>
                                                </div>
                                            ))}
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
                                        <div className="text-center py-12">
                                            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-emerald-900/20 border border-emerald-900/50 flex items-center justify-center">
                                                <CheckCircle size={20} className="text-emerald-500" />
                                            </div>
                                            <p className="text-zinc-500 text-sm font-mono uppercase tracking-wider">All systems nominal.</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {locationAlerts.map(alert => {
                                                const confidence = getConfidenceBadge(alert.confidence_score);
                                                return (
                                                <div
                                                    key={alert.id}
                                                    className={`border rounded-lg p-4 ${getSeverityStyles(alert.severity)} ${
                                                        alert.status === 'unread' ? 'bg-opacity-10' : 'opacity-60 bg-zinc-900 border-zinc-800'
                                                    }`}
                                                >
                                                    <div className="flex items-start justify-between">
                                                        <div className="flex items-start gap-3">
                                                            <span className="mt-0.5 flex-shrink-0">
                                                                {getAlertTypeIcon(alert.alert_type)}
                                                            </span>
                                                            <div>
                                                                <div className="flex items-center gap-2 flex-wrap">
                                                                    <h4 className="text-sm font-bold uppercase tracking-wide">{alert.title}</h4>
                                                                    {alert.alert_type && alert.alert_type !== 'change' && (
                                                                        <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded uppercase tracking-wider font-bold">
                                                                            {alert.alert_type.replace('_', ' ')}
                                                                        </span>
                                                                    )}
                                                                    {confidence && (
                                                                        <span className={`text-[10px] px-1.5 py-0.5 border rounded font-bold uppercase tracking-wider ${confidence.color}`}>
                                                                            <Shield size={8} className="inline mr-0.5" />
                                                                            {confidence.tag} {confidence.label}
                                                                        </span>
                                                                    )}
                                                                    {alert.created_at && (
                                                                        <span className="text-[10px] text-zinc-400 font-mono whitespace-nowrap">
                                                                            {new Date(alert.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                                <p className="text-xs mt-1 opacity-90 leading-relaxed">{linkifyText(alert.message)}</p>
                                                                {alert.effective_date && (
                                                                    <p className="text-[10px] mt-1.5 font-mono text-purple-300 flex items-center gap-1">
                                                                        <Calendar size={10} /> Effective: {new Date(alert.effective_date).toLocaleDateString()}
                                                                    </p>
                                                                )}
                                                                {(alert.source_url || alert.source_name) && (
                                                                    <p className="text-[10px] mt-2 text-zinc-400">
                                                                        <span className="uppercase tracking-wider">Source:</span>{' '}
                                                                        {alert.source_url ? (
                                                                            <a
                                                                                href={alert.source_url}
                                                                                target="_blank"
                                                                                rel="noopener noreferrer"
                                                                                className="text-emerald-300 hover:text-emerald-200 underline"
                                                                            >
                                                                                {alert.source_name || 'View source'}
                                                                            </a>
                                                                        ) : (
                                                                            <span>{alert.source_name}</span>
                                                                        )}
                                                                    </p>
                                                                )}
                                                                {alert.verification_sources && alert.verification_sources.length > 0 && (
                                                                    <div className="mt-2">
                                                                        <button
                                                                            onClick={() => toggleAlertSources(alert.id)}
                                                                            className="text-[10px] uppercase tracking-wider text-zinc-400 hover:text-zinc-200 flex items-center gap-1 transition-colors"
                                                                        >
                                                                            <Eye size={10} />
                                                                            {expandedAlertSources.has(alert.id) ? 'Hide' : 'Show'} {alert.verification_sources.length} verification source(s)
                                                                        </button>
                                                                        {expandedAlertSources.has(alert.id) && (
                                                                            <div className="mt-1.5 space-y-1 pl-3 border-l border-white/10">
                                                                                {alert.verification_sources.map((src, idx) => (
                                                                                    <div key={idx} className="text-[10px]">
                                                                                        <span className={`px-1 py-0.5 rounded mr-1.5 uppercase tracking-wider font-bold ${
                                                                                            src.type === 'official' ? 'bg-emerald-500/20 text-emerald-400' :
                                                                                            src.type === 'news' ? 'bg-blue-500/20 text-blue-400' :
                                                                                            'bg-zinc-700 text-zinc-400'
                                                                                        }`}>
                                                                                            {src.type}
                                                                                        </span>
                                                                                        {src.url ? (
                                                                                            <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-emerald-300 hover:text-emerald-200 underline">
                                                                                                {src.name || src.url}
                                                                                            </a>
                                                                                        ) : (
                                                                                            <span className="text-zinc-400">{src.name}</span>
                                                                                        )}
                                                                                        {src.snippet && (
                                                                                            <p className="text-zinc-500 mt-0.5 italic">{src.snippet}</p>
                                                                                        )}
                                                                                    </div>
                                                                                ))}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                )}
                                                                {alert.action_required && (
                                                                    <p className="text-xs mt-2 font-bold uppercase tracking-wider bg-black/20 inline-block px-2 py-1 rounded">
                                                                        Action: {alert.action_required}
                                                                    </p>
                                                                )}
                                                                {alert.deadline && (
                                                                    <p className="text-[10px] mt-2 font-mono opacity-70">
                                                                        Deadline: {new Date(alert.deadline).toLocaleDateString()}
                                                                    </p>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            {alert.status === 'unread' && (
                                                                <button
                                                                    onClick={() => markAlertReadMutation.mutate(alert.id)}
                                                                    className="p-1.5 hover:bg-black/20 rounded transition-colors"
                                                                    title="Mark as read"
                                                                >
                                                                    <CheckCircle size={14} />
                                                                </button>
                                                            )}
                                                            {alert.status !== 'dismissed' && (
                                                                <button
                                                                    onClick={() => dismissAlertMutation.mutate(alert.id)}
                                                                    className="p-1.5 hover:bg-black/20 rounded transition-colors"
                                                                    title="Dismiss"
                                                                >
                                                                    <X size={14} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                                );
                                            })}
                                        </div>
                                    )
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="bg-zinc-900/30 border border-zinc-800 rounded p-12 text-center h-full flex flex-col items-center justify-center min-h-[400px]">
                            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                                <MapPin size={24} className="text-zinc-600" />
                            </div>
                            <h3 className="text-white font-bold uppercase tracking-wider mb-2">Select a Location</h3>
                            <p className="text-zinc-500 text-xs max-w-sm font-mono">
                                Choose a location from the left to view compliance requirements and alerts.
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
                        className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                        onClick={() => {
                            setShowAddModal(false);
                            setEditingLocation(null);
                            setFormData(emptyFormData);
                            setJurisdictionSearch('');
                            setUseManualEntry(false);
                        }}
                    >
                        <motion.div
                            initial={{ scale: 0.95, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.95, opacity: 0 }}
                            className="bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm p-8 w-full max-w-md"
                            onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        >
                            <div className="flex items-center justify-between mb-6 border-b border-white/10 pb-4">
                                <h2 className="text-xl font-bold text-white uppercase tracking-tight">
                                    {editingLocation ? 'Edit Location' : 'Add Location'}
                                </h2>
                                <button
                                    onClick={() => {
                                        setShowAddModal(false);
                                        setEditingLocation(null);
                                        setFormData(emptyFormData);
                                        setJurisdictionSearch('');
                                        setUseManualEntry(false);
                                    }}
                                    className="p-1 text-zinc-500 hover:text-white transition-colors"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleSubmitLocation} className="space-y-4">
                                <div>
                                    <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                                        Location Name (optional)
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.name}
                                        onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                        placeholder="e.g., Main Office, Warehouse"
                                        className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                                    />
                                </div>

                                {showJurisdictionPicker ? (
                                    <div>
                                        <div className="flex items-center justify-between mb-1.5">
                                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500">
                                                Jurisdiction <span className="text-red-500">*</span>
                                            </label>
                                            <button
                                                type="button"
                                                onClick={() => { setUseManualEntry(true); setFormData(prev => ({ ...prev, jurisdictionKey: '' })); }}
                                                className="text-[10px] text-zinc-600 hover:text-zinc-400 uppercase tracking-wider transition-colors"
                                            >
                                                Enter manually
                                            </button>
                                        </div>
                                        <input
                                            type="text"
                                            value={jurisdictionSearch}
                                            onChange={e => setJurisdictionSearch(e.target.value)}
                                            placeholder="Search by city or state..."
                                            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700 mb-2"
                                        />
                                        <div className="max-h-48 overflow-y-auto border border-zinc-800 rounded bg-zinc-900">
                                            {Object.keys(filteredJurisdictions).length === 0 ? (
                                                <div className="px-3 py-4 text-center text-zinc-600 text-xs">
                                                    {jurisdictionSearch ? 'No matching jurisdictions' : 'Loading jurisdictions...'}
                                                </div>
                                            ) : (
                                                Object.entries(filteredJurisdictions).map(([state, items]) => {
                                                    const stateLabel = US_STATES.find(s => s.value === state)?.label || state;
                                                    return (
                                                        <div key={state}>
                                                            <div className="px-3 py-1.5 bg-zinc-950 text-[10px] text-zinc-500 font-bold uppercase tracking-wider sticky top-0">
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
                                                                        className={`w-full text-left px-3 py-2 text-sm transition-colors flex items-center justify-between ${
                                                                            isSelected
                                                                                ? 'bg-white/10 text-white'
                                                                                : 'text-zinc-400 hover:bg-white/5 hover:text-white'
                                                                        }`}
                                                                    >
                                                                        <span>{j.city}, {j.state}</span>
                                                                        {j.has_local_ordinance && (
                                                                            <span className="text-[9px] px-1.5 py-0.5 bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 rounded uppercase tracking-wider font-bold">
                                                                                Local
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
                                            <div className="mt-2 px-3 py-2 bg-zinc-800/50 border border-zinc-700 rounded text-xs text-zinc-300">
                                                Selected: <span className="text-white font-bold">{formData.city}, {formData.state}</span>
                                                {formData.county && <span className="text-zinc-500 ml-1">({formData.county} County)</span>}
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <>
                                        {(isClient || isAdmin) && !editingLocation && useManualEntry && (
                                            <button
                                                type="button"
                                                onClick={() => { setUseManualEntry(false); setFormData(emptyFormData); }}
                                                className="text-[10px] text-zinc-600 hover:text-zinc-400 uppercase tracking-wider transition-colors"
                                            >
                                                Use jurisdiction picker
                                            </button>
                                        )}
                                        <div>
                                            <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                                                Street Address (optional)
                                            </label>
                                            <input
                                                type="text"
                                                value={formData.address}
                                                onChange={e => setFormData(prev => ({ ...prev, address: e.target.value }))}
                                                placeholder="123 Main St"
                                                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                                            />
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                                                    City <span className="text-red-500">*</span>
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.city}
                                                    onChange={e => setFormData(prev => ({ ...prev, city: e.target.value }))}
                                                    required
                                                    placeholder="San Francisco"
                                                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                                                    State <span className="text-red-500">*</span>
                                                </label>
                                                <select
                                                    value={formData.state}
                                                    onChange={e => setFormData(prev => ({ ...prev, state: e.target.value }))}
                                                    required
                                                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors"
                                                >
                                                    <option value="">Select...</option>
                                                    {US_STATES.map(state => (
                                                        <option key={state.value} value={state.value}>
                                                            {state.label}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                                                    County (optional)
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.county}
                                                    onChange={e => setFormData(prev => ({ ...prev, county: e.target.value }))}
                                                    placeholder="San Francisco"
                                                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">
                                                    ZIP Code {!isClient && !isAdmin && <span className="text-red-500">*</span>}
                                                </label>
                                                <input
                                                    type="text"
                                                    value={formData.zipcode}
                                                    onChange={e => setFormData(prev => ({ ...prev, zipcode: e.target.value }))}
                                                    required={!isClient && !isAdmin}
                                                    placeholder="94105"
                                                    maxLength={10}
                                                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                                                />
                                            </div>
                                        </div>
                                    </>
                                )}

                                <div className="flex gap-3 pt-6 border-t border-white/10">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowAddModal(false);
                                            setEditingLocation(null);
                                            setFormData(emptyFormData);
                                            setJurisdictionSearch('');
                                            setUseManualEntry(false);
                                        }}
                                        className="flex-1 px-4 py-2 bg-transparent border border-zinc-700 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded text-xs font-bold uppercase tracking-wider transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={createLocationMutation.isPending || updateLocationMutation.isPending || (showJurisdictionPicker && !formData.jurisdictionKey)}
                                        className="flex-1 px-4 py-2 bg-white hover:bg-zinc-200 text-black rounded text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50"
                                    >
                                        {createLocationMutation.isPending || updateLocationMutation.isPending
                                            ? 'Saving...'
                                            : editingLocation
                                                ? 'Update Location'
                                                : 'Add Location'}
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
