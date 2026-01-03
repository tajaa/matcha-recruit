import { useState, useEffect } from 'react';
import { leadsAgent } from '../api/client';
import type { Lead, LeadStatus, LeadPriority } from '../types/leads';

const STATUS_CONFIG: Record<string, { label: string; color: string; description: string }> = {
    new: { label: 'New Leads', color: 'border-blue-500/30', description: 'Fresh from search' },
    qualified: { label: 'Qualified', color: 'border-emerald-500/30', description: 'Passed AI check' },
    staging: { label: 'Finding Contacts', color: 'border-amber-500/30', description: 'Need contact info' },
    draft_ready: { label: 'Draft Ready', color: 'border-purple-500/30', description: 'Email generated' },
    approved: { label: 'Approved', color: 'border-pink-500/30', description: 'Ready to send' },
    contacted: { label: 'Contacted', color: 'border-indigo-500/30', description: 'Email sent' },
    replied: { label: 'Replied', color: 'border-green-500/30', description: 'Candidate responded' },
};

const ORDERED_STATUSES: LeadStatus[] = ['new', 'staging', 'draft_ready', 'approved', 'contacted'];

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

    const getPriorityBadge = (priority: LeadPriority) => {
        switch (priority) {
            case 'high': return <span className="text-[9px] font-bold text-rose-500 uppercase tracking-wider">High Priority</span>;
            case 'medium': return <span className="text-[9px] font-bold text-amber-500 uppercase tracking-wider">Medium</span>;
            case 'low': return <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-wider">Low</span>;
            default: return null;
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
        <div className="flex gap-6 overflow-x-auto pb-6 px-2 min-h-[600px] scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
            {ORDERED_STATUSES.map((status) => {
                const leads = pipeline[status] || [];
                const config = STATUS_CONFIG[status] || { label: status, color: 'border-zinc-800', description: '' };
                
                return (
                    <div key={status} className="flex-shrink-0 w-80 flex flex-col gap-4">
                        {/* Column Header */}
                        <div className={`flex flex-col gap-1 pb-2 border-b-2 ${config.color.replace('/30', '')}`}>
                            <div className="flex items-center justify-between">
                                <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                                    {config.label}
                                </h3>
                                <span className="text-[10px] font-mono text-zinc-500 bg-zinc-900 px-2 py-0.5 rounded-full">
                                    {leads.length}
                                </span>
                            </div>
                            <p className="text-[10px] text-zinc-500 truncate">{config.description}</p>
                        </div>

                        {/* Cards */}
                        <div className="flex flex-col gap-3 flex-1">
                            {leads.map((lead) => (
                                <div
                                    key={lead.id}
                                    onClick={() => onSelectLead(lead)}
                                    className="group relative p-4 bg-zinc-900/40 border border-zinc-800 hover:border-zinc-600 hover:bg-zinc-900/80 rounded-xl transition-all cursor-pointer shadow-sm hover:shadow-md hover:-translate-y-0.5"
                                >
                                    {/* Top Metadata */}
                                    <div className="flex items-start justify-between mb-3">
                                        <div className="flex-1 min-w-0 pr-2">
                                            <div className="text-[10px] text-zinc-500 truncate">{lead.company_name}</div>
                                            <h4 className="text-sm font-bold text-white group-hover:text-emerald-400 transition-colors line-clamp-2 leading-tight mt-0.5">
                                                {lead.title}
                                            </h4>
                                        </div>
                                        {lead.relevance_score && (
                                            <div className="flex flex-col items-end shrink-0">
                                                <div className={`text-xs font-bold ${lead.relevance_score >= 7 ? 'text-emerald-500' : 'text-zinc-500'}`}>
                                                    {lead.relevance_score}/10
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {/* Middle Details */}
                                    <div className="flex items-center gap-2 mb-4">
                                        {lead.location && (
                                            <span className="flex items-center gap-1 text-[10px] text-zinc-500">
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                                </svg>
                                                {lead.location}
                                            </span>
                                        )}
                                    </div>

                                    {/* Bottom Status / Action */}
                                    <div className="flex items-center justify-between pt-3 border-t border-zinc-800/50">
                                        {getPriorityBadge(lead.priority)}
                                        
                                        {/* Status Indicators */}
                                        {status === 'staging' && (
                                            <div className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide flex items-center gap-1.5 ${
                                                lead.contacts_count > 0 
                                                    ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' 
                                                    : 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
                                            }`}>
                                                <div className={`w-1.5 h-1.5 rounded-full ${lead.contacts_count > 0 ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                                                {lead.contacts_count > 0 ? `${lead.contacts_count} Contact${lead.contacts_count > 1 ? 's' : ''}` : 'No Contacts'}
                                            </div>
                                        )}

                                        {status === 'new' && (
                                            <div className="text-[9px] text-zinc-500 flex items-center gap-1">
                                                <span>Review Lead</span>
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                                                </svg>
                                            </div>
                                        )}
                                    </div>
                                    
                                    {/* Pending Analysis Warning */}
                                    {lead.gemini_analysis?.reasoning?.includes("Pending AI Analysis") && (
                                        <div className="absolute top-2 right-2 w-2 h-2 bg-amber-500 rounded-full animate-pulse" title="AI Analysis Pending" />
                                    )}
                                </div>
                            ))}

                            {leads.length === 0 && (
                                <div className="h-32 border border-dashed border-zinc-800/50 rounded-xl flex items-center justify-center">
                                    <p className="text-[10px] text-zinc-700 uppercase tracking-widest">Empty</p>
                                </div>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}