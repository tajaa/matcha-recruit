import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { BusinessLocation, ComplianceRequirement, LocationCreate } from '../api/compliance';
import {
    complianceAPI,
    COMPLIANCE_CATEGORY_LABELS,
    JURISDICTION_LEVEL_LABELS
} from '../api/compliance';
import {
    Shield, MapPin, Plus, Trash2, Edit2, X,
    ChevronDown, ChevronRight, AlertTriangle, Bell, CheckCircle,
    ExternalLink, Clock, Building2
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
                return 'bg-red-500/20 text-red-400 border-red-500/30';
            case 'warning':
                return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
            default:
                return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
        }
    };

    const selectedLocation = locations?.find(l => l.id === selectedLocationId);
    const locationAlerts = alerts?.filter(a => a.location_id === selectedLocationId) || [];
    const unreadAlertsCount = locationAlerts.filter(a => a.status === 'unread').length;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-thin tracking-tight text-white flex items-center gap-3">
                        <Shield size={28} className="text-emerald-400" />
                        Compliance Tracking
                    </h1>
                    <p className="text-gray-400 mt-1">
                        Monitor labor laws, tax rates, and posting requirements by location
                    </p>
                </div>
                <button
                    onClick={() => {
                        setFormData(emptyFormData);
                        setEditingLocation(null);
                        setShowAddModal(true);
                    }}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded-lg text-sm font-medium transition-colors"
                >
                    <Plus size={18} />
                    Add Location
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1 space-y-4">
                    <h2 className="text-lg font-medium text-white">Your Locations</h2>

                    {loadingLocations ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map(i => (
                                <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-4 animate-pulse">
                                    <div className="h-5 w-32 bg-white/10 rounded mb-2" />
                                    <div className="h-4 w-48 bg-white/10 rounded" />
                                </div>
                            ))}
                        </div>
                    ) : locations?.length === 0 ? (
                        <div className="bg-white/5 border border-white/10 rounded-xl p-8 text-center">
                            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-white/5 flex items-center justify-center">
                                <MapPin size={28} className="text-gray-500" />
                            </div>
                            <h3 className="text-white font-medium mb-2">No Locations Yet</h3>
                            <p className="text-gray-400 text-sm mb-4">
                                Add your business locations to start tracking compliance requirements.
                            </p>
                            <button
                                onClick={() => setShowAddModal(true)}
                                className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded-lg text-sm font-medium transition-colors"
                            >
                                <Plus size={16} />
                                Add Location
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {locations?.map(location => (
                                <div
                                    key={location.id}
                                    onClick={() => setSelectedLocationId(location.id)}
                                    className={`bg-white/5 border rounded-xl p-4 cursor-pointer transition-all ${
                                        selectedLocationId === location.id
                                            ? 'border-emerald-500/50 bg-emerald-500/5'
                                            : 'border-white/10 hover:border-white/20'
                                    }`}
                                >
                                    <div className="flex items-start justify-between">
                                        <div className="min-w-0 flex-1">
                                            <h3 className="text-white font-medium truncate">
                                                {location.name || `${location.city}, ${location.state}`}
                                            </h3>
                                            <p className="text-gray-400 text-sm truncate">
                                                {location.address ? `${location.address}, ` : ''}{location.city}, {location.state} {location.zipcode}
                                            </p>
                                            <div className="flex items-center gap-4 mt-2 text-xs">
                                                <span className="text-gray-500">
                                                    {location.requirements_count} requirements
                                                </span>
                                                {location.unread_alerts_count > 0 && (
                                                    <span className="text-amber-400 flex items-center gap-1">
                                                        <Bell size={12} />
                                                        {location.unread_alerts_count} alerts
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-1 ml-2">
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    openEditModal(location);
                                                    setShowAddModal(true);
                                                }}
                                                className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                                                title="Edit"
                                            >
                                                <Edit2 size={14} />
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    if (confirm('Delete this location?')) {
                                                        deleteLocationMutation.mutate(location.id);
                                                    }
                                                }}
                                                className="p-1.5 text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                                                title="Delete"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </div>
                                    {location.last_compliance_check && (
                                        <p className="text-xs text-gray-500 mt-2 flex items-center gap-1">
                                            <Clock size={10} />
                                            Last checked: {new Date(location.last_compliance_check).toLocaleDateString()}
                                        </p>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div className="lg:col-span-2">
                    {selectedLocationId && selectedLocation ? (
                        <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
                            <div className="p-4 border-b border-white/10 flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                                        <Building2 size={20} className="text-emerald-400" />
                                    </div>
                                    <div>
                                        <h2 className="text-lg font-medium text-white">
                                            {selectedLocation.name || `${selectedLocation.city}, ${selectedLocation.state}`}
                                        </h2>
                                        <p className="text-sm text-gray-400">
                                            {selectedLocation.city}, {selectedLocation.state} {selectedLocation.zipcode}
                                        </p>
                                    </div>
                                </div>
                            </div>

                            <div className="flex border-b border-white/10">
                                <button
                                    onClick={() => setActiveTab('requirements')}
                                    className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                                        activeTab === 'requirements'
                                            ? 'text-white border-b-2 border-emerald-500'
                                            : 'text-gray-400 hover:text-white'
                                    }`}
                                >
                                    Requirements ({requirements?.length || 0})
                                </button>
                                <button
                                    onClick={() => setActiveTab('alerts')}
                                    className={`flex-1 px-4 py-3 text-sm font-medium transition-colors relative ${
                                        activeTab === 'alerts'
                                            ? 'text-white border-b-2 border-emerald-500'
                                            : 'text-gray-400 hover:text-white'
                                    }`}
                                >
                                    Alerts ({locationAlerts.length})
                                    {unreadAlertsCount > 0 && (
                                        <span className="ml-2 px-1.5 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded-full">
                                            {unreadAlertsCount}
                                        </span>
                                    )}
                                </button>
                            </div>

                            <div className="p-4 max-h-[600px] overflow-y-auto custom-scrollbar">
                                {activeTab === 'requirements' ? (
                                    loadingRequirements ? (
                                        <div className="space-y-3">
                                            {[1, 2, 3].map(i => (
                                                <div key={i} className="h-16 bg-white/10 rounded-xl animate-pulse" />
                                            ))}
                                        </div>
                                    ) : Object.keys(requirementsByCategory).length === 0 ? (
                                        <div className="text-center py-8 text-gray-400">
                                            No requirements found. Add requirements to see them here.
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {Object.entries(requirementsByCategory).map(([category, reqs]) => (
                                                <div key={category} className="bg-white/5 rounded-xl overflow-hidden">
                                                    <div className="flex items-center justify-between p-4 hover:bg-white/5 transition-colors">
                                                        <button
                                                            onClick={() => toggleCategory(category)}
                                                            className="flex items-center gap-3 text-left flex-1"
                                                        >
                                                            <span className="text-white font-medium">
                                                                {COMPLIANCE_CATEGORY_LABELS[category] || category}
                                                            </span>
                                                            <span className="px-2 py-0.5 bg-white/10 text-gray-400 text-xs rounded-full">
                                                                {reqs.length}
                                                            </span>
                                                            {expandedCategories.has(category) ? (
                                                                <ChevronDown size={18} className="text-gray-400" />
                                                            ) : (
                                                                <ChevronRight size={18} className="text-gray-400" />
                                                            )}
                                                        </button>
                                                    </div>

                                                    <AnimatePresence initial={false}>
                                                        {expandedCategories.has(category) && (
                                                            <motion.div
                                                                initial={{ height: 0, opacity: 0 }}
                                                                animate={{ height: 'auto', opacity: 1 }}
                                                                exit={{ height: 0, opacity: 0 }}
                                                                transition={{ duration: 0.2 }}
                                                                className="overflow-hidden"
                                                            >
                                                                <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
                                                                    {reqs.map(req => (
                                                                        <div key={req.id} className="bg-white/5 rounded-lg p-3">
                                                                            <div className="flex items-start justify-between">
                                                                                <div>
                                                                                    <h4 className="text-white text-sm font-medium">
                                                                                        {req.title}
                                                                                    </h4>
                                                                                    <div className="flex items-center gap-2 mt-1">
                                                                                        <span className="px-1.5 py-0.5 bg-white/10 text-gray-400 text-xs rounded">
                                                                                            {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                                                                                        </span>
                                                                                        <span className="text-gray-500 text-xs">
                                                                                            {req.jurisdiction_name}
                                                                                        </span>
                                                                                    </div>
                                                                                </div>
                                                                                {req.current_value && (
                                                                                    <span className="text-emerald-400 font-medium text-sm">
                                                                                        {req.current_value}
                                                                                    </span>
                                                                                )}
                                                                            </div>
                                                                            {req.description && (
                                                                                <p className="text-gray-400 text-xs mt-2">
                                                                                    {req.description}
                                                                                </p>
                                                                            )}
                                                                            <div className="flex items-center justify-between mt-2 pt-2 border-t border-white/5">
                                                                                <div className="flex items-center gap-3 text-xs">
                                                                                    {req.effective_date && (
                                                                                        <span className="text-gray-500">
                                                                                            Effective: {new Date(req.effective_date).toLocaleDateString()}
                                                                                        </span>
                                                                                    )}
                                                                                    {req.previous_value && (
                                                                                        <span className="text-amber-400">
                                                                                            Changed from {req.previous_value}
                                                                                        </span>
                                                                                    )}
                                                                                </div>
                                                                                {req.source_url && (
                                                                                    <a
                                                                                        href={req.source_url}
                                                                                        target="_blank"
                                                                                        rel="noopener noreferrer"
                                                                                        className="text-blue-400 hover:text-blue-300 text-xs flex items-center gap-1"
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
                                                <div key={i} className="h-20 bg-white/10 rounded-xl animate-pulse" />
                                            ))}
                                        </div>
                                    ) : locationAlerts.length === 0 ? (
                                        <div className="text-center py-8">
                                            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-white/5 flex items-center justify-center">
                                                <CheckCircle size={28} className="text-emerald-400" />
                                            </div>
                                            <p className="text-gray-400">No alerts for this location</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {locationAlerts.map(alert => (
                                                <div
                                                    key={alert.id}
                                                    className={`border rounded-xl p-4 ${getSeverityStyles(alert.severity)} ${
                                                        alert.status === 'unread' ? 'border-opacity-100' : 'border-opacity-30 opacity-60'
                                                    }`}
                                                >
                                                    <div className="flex items-start justify-between">
                                                        <div className="flex items-start gap-3">
                                                            <AlertTriangle size={18} className="mt-0.5 flex-shrink-0" />
                                                            <div>
                                                                <h4 className="font-medium">{alert.title}</h4>
                                                                <p className="text-sm mt-1 opacity-80">{alert.message}</p>
                                                                {alert.action_required && (
                                                                    <p className="text-sm mt-2 font-medium">
                                                                        Action: {alert.action_required}
                                                                    </p>
                                                                )}
                                                                {alert.deadline && (
                                                                    <p className="text-xs mt-1 opacity-70">
                                                                        Deadline: {new Date(alert.deadline).toLocaleDateString()}
                                                                    </p>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-1">
                                                            {alert.status === 'unread' && (
                                                                <button
                                                                    onClick={() => markAlertReadMutation.mutate(alert.id)}
                                                                    className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
                                                                    title="Mark as read"
                                                                >
                                                                    <CheckCircle size={16} />
                                                                </button>
                                                            )}
                                                            {alert.status !== 'dismissed' && (
                                                                <button
                                                                    onClick={() => dismissAlertMutation.mutate(alert.id)}
                                                                    className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
                                                                    title="Dismiss"
                                                                >
                                                                    <X size={16} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-2 mt-3 text-xs opacity-60">
                                                        <span>{new Date(alert.created_at).toLocaleString()}</span>
                                                        {alert.category && (
                                                            <>
                                                                <span>•</span>
                                                                <span>{COMPLIANCE_CATEGORY_LABELS[alert.category] || alert.category}</span>
                                                            </>
                                                        )}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="bg-white/5 border border-white/10 rounded-2xl p-8 text-center h-full flex flex-col items-center justify-center min-h-[400px]">
                            <div className="w-20 h-20 mx-auto mb-4 rounded-2xl bg-white/5 flex items-center justify-center">
                                <MapPin size={36} className="text-gray-500" />
                            </div>
                            <h3 className="text-white font-medium mb-2">Select a Location</h3>
                            <p className="text-gray-400 text-sm max-w-sm">
                                Choose a location from the list to view compliance requirements and alerts.
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
                        className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
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
                            className="bg-[#111] border border-white/10 rounded-2xl p-6 w-full max-w-md"
                            onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        >
                            <div className="flex items-center justify-between mb-6">
                                <h2 className="text-lg font-medium text-white">
                                    {editingLocation ? 'Edit Location' : 'Add Location'}
                                </h2>
                                <button
                                    onClick={() => {
                                        setShowAddModal(false);
                                        setEditingLocation(null);
                                        setFormData(emptyFormData);
                                    }}
                                    className="p-1 text-gray-400 hover:text-white"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <form onSubmit={handleSubmitLocation} className="space-y-4">
                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">
                                        Location Name (optional)
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.name}
                                        onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                                        placeholder="e.g., Main Office, Warehouse"
                                        className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm text-gray-400 mb-1">
                                        Street Address (optional)
                                    </label>
                                    <input
                                        type="text"
                                        value={formData.address}
                                        onChange={e => setFormData(prev => ({ ...prev, address: e.target.value }))}
                                        placeholder="123 Main St"
                                        className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50"
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm text-gray-400 mb-1">
                                            City <span className="text-red-400">*</span>
                                        </label>
                                        <input
                                            type="text"
                                            value={formData.city}
                                            onChange={e => setFormData(prev => ({ ...prev, city: e.target.value }))}
                                            required
                                            placeholder="San Francisco"
                                            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm text-gray-400 mb-1">
                                            State <span className="text-red-400">*</span>
                                        </label>
                                        <select
                                            value={formData.state}
                                            onChange={e => setFormData(prev => ({ ...prev, state: e.target.value }))}
                                            required
                                            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-emerald-500/50"
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
                                        <label className="block text-sm text-gray-400 mb-1">
                                            County (optional)
                                        </label>
                                        <input
                                            type="text"
                                            value={formData.county}
                                            onChange={e => setFormData(prev => ({ ...prev, county: e.target.value }))}
                                            placeholder="San Francisco"
                                            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm text-gray-400 mb-1">
                                            ZIP Code <span className="text-red-400">*</span>
                                        </label>
                                        <input
                                            type="text"
                                            value={formData.zipcode}
                                            onChange={e => setFormData(prev => ({ ...prev, zipcode: e.target.value }))}
                                            required
                                            placeholder="94105"
                                            maxLength={10}
                                            className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-emerald-500/50"
                                        />
                                    </div>
                                </div>

                                <div className="flex gap-3 pt-4">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setShowAddModal(false);
                                            setEditingLocation(null);
                                            setFormData(emptyFormData);
                                        }}
                                        className="flex-1 px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-400 rounded-lg text-sm font-medium transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={createLocationMutation.isPending || updateLocationMutation.isPending}
                                        className="flex-1 px-4 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
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
