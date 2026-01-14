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
    ExternalLink, Building2
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
                return 'bg-red-50 text-red-700 border-red-200';
            case 'warning':
                return 'bg-amber-50 text-amber-700 border-amber-200';
            default:
                return 'bg-blue-50 text-blue-700 border-blue-200';
        }
    };

    const selectedLocation = locations?.find(l => l.id === selectedLocationId);
    const locationAlerts = alerts?.filter(a => a.location_id === selectedLocationId) || [];
    const unreadAlertsCount = locationAlerts.filter(a => a.status === 'unread').length;

    return (
        <div className="max-w-7xl mx-auto space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-light tracking-tight text-zinc-900">Compliance</h1>
                    <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">
                        Monitor labor laws, tax rates, and posting requirements
                    </p>
                </div>
                <button
                    onClick={() => {
                        setFormData(emptyFormData);
                        setEditingLocation(null);
                        setShowAddModal(true);
                    }}
                    className="flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 text-white rounded text-xs font-medium uppercase tracking-wider transition-colors"
                >
                    <Plus size={14} />
                    Add Location
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-1 space-y-4">
                    <h2 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider pb-2 border-b border-zinc-200">
                        Locations
                    </h2>

                    {loadingLocations ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map(i => (
                                <div key={i} className="bg-zinc-100 rounded p-4 animate-pulse h-20" />
                            ))}
                        </div>
                    ) : locations?.length === 0 ? (
                        <div className="bg-zinc-50 border border-zinc-200 rounded p-8 text-center">
                            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-zinc-100 flex items-center justify-center">
                                <MapPin size={20} className="text-zinc-400" />
                            </div>
                            <h3 className="text-zinc-900 text-sm font-medium mb-1">No Locations</h3>
                            <p className="text-zinc-500 text-xs mb-4">
                                Add business locations to track compliance.
                            </p>
                            <button
                                onClick={() => setShowAddModal(true)}
                                className="text-zinc-900 text-xs font-medium hover:underline"
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
                                            ? 'border-zinc-900 bg-zinc-50 shadow-sm'
                                            : 'border-zinc-200 bg-white hover:border-zinc-300'
                                    }`}
                                >
                                    <div className="flex items-start justify-between">
                                        <div className="min-w-0 flex-1">
                                            <h3 className={`font-medium text-sm truncate ${
                                                selectedLocationId === location.id ? 'text-zinc-900' : 'text-zinc-700'
                                            }`}>
                                                {location.name || `${location.city}, ${location.state}`}
                                            </h3>
                                            <p className="text-zinc-500 text-xs truncate mt-0.5">
                                                {location.address ? `${location.address}, ` : ''}{location.city}, {location.state} {location.zipcode}
                                            </p>
                                            <div className="flex items-center gap-4 mt-3 text-[10px] uppercase tracking-wider">
                                                <span className="text-zinc-500">
                                                    {location.requirements_count} reqs
                                                </span>
                                                {location.unread_alerts_count > 0 && (
                                                    <span className="text-amber-600 flex items-center gap-1 font-medium">
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
                                                className="p-1.5 text-zinc-400 hover:text-zinc-900 rounded transition-colors"
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
                                                className="p-1.5 text-zinc-400 hover:text-red-600 rounded transition-colors"
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
                        <div className="bg-white border border-zinc-200 rounded shadow-sm overflow-hidden min-h-[600px] flex flex-col">
                            <div className="p-6 border-b border-zinc-100 bg-zinc-50/50 flex items-center justify-between">
                                <div className="flex items-center gap-4">
                                    <div className="w-10 h-10 rounded bg-white border border-zinc-200 flex items-center justify-center shadow-sm">
                                        <Building2 size={20} className="text-zinc-400" />
                                    </div>
                                    <div>
                                        <h2 className="text-lg font-medium text-zinc-900">
                                            {selectedLocation.name || `${selectedLocation.city}, ${selectedLocation.state}`}
                                        </h2>
                                        <p className="text-xs text-zinc-500">
                                            {selectedLocation.city}, {selectedLocation.state} {selectedLocation.zipcode}
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <div className="flex border-b border-zinc-200">
                                <button
                                    onClick={() => setActiveTab('requirements')}
                                    className={`flex-1 px-4 py-3 text-xs font-medium uppercase tracking-wider transition-colors ${
                                        activeTab === 'requirements'
                                            ? 'text-zinc-900 border-b-2 border-zinc-900 bg-white'
                                            : 'text-zinc-500 hover:text-zinc-900 bg-zinc-50/50 hover:bg-zinc-50'
                                    }`}
                                >
                                    Requirements ({requirements?.length || 0})
                                </button>
                                <button
                                    onClick={() => setActiveTab('alerts')}
                                    className={`flex-1 px-4 py-3 text-xs font-medium uppercase tracking-wider transition-colors flex items-center justify-center gap-2 ${
                                        activeTab === 'alerts'
                                            ? 'text-zinc-900 border-b-2 border-zinc-900 bg-white'
                                            : 'text-zinc-500 hover:text-zinc-900 bg-zinc-50/50 hover:bg-zinc-50'
                                    }`}
                                >
                                    Alerts ({locationAlerts.length})
                                    {unreadAlertsCount > 0 && (
                                        <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[10px] rounded-full font-bold">
                                            {unreadAlertsCount}
                                        </span>
                                    )}
                                </button>
                            </div>

                            <div className="p-6 flex-1 bg-white overflow-y-auto">
                                {activeTab === 'requirements' ? (
                                    loadingRequirements ? (
                                        <div className="space-y-4">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className="h-16 bg-zinc-100 rounded animate-pulse" />
                                            ))}
                                        </div>
                                    ) : Object.keys(requirementsByCategory).length === 0 ? (
                                        <div className="text-center py-12 text-zinc-500 text-sm">
                                            No requirements found for this jurisdiction.
                                        </div>
                                    ) : (
                                        <div className="space-y-4">
                                            {Object.entries(requirementsByCategory).map(([category, reqs]) => (
                                                <div key={category} className="border border-zinc-200 rounded overflow-hidden">
                                                    <button
                                                        onClick={() => toggleCategory(category)}
                                                        className="w-full flex items-center justify-between p-4 bg-zinc-50 hover:bg-zinc-100 transition-colors"
                                                    >
                                                        <div className="flex items-center gap-3">
                                                            <span className="text-zinc-900 text-sm font-medium">
                                                                {COMPLIANCE_CATEGORY_LABELS[category] || category}
                                                            </span>
                                                            <span className="px-2 py-0.5 bg-white border border-zinc-200 text-zinc-500 text-[10px] rounded-full">
                                                                {reqs.length}
                                                            </span>
                                                        </div>
                                                        {expandedCategories.has(category) ? (
                                                            <ChevronDown size={16} className="text-zinc-400" />
                                                        ) : (
                                                            <ChevronRight size={16} className="text-zinc-400" />
                                                        )}
                                                    </button>

                                                    <AnimatePresence initial={false}>
                                                        {expandedCategories.has(category) && (
                                                            <motion.div
                                                                initial={{ height: 0, opacity: 0 }}
                                                                animate={{ height: 'auto', opacity: 1 }}
                                                                exit={{ height: 0, opacity: 0 }}
                                                                transition={{ duration: 0.2 }}
                                                                className="overflow-hidden bg-white border-t border-zinc-200"
                                                            >
                                                                <div className="divide-y divide-zinc-100">
                                                                    {reqs.map(req => (
                                                                        <div key={req.id} className="p-4 hover:bg-zinc-50/50 transition-colors">
                                                                            <div className="flex items-start justify-between mb-2">
                                                                                <div>
                                                                                    <h4 className="text-zinc-900 text-sm font-medium">
                                                                                        {req.title}
                                                                                    </h4>
                                                                                    <div className="flex items-center gap-2 mt-1">
                                                                                        <span className="px-1.5 py-0.5 bg-zinc-100 text-zinc-600 text-[10px] uppercase tracking-wide rounded">
                                                                                            {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                                                                                        </span>
                                                                                        <span className="text-zinc-500 text-xs">
                                                                                            {req.jurisdiction_name}
                                                                                        </span>
                                                                                    </div>
                                                                                </div>
                                                                                {req.current_value && (
                                                                                    <span className="text-zinc-900 font-mono text-sm bg-zinc-100 px-2 py-1 rounded">
                                                                                        {req.current_value}
                                                                                    </span>
                                                                                )}
                                                                            </div>
                                                                            {req.description && (
                                                                                <p className="text-zinc-600 text-xs leading-relaxed mb-3">
                                                                                    {req.description}
                                                                                </p>
                                                                            )}
                                                                            <div className="flex items-center justify-between text-[10px] text-zinc-400">
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
                                                                                        className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
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
                                                <div key={i} className="h-20 bg-zinc-100 rounded animate-pulse" />
                                            ))}
                                        </div>
                                    ) : locationAlerts.length === 0 ? (
                                        <div className="text-center py-12">
                                            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-emerald-50 flex items-center justify-center">
                                                <CheckCircle size={20} className="text-emerald-500" />
                                            </div>
                                            <p className="text-zinc-500 text-sm">All clear. No alerts.</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {locationAlerts.map(alert => (
                                                <div
                                                    key={alert.id}
                                                    className={`border rounded-lg p-4 ${getSeverityStyles(alert.severity)} ${
                                                        alert.status === 'unread' ? 'shadow-sm' : 'opacity-75 bg-zinc-50 border-zinc-200'
                                                    }`}
                                                >
                                                    <div className="flex items-start justify-between">
                                                        <div className="flex items-start gap-3">
                                                            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0 opacity-80" />
                                                            <div>
                                                                <h4 className="text-sm font-medium opacity-90">{alert.title}</h4>
                                                                <p className="text-xs mt-1 opacity-80 leading-relaxed">{alert.message}</p>
                                                                {alert.action_required && (
                                                                    <p className="text-xs mt-2 font-medium">
                                                                        Action: {alert.action_required}
                                                                    </p>
                                                                )}
                                                                {alert.deadline && (
                                                                    <p className="text-[10px] mt-1 opacity-70">
                                                                        Deadline: {new Date(alert.deadline).toLocaleDateString()}
                                                                    </p>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            {alert.status === 'unread' && (
                                                                <button
                                                                    onClick={() => markAlertReadMutation.mutate(alert.id)}
                                                                    className="p-1.5 hover:bg-black/5 rounded transition-colors"
                                                                    title="Mark as read"
                                                                >
                                                                    <CheckCircle size={14} />
                                                                </button>
                                                            )}
                                                            {alert.status !== 'dismissed' && (
                                                                <button
                                                                    onClick={() => dismissAlertMutation.mutate(alert.id)}
                                                                    className="p-1.5 hover:bg-black/5 rounded transition-colors"
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
                        <div className="bg-zinc-50 border border-zinc-200 rounded p-12 text-center h-full flex flex-col items-center justify-center min-h-[400px]">
                            <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-white border border-zinc-200 flex items-center justify-center shadow-sm">
                                <MapPin size={24} className="text-zinc-400" />
                            </div>
                            <h3 className="text-zinc-900 font-medium mb-2">Select a Location</h3>
                            <p className="text-zinc-500 text-sm max-w-sm">
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
                        className="fixed inset-0 bg-zinc-900/20 backdrop-blur-sm z-50 flex items-center justify-center p-4"
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
                            className="bg-white shadow-2xl rounded-sm p-8 w-full max-w-md"
                            onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        >
                            <div className="flex items-center justify-between mb-6 border-b border-zinc-100 pb-4">
                                <h2 className="text-xl font-light text-zinc-900">
                                    {editingLocation ? 'Edit Location' : 'Add Location'}
                                </h2>
                                <button
                                    onClick={() => {
                                        setShowAddModal(false);
                                        setEditingLocation(null);
                                        setFormData(emptyFormData);
                                    }}
                                    className="p-1 text-zinc-400 hover:text-zinc-600"
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
                                        className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
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
                                        className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
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
                                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
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
                                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
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
                                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
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
                                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                                        />
                                    </div>
                                </div>

                                <div className="flex gap-3 pt-6 border-t border-zinc-100">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowAddModal(false);
                                            setEditingLocation(null);
                                            setFormData(emptyFormData);
                                        }}
                                        className="flex-1 px-4 py-2 bg-white border border-zinc-200 text-zinc-600 hover:bg-zinc-50 rounded text-sm font-medium transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={createLocationMutation.isPending || updateLocationMutation.isPending}
                                        className="flex-1 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 text-white rounded text-sm font-medium transition-colors disabled:opacity-50"
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
