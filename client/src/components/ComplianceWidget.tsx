import { useQuery } from '@tanstack/react-query';
import { complianceAPI, COMPLIANCE_CATEGORY_LABELS } from '../api/compliance';
import { Shield, MapPin, AlertTriangle, ChevronRight, Plus, RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';

export function ComplianceWidget() {
    const { data: summary, isLoading, error } = useQuery({
        queryKey: ['compliance-summary'],
        queryFn: complianceAPI.getSummary,
    });

    if (isLoading) {
        return (
            <div className="bg-white border border-zinc-200 p-6 animate-pulse">
                <div className="h-6 w-48 bg-zinc-100 rounded mb-4" />
                <div className="grid grid-cols-4 gap-4 mb-4">
                    {[1, 2, 3, 4].map(i => (
                        <div key={i} className="h-16 bg-zinc-100 rounded" />
                    ))}
                </div>
                <div className="h-32 bg-zinc-100 rounded" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-white border border-zinc-200 p-6">
                <div className="flex items-center gap-3 mb-4">
                    <Shield size={20} className="text-zinc-600" />
                    <h2 className="text-lg font-medium text-zinc-900">Compliance</h2>
                </div>
                <p className="text-zinc-500 text-sm">Failed to load compliance data</p>
            </div>
        );
    }

    if (!summary || summary.total_locations === 0) {
        return (
            <div className="bg-white border border-zinc-200 p-6">
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 border border-zinc-200 bg-zinc-50 flex items-center justify-center">
                        <Shield size={20} className="text-zinc-600" />
                    </div>
                    <div>
                        <h2 className="text-lg font-medium text-zinc-900">Compliance Tracking</h2>
                        <p className="text-xs text-zinc-500">Monitor labor law & tax requirements</p>
                    </div>
                </div>

                <div className="text-center py-8">
                    <div className="w-16 h-16 mx-auto mb-4 border border-zinc-200 bg-zinc-50 flex items-center justify-center">
                        <MapPin size={28} className="text-zinc-400" />
                    </div>
                    <h3 className="text-zinc-900 font-medium mb-2">No Locations Added</h3>
                    <p className="text-zinc-500 text-sm mb-4 max-w-sm mx-auto">
                        Add your business locations to automatically track compliance requirements like minimum wage, workers' comp, and tax rates.
                    </p>
                    <Link
                        to="/app/matcha/compliance"
                        className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 border border-zinc-200 text-sm font-medium transition-colors"
                    >
                        <Plus size={16} />
                        Add Location
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-white border border-zinc-200 p-6">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 border border-zinc-200 bg-zinc-50 flex items-center justify-center">
                        <Shield size={20} className="text-zinc-600" />
                    </div>
                    <div>
                        <h2 className="text-lg font-medium text-zinc-900">Compliance</h2>
                        <p className="text-xs text-zinc-500">Labor law & tax requirements</p>
                    </div>
                </div>
                <Link
                    to="/app/matcha/compliance"
                    className="flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 transition-colors"
                >
                    View All
                    <ChevronRight size={16} />
                </Link>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <div className="bg-zinc-50 border border-zinc-100 p-3 text-center">
                    <div className="text-2xl font-semibold text-zinc-900">{summary.total_locations}</div>
                    <div className="text-xs text-zinc-500">Locations</div>
                </div>
                <div className="bg-zinc-50 border border-zinc-100 p-3 text-center">
                    <div className="text-2xl font-semibold text-zinc-900">{summary.total_requirements}</div>
                    <div className="text-xs text-zinc-500">Requirements</div>
                </div>
                <div className="bg-zinc-50 border border-zinc-100 p-3 text-center">
                    <div className={`text-2xl font-semibold ${summary.unread_alerts > 0 ? 'text-zinc-900' : 'text-zinc-900'}`}>
                        {summary.unread_alerts}
                    </div>
                    <div className="text-xs text-zinc-500">Unread Alerts</div>
                </div>
                <div className="bg-zinc-50 border border-zinc-100 p-3 text-center">
                    <div className={`text-2xl font-semibold ${summary.critical_alerts > 0 ? 'text-zinc-900' : 'text-zinc-900'}`}>
                        {summary.critical_alerts}
                    </div>
                    <div className="text-xs text-zinc-500">Critical</div>
                </div>
            </div>

            {(summary.recent_changes?.length ?? 0) > 0 ? (
                <div>
                    <h3 className="text-sm font-medium text-zinc-500 mb-3">Recent Changes</h3>
                    <div className="space-y-2">
                        {(summary.recent_changes ?? []).slice(0, 3).map((change, idx) => (
                            <div
                                key={idx}
                                className="flex items-start gap-3 p-3 bg-zinc-50 border border-zinc-100"
                            >
                                <div className="w-8 h-8 border border-zinc-200 bg-white flex items-center justify-center flex-shrink-0">
                                    <RefreshCw size={14} className="text-zinc-600" />
                                </div>
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium text-zinc-900 truncate">
                                            {change.title}
                                        </span>
                                        <span className="text-xs px-1.5 py-0.5 bg-zinc-100 text-zinc-500 border border-zinc-200">
                                            {COMPLIANCE_CATEGORY_LABELS[change.category] || change.category}
                                        </span>
                                    </div>
                                    <p className="text-xs text-zinc-500 mt-0.5">
                                        {change.old_value} → <span className="text-zinc-900 font-medium">{change.new_value}</span>
                                    </p>
                                    <p className="text-xs text-zinc-400 mt-0.5">{change.location}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ) : (
                <div className="text-center py-4 text-zinc-500 text-sm">
                    No recent changes detected
                </div>
            )}

            {summary.critical_alerts > 0 && (
                <div className="mt-4 p-3 bg-zinc-100 border border-zinc-200 flex items-center gap-3">
                    <AlertTriangle size={18} className="text-zinc-700 flex-shrink-0" />
                    <p className="text-sm text-zinc-700">
                        You have {summary.critical_alerts} critical compliance alert{summary.critical_alerts > 1 ? 's' : ''} requiring attention
                    </p>
                </div>
            )}
        </div>
    );
}

export default ComplianceWidget;
