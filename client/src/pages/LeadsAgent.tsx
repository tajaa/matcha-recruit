import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import LeadSearch from '../components/LeadSearch';
import LeadPipeline from '../components/LeadPipeline';
import LeadDetailDrawer from '../components/LeadDetailDrawer';
import LeadEmails from '../components/LeadEmails';

export default function LeadsAgent() {
    const { hasRole } = useAuth();
    const [activeTab, setActiveTab] = useState<'search' | 'pipeline' | 'emails' | 'stats'>('search');
    const [refreshKey, setRefreshKey] = useState(0);
    const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);

    const handleSearchComplete = () => {
        setRefreshKey(prev => prev + 1);
        setActiveTab('pipeline');
    };

    const handleUpdate = () => {
        setRefreshKey(prev => prev + 1);
    };

    if (!hasRole('admin')) {
        return (
            <div className="flex items-center justify-center min-h-[50vh]">
                <div className="text-center">
                    <h2 className="text-xl font-bold text-white mb-2">Access Denied</h2>
                    <p className="text-zinc-500">You do not have permission to access the Leads Agent.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-6">
                <div>
                    <h1 className="text-2xl font-bold text-white tracking-tight">Leads Agent</h1>
                    <p className="text-zinc-500 text-sm mt-1">
                        Agentic workflow for executive lead generation and outreach.
                    </p>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex items-center gap-1 p-1 bg-zinc-900/50 border border-zinc-800 rounded-lg self-start">
                {(['search', 'pipeline', 'emails', 'stats'] as const).map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`px-4 py-1.5 text-[10px] font-medium uppercase tracking-widest transition-all rounded-md ${activeTab === tab
                            ? 'bg-zinc-800 text-white shadow-sm'
                            : 'text-zinc-500 hover:text-zinc-300'
                            }`}
                    >
                        {tab}
                    </button>
                ))}
            </div>

            {/* Content */}
            <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-6 min-h-[60vh]">
                {activeTab === 'search' && (
                    <LeadSearch onSearchComplete={handleSearchComplete} />
                )}
                {activeTab === 'pipeline' && (
                    <LeadPipeline
                        refreshTrigger={refreshKey}
                        onSelectLead={(lead) => setSelectedLeadId(lead.id)}
                    />
                )}
                {activeTab === 'emails' && (
                    <LeadEmails />
                )}
                {activeTab === 'stats' && (
                    <div className="flex flex-col items-center justify-center h-full text-zinc-500 py-20">
                        <svg className="w-12 h-12 mb-4 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
                        </svg>
                        <p className="text-sm">Lead generation stats coming soon...</p>
                    </div>
                )}
            </div>

            {/* Detail Drawer */}
            <LeadDetailDrawer
                leadId={selectedLeadId}
                onClose={() => setSelectedLeadId(null)}
                onUpdate={handleUpdate}
            />
        </div>
    );
}
