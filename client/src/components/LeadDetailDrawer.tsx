import { useState, useEffect } from 'react';
import { leadsAgent } from '../api/client';
import type { LeadWithContacts, LeadStatus, LeadPriority } from '../types/leads';

interface LeadDetailDrawerProps {
    leadId: string | null;
    onClose: () => void;
    onUpdate: () => void;
}

export default function LeadDetailDrawer({ leadId, onClose, onUpdate }: LeadDetailDrawerProps) {
    const [lead, setLead] = useState<LeadWithContacts | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);
    const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
    const [activeSubTab, setActiveSubTab] = useState<'info' | 'contacts' | 'emails'>('info');
    const [isAddingContact, setIsAddingContact] = useState(false);
    const [newContact, setNewContact] = useState({ name: '', title: '', email: '', linkedin_url: '' });

    const fetchLeadDetail = async () => {
        if (!leadId) return;
        setIsLoading(true);
        try {
            const response = await leadsAgent.get(leadId);
            setLead(response);
        } catch (error) {
            console.error('Failed to fetch lead detail:', error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (leadId) {
            fetchLeadDetail();
        } else {
            setLead(null);
        }
    }, [leadId]);

    const handleUpdateStatus = async (status: LeadStatus) => {
        if (!lead) return;
        try {
            await leadsAgent.update(lead.id, { status });
            fetchLeadDetail();
            onUpdate();
        } catch (error) {
            console.error('Update failed:', error);
        }
    };

    const handleUpdatePriority = async (priority: LeadPriority) => {
        if (!lead) return;
        try {
            await leadsAgent.update(lead.id, { priority });
            fetchLeadDetail();
            onUpdate();
        } catch (error) {
            console.error('Update failed:', error);
        }
    };

    const findContacts = async () => {
        if (!lead) return;
        setIsProcessing(true);
        try {
            await leadsAgent.findContacts(lead.id);
            await fetchLeadDetail();
            setActiveSubTab('contacts');
        } catch (error) {
            console.error('Find contacts failed:', error);
        } finally {
            setIsProcessing(false);
        }
    };

    const researchContact = async () => {
        if (!lead) return;
        setIsProcessing(true);
        setMessage(null);
        try {
            await leadsAgent.researchContact(lead.id);
            await fetchLeadDetail();
            setMessage({ type: 'success', text: 'Contact found via web research!' });
            // Clear success message after 3 seconds
            setTimeout(() => setMessage(null), 3000);
        } catch (error: any) {
            console.error('Research contact failed:', error);
            setMessage({ 
                type: 'error', 
                text: `Error: ${error.response?.data?.detail || error.message || 'Unknown error'}` 
            });
        } finally {
            setIsProcessing(false);
        }
    };

    const reAnalyze = async () => {
        if (!lead) return;
        setIsProcessing(true);
        setMessage(null);
        try {
            await leadsAgent.reanalyze(lead.id);
            await fetchLeadDetail();
            setMessage({ type: 'success', text: 'Analysis updated!' });
            setTimeout(() => setMessage(null), 3000);
        } catch (error: any) {
            console.error('Re-analyze failed:', error);
            setMessage({ 
                type: 'error', 
                text: `Error: ${error.response?.data?.detail || error.message || 'Unknown error'}` 
            });
        } finally {
            setIsProcessing(false);
        }
    };

    const setPrimary = async (contactId: string) => {
        if (!lead) return;
        try {
            await leadsAgent.setPrimaryContact(lead.id, contactId);
            await fetchLeadDetail();
        } catch (error) {
            console.error('Set primary failed:', error);
        }
    };

    const draftEmail = async (contactId?: string) => {
        if (!lead) return;
        setIsProcessing(true);
        try {
            await leadsAgent.draftEmail(lead.id, contactId);
            await fetchLeadDetail();
            setActiveSubTab('emails');
        } catch (error) {
            console.error('Draft email failed:', error);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleAddManualContact = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!lead || !newContact.name) return;
        setIsProcessing(true);
        try {
            await leadsAgent.addContact(lead.id, {
                ...newContact,
                is_primary: lead.contacts.length === 0 // Set as primary if it's the first one
            });
            setNewContact({ name: '', title: '', email: '', linkedin_url: '' });
            setIsAddingContact(false);
            await fetchLeadDetail();
        } catch (error) {
            console.error('Add contact failed:', error);
        } finally {
            setIsProcessing(false);
        }
    };

    if (!leadId) return null;

    return (
        <div className={`fixed inset-y-0 right-0 w-full max-w-2xl bg-zinc-950 border-l border-zinc-800 shadow-2xl z-50 transform transition-transform duration-300 ${leadId ? 'translate-x-0' : 'translate-x-full'}`}>
            <div className="flex flex-col h-full">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-zinc-800">
                    <div className="space-y-1">
                        <h2 className="text-lg font-bold text-white tracking-tight">{lead?.title || 'Loading...'}</h2>
                        <div className="text-sm text-zinc-500">{lead?.company_name}</div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-zinc-900 rounded-lg transition-colors text-zinc-400">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto">
                    {isLoading ? (
                        <div className="flex items-center justify-center h-40">
                            <div className="w-2 h-2 rounded-full bg-white animate-ping" />
                        </div>
                    ) : lead ? (
                        <div className="p-6 space-y-8">
                            {/* Quick Actions & Status */}
                            <div className="flex flex-wrap items-center gap-4">
                                <div className="space-y-1.5">
                                    <label className="text-[10px] uppercase tracking-widest text-zinc-600 block">Status</label>
                                    <select
                                        value={lead.status}
                                        onChange={(e) => handleUpdateStatus(e.target.value as LeadStatus)}
                                        className="bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-zinc-700"
                                    >
                                        {['new', 'staging', 'draft_ready', 'approved', 'contacted', 'closed'].map(s => (
                                            <option key={s} value={s}>{s.replace('_', ' ')}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="space-y-1.5">
                                    <label className="text-[10px] uppercase tracking-widest text-zinc-600 block">Priority</label>
                                    <div className="flex gap-1">
                                        {(['skip', 'low', 'medium', 'high'] as LeadPriority[]).map(p => (
                                            <button
                                                key={p}
                                                onClick={() => handleUpdatePriority(p)}
                                                className={`px-2 py-1 text-[10px] uppercase border rounded transition-all ${lead.priority === p
                                                    ? 'bg-zinc-300 text-black border-zinc-300'
                                                    : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-700'
                                                    }`}
                                            >
                                                {p}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Tabs */}
                            <div className="border-b border-zinc-900">
                                <div className="flex gap-6">
                                    {(['info', 'contacts', 'emails'] as const).map(tab => (
                                        <button
                                            key={tab}
                                            onClick={() => setActiveSubTab(tab)}
                                            className={`pb-3 text-xs font-bold uppercase tracking-widest transition-all relative ${activeSubTab === tab ? 'text-white' : 'text-zinc-600 hover:text-zinc-400'
                                                }`}
                                        >
                                            {tab}
                                            {activeSubTab === tab && <div className="absolute bottom-0 inset-x-0 h-0.5 bg-white" />}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Tab Content */}
                            <div className="min-h-[300px]">
                                {activeSubTab === 'info' && (
                                    <div className="space-y-6 animate-in fade-in duration-300">
                                        <div className="flex justify-end">
                                            {lead.source_url && (
                                                <a
                                                    href={lead.source_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-emerald-500 hover:text-emerald-400 transition-colors"
                                                >
                                                    View Original Post
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                    </svg>
                                                </a>
                                            )}
                                        </div>

                                        <section>
                                            <h3 className="text-[10px] uppercase tracking-[0.2em] text-white mb-2">Job Description</h3>
                                            <p className="text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap line-clamp-[15] italic">
                                                {lead.job_description || 'No description available'}
                                            </p>
                                        </section>

                                        {lead.gemini_analysis && (
                                            <section className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-xl relative group">
                                                <div className="flex items-center justify-between mb-2">
                                                    <h3 className="text-[10px] uppercase tracking-[0.2em] text-emerald-400/70">Gemini Analysis</h3>
                                                    <button
                                                        onClick={reAnalyze}
                                                        disabled={isProcessing}
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity text-[9px] uppercase font-bold text-emerald-500 hover:text-emerald-400 disabled:opacity-50"
                                                    >
                                                        {isProcessing ? 'Analyzing...' : 'Re-Run Analysis'}
                                                    </button>
                                                </div>
                                                <div className="max-h-60 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-emerald-500/20 scrollbar-track-transparent">
                                                    <p className="text-xs text-zinc-300 whitespace-pre-wrap font-mono">{lead.gemini_analysis.reasoning}</p>
                                                </div>
                                                <div className="grid grid-cols-2 gap-4 mt-4 text-[10px]">
                                                    <div>
                                                        <span className="text-zinc-600 uppercase block mb-1">Seniority</span>
                                                        <span className="text-zinc-300 uppercase">{lead.gemini_analysis.extracted_seniority || 'N/A'}</span>
                                                    </div>
                                                    <div>
                                                        <span className="text-zinc-600 uppercase block mb-1">Domain</span>
                                                        <span className="text-zinc-300">{lead.gemini_analysis.extracted_domain || 'N/A'}</span>
                                                    </div>
                                                </div>
                                            </section>
                                        )}
                                    </div>
                                )}

                                {activeSubTab === 'contacts' && (
                                    <div className="space-y-6 animate-in fade-in duration-300">
                                        <div className="flex items-center justify-between">
                                            <div className="flex flex-col">
                                                <h3 className="text-[10px] uppercase tracking-[0.2em] text-white">Found Contacts</h3>
                                                {message && (
                                                    <span className={`text-[10px] ${message.type === 'success' ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                        {message.text}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="flex gap-4">
                                                <button
                                                    onClick={() => setIsAddingContact(!isAddingContact)}
                                                    className="text-[10px] uppercase tracking-widest text-zinc-500 hover:text-white transition-colors"
                                                >
                                                    {isAddingContact ? 'Cancel' : 'Add Manual'}
                                                </button>
                                                <button
                                                    onClick={researchContact}
                                                    disabled={isProcessing}
                                                    className="text-[10px] uppercase tracking-widest text-amber-500 hover:text-amber-400 disabled:opacity-50 flex items-center gap-2"
                                                >
                                                    {isProcessing ? 'Researching...' : 'Research Web'}
                                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                                                    </svg>
                                                </button>
                                                <button
                                                    onClick={findContacts}
                                                    disabled={isProcessing}
                                                    className="text-[10px] uppercase tracking-widest text-emerald-500 hover:text-emerald-400 disabled:opacity-50"
                                                >
                                                    {isProcessing ? 'Searching...' : 'Search Contacts'}
                                                </button>
                                            </div>
                                        </div>

                                        {isAddingContact && (
                                            <form onSubmit={handleAddManualContact} className="p-4 bg-zinc-900/80 border border-zinc-800 rounded-xl space-y-4 animate-in slide-in-from-top-2 duration-200">
                                                <div className="grid grid-cols-2 gap-4">
                                                    <div className="space-y-1">
                                                        <label className="text-[9px] uppercase tracking-widest text-zinc-600">Name</label>
                                                        <input
                                                            autoFocus
                                                            value={newContact.name}
                                                            onChange={e => setNewContact({...newContact, name: e.target.value})}
                                                            className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500/50"
                                                            placeholder="John Doe"
                                                            required
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <label className="text-[9px] uppercase tracking-widest text-zinc-600">Title</label>
                                                        <input
                                                            value={newContact.title}
                                                            onChange={e => setNewContact({...newContact, title: e.target.value})}
                                                            className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500/50"
                                                            placeholder="CTO"
                                                        />
                                                    </div>
                                                </div>
                                                <div className="grid grid-cols-2 gap-4">
                                                    <div className="space-y-1">
                                                        <label className="text-[9px] uppercase tracking-widest text-zinc-600">Email</label>
                                                        <input
                                                            type="email"
                                                            value={newContact.email}
                                                            onChange={e => setNewContact({...newContact, email: e.target.value})}
                                                            className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500/50"
                                                            placeholder="john@company.com"
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <label className="text-[9px] uppercase tracking-widest text-zinc-600">LinkedIn</label>
                                                        <input
                                                            value={newContact.linkedin_url}
                                                            onChange={e => setNewContact({...newContact, linkedin_url: e.target.value})}
                                                            className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs text-white focus:outline-none focus:border-emerald-500/50"
                                                            placeholder="linkedin.com/in/..."
                                                        />
                                                    </div>
                                                </div>
                                                <div className="flex justify-end gap-3 pt-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => setIsAddingContact(false)}
                                                        className="text-[10px] uppercase font-bold text-zinc-600 hover:text-zinc-400"
                                                    >
                                                        Cancel
                                                    </button>
                                                    <button
                                                        type="submit"
                                                        disabled={isProcessing}
                                                        className="px-3 py-1 bg-white text-black text-[10px] font-bold uppercase rounded hover:bg-zinc-200 disabled:opacity-50"
                                                    >
                                                        {isProcessing ? 'Adding...' : 'Add Contact'}
                                                    </button>
                                                </div>
                                            </form>
                                        )}

                                        <div className="space-y-3">
                                            {lead.contacts.map(contact => (
                                                <div key={contact.id} className={`p-4 bg-zinc-900/50 border rounded-xl ${contact.is_primary ? 'border-emerald-500/30' : 'border-zinc-800'}`}>
                                                    <div className="flex items-start justify-between">
                                                        <div className="space-y-1">
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-xs font-bold text-white">{contact.name}</span>
                                                                {contact.is_primary ? (
                                                                    <span className="text-[8px] bg-emerald-500/10 text-emerald-500 px-1 py-0.5 rounded border border-emerald-500/20 font-bold uppercase">Primary</span>
                                                                ) : (
                                                                    <span className={`text-[8px] px-1 py-0.5 rounded border font-bold uppercase ${
                                                                        contact.source === 'ai_research' 
                                                                            ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' 
                                                                            : 'bg-zinc-800 text-zinc-500 border-zinc-700'
                                                                    }`}>
                                                                        {contact.source || 'Manual'}
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <div className="text-[10px] text-zinc-500">{contact.title || 'Executive'}</div>
                                                            <div className="text-[10px] text-zinc-400 mt-1">{contact.email || '(No email found yet)'}</div>
                                                            {contact.email_confidence && (
                                                                <div className="flex items-center gap-2 mt-2">
                                                                    <div className="flex-1 max-w-[60px] h-1 bg-zinc-800 rounded-full overflow-hidden">
                                                                        <div className="h-full bg-emerald-500/50" style={{ width: `${contact.email_confidence}%` }} />
                                                                    </div>
                                                                    <span className="text-[8px] text-zinc-600">Conf: {contact.email_confidence}%</span>
                                                                </div>
                                                            )}
                                                        </div>
                                                        <div className="flex flex-col gap-2">
                                                            {!contact.is_primary && (
                                                                <button
                                                                    onClick={() => setPrimary(contact.id)}
                                                                    className="px-3 py-1 bg-zinc-800 text-zinc-300 text-[9px] font-bold uppercase rounded hover:bg-zinc-700 border border-zinc-700 transition-colors"
                                                                >
                                                                    Set Primary
                                                                </button>
                                                            )}
                                                            {contact.email && (
                                                                <button
                                                                    onClick={() => draftEmail(contact.id)}
                                                                    className="px-3 py-1 bg-white text-black text-[9px] font-bold uppercase rounded hover:bg-zinc-200 transition-colors"
                                                                >
                                                                    Draft Email
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                    {contact.is_primary && contact.gemini_ranking_reason && (
                                                        <div className="mt-3 pt-3 border-t border-zinc-800 text-[9px] text-zinc-500 italic">
                                                            {contact.gemini_ranking_reason}
                                                        </div>
                                                    )}
                                                </div>
                                            ))}

                                            {lead.contacts.length === 0 && (
                                                <div className="text-center py-10 border border-dashed border-zinc-900 rounded-xl">
                                                    <p className="text-[10px] text-zinc-700 uppercase tracking-widest">No contacts found yet</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {activeSubTab === 'emails' && (
                                    <div className="space-y-6 animate-in fade-in duration-300">
                                        <div className="flex items-center justify-between">
                                            <h3 className="text-[10px] uppercase tracking-[0.2em] text-white">Email Drafts</h3>
                                            <button
                                                onClick={() => {
                                                    const primaryContact = lead.contacts.find(c => c.is_primary);
                                                    if (primaryContact) {
                                                        draftEmail(primaryContact.id);
                                                    } else if (lead.contacts.length > 0) {
                                                        // Fallback to first contact if no primary
                                                        draftEmail(lead.contacts[0].id);
                                                    } else {
                                                        // Draft without a contact (use placeholders)
                                                        draftEmail(undefined);
                                                    }
                                                }}
                                                disabled={isProcessing}
                                                className="text-[10px] uppercase tracking-widest text-emerald-500 hover:text-emerald-400 disabled:opacity-50 flex items-center gap-2"
                                            >
                                                {isProcessing ? 'Drafting...' : 'Auto Draft'}
                                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                                                </svg>
                                            </button>
                                        </div>
                                        <div className="space-y-4">
                                            {lead.emails.map(email => (
                                                <div key={email.id} className="p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl">
                                                    <div className="flex items-center justify-between mb-3 pb-3 border-b border-zinc-800">
                                                        <span className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded uppercase font-bold tracking-widest">{email.status}</span>
                                                        <span className="text-[9px] text-zinc-600">{new Date(email.created_at).toLocaleString()}</span>
                                                    </div>
                                                    <div className="text-xs font-bold text-white mb-2">Subject: {email.subject}</div>
                                                    <div className="text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed italic border-l border-zinc-800 pl-4 py-2">
                                                        {email.body}
                                                    </div>
                                                </div>
                                            ))}

                                            {lead.emails.length === 0 && (
                                                <div className="text-center py-10 border border-dashed border-zinc-900 rounded-xl">
                                                    <p className="text-[10px] text-zinc-700 uppercase tracking-widest">No emails drafted yet</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center justify-center py-20">
                            <p className="text-sm text-zinc-500">Lead not found</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
