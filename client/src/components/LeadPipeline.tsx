import { useState, useEffect } from 'react';
import { leadsAgent } from '../api/client';
import type { Lead, LeadStatus, LeadPriority } from '../types/leads';

const STATUS_LABELS: Partial<Record<LeadStatus, string>> = {
    new: 'New Leads',
    qualified: 'Qualified',
    staging: 'Staging/Review',
    prioritized: 'Prioritized',
    draft_ready: 'Draft Ready',
    approved: 'Approved',
    contacted: 'Contacted',
    replied: 'Replied',
    closed: 'Closed'
};

const STATUS_COLORS: Partial<Record<LeadStatus, string>> = {
    new: 'zinc',
    qualified: 'emerald',
    staging: 'amber',
    prioritized: 'purple',
    draft_ready: 'blue',
    approved: 'emerald',
    contacted: 'indigo',
    replied: 'teal',
    closed: 'zinc'
};

interface LeadPipelineProps {
    onSelectLead: (lead: Lead) => void;
    refreshTrigger?: number;
}

export default function LeadPipeline({ onSelectLead, refreshTrigger }: LeadPipelineProps) {
    const [pipeline, setPipeline] = useState<Record<string, Lead[]>>({});
    const [isLoading, setIsLoading] = useState(true);

    const fetchPipeline = async () => {
        setIsLoading(true);
        try {
            const response = await leadsAgent.getPipeline();
            setPipeline(response);
        } catch (error) {
            console.error('Failed to fetch pipeline:', error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchPipeline();
    }, [refreshTrigger]);

    const getPriorityColor = (priority: LeadPriority) => {
        switch (priority) {
            case 'high': return 'text-rose-500';
            case 'medium': return 'text-amber-500';
            case 'low': return 'text-zinc-500';
            case 'skip': return 'text-zinc-700';
            default: return 'text-zinc-500';
        }
    };

    if (isLoading && Object.keys(pipeline).length === 0) {
        return (
            <div className="flex items-center justify-center py-20">
                <div className="flex flex-col items-center gap-3">
                    <div className="w-4 h-4 rounded-full bg-white animate-pulse" />
                    <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono">Loading Pipeline</span>
                </div>
            </div>
        );
    }

    return (
        <div className="flex gap-4 overflow-x-auto pb-6 -mx-2 px-2 scrollbar-thin scrollbar-thumb-zinc-800">
            {(['new', 'staging', 'draft_ready', 'approved', 'contacted'] as LeadStatus[]).map((status) => (
                <div key={status} className="flex-shrink-0 w-80 flex flex-col gap-4">
                    <div className="flex items-center justify-between px-1">
                        <h3 className="text-[10px] font-bold text-zinc-400 uppercase tracking-[0.2em] flex items-center gap-2">
                            <span className={`w-1.5 h-1.5 rounded-full bg-${STATUS_COLORS[status]}-500`} />
                            {STATUS_LABELS[status]}
                            <span className="text-zinc-600 font-normal normal-case tracking-normal ml-1">
                                ({pipeline[status]?.length || 0})
                            </span>
                        </h3>
                    </div>

                    <div className="flex flex-col gap-3 min-h-[400px]">
                        {pipeline[status]?.map((lead) => (
                            <button
                                key={lead.id}
                                onClick={() => onSelectLead(lead)}
                                className="group p-4 bg-zinc-900/40 border border-zinc-800 hover:border-zinc-700 hover:bg-zinc-900/60 rounded-xl transition-all text-left"
                            >
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <div className={`text-[10px] uppercase font-bold tracking-tighter ${getPriorityColor(lead.priority)}`}>
                                        {lead.priority}
                                    </div>
                                    <div className="text-[8px] text-zinc-600 font-mono">
                                        {new Date(lead.created_at).toLocaleDateString()}
                                    </div>
                                </div>

                                <h4 className="text-xs font-bold text-white group-hover:text-emerald-400 transition-colors line-clamp-2 leading-tight mb-1">
                                    {lead.title}
                                </h4>
                                <div className="text-[10px] text-zinc-400 truncate">{lead.company_name}</div>

                                {lead.location && (
                                    <div className="text-[9px] text-zinc-500 mt-2 flex items-center gap-1">
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                        </svg>
                                        {lead.location}
                                    </div>
                                )}

                                {lead.relevance_score && (
                                    <div className="mt-3 flex items-center gap-2">
                                        <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-emerald-500/50"
                                                style={{ width: `${(lead.relevance_score / 10) * 100}%` }}
                                            />
                                        </div>
                                        <span className="text-[9px] text-zinc-600 font-bold">{lead.relevance_score}/10</span>
                                    </div>
                                )}
                            </button>
                        ))}

                        {(!pipeline[status] || pipeline[status].length === 0) && (
                            <div className="flex-1 border border-dashed border-zinc-900 rounded-xl flex items-center justify-center p-8">
                                <p className="text-[10px] text-zinc-700 uppercase tracking-widest text-center">No Leads</p>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}
