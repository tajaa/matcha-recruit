import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { BusinessLocation, ComplianceRequirement, LocationCreate } from '../api/compliance';
import {
    complianceAPI,
    COMPLIANCE_CATEGORY_LABELS,
    JURISDICTION_LEVEL_LABELS
} from '../api/compliance';
import {
    MapPin, Plus, Trash2, Edit2, X,
    ChevronDown, ChevronRight, AlertTriangle, Bell, CheckCircle,
    ExternalLink, Building2, Loader2
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

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
}

const emptyFormData: LocationFormData = {
    name: '',
    address: '',
    city: '',
    state: '',
    county: '',
    zipcode: ''
};

export function Compliance() {
    const queryClient = useQueryClient();
    const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
    const [showAddModal, setShowAddModal] = useState(false);
    const [editingLocation, setEditingLocation] = useState<BusinessLocation | null>(null);
    const [formData, setFormData] = useState<LocationFormData>(emptyFormData);
    const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
    const [activeTab, setActiveTab] = useState<'requirements' | 'alerts'>('requirements');
    const [checkInProgress, setCheckInProgress] = useState(false);
    const [checkMessages, setCheckMessages] = useState<{ type: string; message?: string; location?: string; new?: number; updated?: number; alerts?: number }[]>([]);

    const { data: locations, isLoading: loadingLocations } = useQuery({
        queryKey: ['compliance-locations'],
        queryFn: complianceAPI.getLocations
    });

    const { data: requirements, isLoading: loadingRequirements } = useQuery({
        queryKey: ['compliance-requirements', selectedLocationId],
        queryFn: () => selectedLocationId ? complianceAPI.getRequirements(selectedLocationId) : Promise.resolve([]),
        enabled: !!selectedLocationId
    });

    const { data: alerts, isLoading: loadingAlerts } = useQuery({
        queryKey: ['compliance-alerts'],
        queryFn: () => complianceAPI.getAlerts()
    });

    const createLocationMutation = useMutation({
        mutationFn: (data: LocationCreate) => complianceAPI.createLocation(data),
        onSuccess: (newLocation) => {
            queryClient.invalidateQueries({ queryKey: ['compliance-locations'] });
            queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
            setShowAddModal(false);
            setFormData(emptyFormData);
            setSelectedLocationId(newLocation.id);
        }
    });

    const updateLocationMutation = useMutation({
        mutationFn: ({ id, data }: { id: string; data: LocationCreate }) => complianceAPI.updateLocation(id, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-locations'] });
            setEditingLocation(null);
            setFormData(emptyFormData);
        }
    });

    const deleteLocationMutation = useMutation({
        mutationFn: (id: string) => complianceAPI.deleteLocation(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-locations'] });
            queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
            if (selectedLocationId === deleteLocationMutation.variables) {
                setSelectedLocationId(null);
            }
        }
    });

    const markAlertReadMutation = useMutation({
        mutationFn: (id: string) => complianceAPI.markAlertRead(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-alerts'] });
            queryClient.invalidateQueries({ queryKey: ['compliance-summary'] });
        }
    });

    const dismissAlertMutation = useMutation({
        mutationFn: (id: string) => complianceAPI.dismissAlert(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['compliance-alerts'] });
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
        if (!formData.city || !formData.state || !formData.zipcode) return;

        const data: LocationCreate = {
            name: formData.name || undefined,
            address: formData.address || undefined,
            city: formData.city,
            state: formData.state,
            county: formData.county || undefined,
            zipcode: formData.zipcode
        };

        if (editingLocation) {
            updateLocationMutation.mutate({ id: editingLocation.id, data });
        } else {
            createLocationMutation.mutate(data);
        }
    };

    const openEditModal = (location: BusinessLocation) => {
        setEditingLocation(location);
        setFormData({
            name: location.name || '',
            address: location.address || '',
            city: location.city,
            state: location.state,
            county: location.county || '',
            zipcode: location.zipcode
        });
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

    const selectedLocation = locations?.find(l => l.id === selectedLocationId);
    const locationAlerts = alerts?.filter(a => a.location_id === selectedLocationId && a.status !== 'dismissed') || [];
    const unreadAlertsCount = locationAlerts.filter(a => a.status === 'unread').length;

    return (
        <div className="max-w-7xl mx-auto space-y-8">
            <div className="flex items-center justify-between border-b border-white/10 pb-8">
                <div>
                    <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Compliance</h1>
                    <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
                        Monitor labor laws, tax rates, and posting requirements
                    </p>
                </div>
                <button
                    onClick={() => {
                        setFormData(emptyFormData);
                        setEditingLocation(null);
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
                            <div className="p-6 border-b border-white/10 bg-zinc-900/50 flex items-center justify-between">
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
                                            const response = await complianceAPI.checkCompliance(selectedLocationId);
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
                                            queryClient.invalidateQueries({ queryKey: ['compliance-requirements', selectedLocationId] });
                                            queryClient.invalidateQueries({ queryKey: ['compliance-alerts'] });
                                            queryClient.invalidateQueries({ queryKey: ['compliance-locations'] });
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

                            {checkMessages.length > 0 && (
                                <div className="border-b border-white/10 px-6 py-3 bg-zinc-900/30 space-y-1 max-h-40 overflow-y-auto">
                                    {checkMessages.map((msg, i) => (
                                        <div key={i} className="flex items-center gap-2 text-xs font-mono">
                                            {msg.type === 'error' ? (
                                                <X size={12} className="text-red-400 flex-shrink-0" />
                                            ) : msg.type === 'completed' ? (
                                                <CheckCircle size={12} className="text-emerald-400 flex-shrink-0" />
                                            ) : checkInProgress && i === checkMessages.length - 1 ? (
                                                <Loader2 size={12} className="text-blue-400 animate-spin flex-shrink-0" />
                                            ) : (
                                                <CheckCircle size={12} className="text-zinc-600 flex-shrink-0" />
                                            )}
                                            <span className={
                                                msg.type === 'error' ? 'text-red-400' :
                                                msg.type === 'completed' ? 'text-emerald-400' :
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
                            </div>

                            <div className="p-6 flex-1 bg-zinc-950 overflow-y-auto">
                                {activeTab === 'requirements' ? (
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
                                            {locationAlerts.map(alert => (
                                                <div
                                                    key={alert.id}
                                                    className={`border rounded-lg p-4 ${getSeverityStyles(alert.severity)} ${
                                                        alert.status === 'unread' ? 'bg-opacity-10' : 'opacity-60 bg-zinc-900 border-zinc-800'
                                                    }`}
                                                >
                                                    <div className="flex items-start justify-between">
                                                        <div className="flex items-start gap-3">
                                                            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
                                                            <div>
                                                                <h4 className="text-sm font-bold uppercase tracking-wide">{alert.title}</h4>
                                                                <p className="text-xs mt-1 opacity-90 leading-relaxed">{alert.message}</p>
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
                                            ))}
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
                                            ZIP Code <span className="text-red-500">*</span>
                                        </label>
                                        <input
                                            type="text"
                                            value={formData.zipcode}
                                            onChange={e => setFormData(prev => ({ ...prev, zipcode: e.target.value }))}
                                            required
                                            placeholder="94105"
                                            maxLength={10}
                                            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                                        />
                                    </div>
                                </div>

                                <div className="flex gap-3 pt-6 border-t border-white/10">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowAddModal(false);
                                            setEditingLocation(null);
                                            setFormData(emptyFormData);
                                        }}
                                        className="flex-1 px-4 py-2 bg-transparent border border-zinc-700 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded text-xs font-bold uppercase tracking-wider transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={createLocationMutation.isPending || updateLocationMutation.isPending}
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
