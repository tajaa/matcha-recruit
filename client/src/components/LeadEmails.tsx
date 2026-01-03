import { useState, useEffect } from 'react';
import { leadsAgent } from '../api/client';
import type { LeadEmail, EmailStatus } from '../types/leads';

export default function LeadEmails() {
    const [emails, setEmails] = useState<LeadEmail[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [filter, setFilter] = useState<EmailStatus | 'all'>('all');

    const fetchEmails = async () => {
        setIsLoading(true);
        try {
            const response = await leadsAgent.listEmails(filter === 'all' ? undefined : filter);
            setEmails(response);
        } catch (error) {
            console.error('Failed to fetch emails:', error);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchEmails();
    }, [filter]);

    const handleApprove = async (id: string) => {
        try {
            await leadsAgent.approveEmail(id);
            fetchEmails();
        } catch (error) {
            console.error('Approve failed:', error);
        }
    };

    const handleSend = async (id: string) => {
        try {
            await leadsAgent.sendEmail(id);
            fetchEmails();
        } catch (error) {
            console.error('Send failed:', error);
        }
    };

    const getStatusColor = (status: EmailStatus) => {
        switch (status) {
            case 'sent': return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
            case 'approved': return 'text-amber-500 bg-amber-500/10 border-amber-500/20';
            case 'draft': return 'text-zinc-500 bg-zinc-500/10 border-zinc-500/20';
            case 'replied': return 'text-indigo-500 bg-indigo-500/10 border-indigo-500/20';
            case 'bounced': return 'text-rose-500 bg-rose-500/10 border-rose-500/20';
            default: return 'text-zinc-500 bg-zinc-500/10 border-zinc-500/20';
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">Email Outreach</h2>
                <div className="flex gap-2">
                    {(['all', 'draft', 'approved', 'sent'] as const).map(f => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`px-3 py-1 rounded text-[10px] uppercase tracking-wider border transition-all ${filter === f
                                    ? 'bg-white text-black border-white'
                                    : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-700'
                                }`}
                        >
                            {f}
                        </button>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-1 gap-4">
                {isLoading ? (
                    <div className="flex items-center justify-center py-20">
                        <div className="w-2 h-2 rounded-full bg-white animate-ping" />
                    </div>
                ) : emails.length > 0 ? (
                    emails.map(email => (
                        <div key={email.id} className="p-6 bg-zinc-900/40 border border-zinc-800 rounded-xl space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <span className={`px-2 py-0.5 rounded border text-[8px] font-bold uppercase tracking-widest ${getStatusColor(email.status)}`}>
                                        {email.status}
                                    </span>
                                    <span className="text-[10px] text-zinc-500 font-mono">
                                        {new Date(email.created_at).toLocaleString()}
                                    </span>
                                </div>
                                <div className="flex gap-2">
                                    {email.status === 'draft' && (
                                        <button
                                            onClick={() => handleApprove(email.id)}
                                            className="px-3 py-1 bg-zinc-800 hover:bg-zinc-700 text-white text-[9px] font-bold uppercase rounded border border-zinc-700 transition-colors"
                                        >
                                            Approve
                                        </button>
                                    )}
                                    {email.status === 'approved' && (
                                        <button
                                            onClick={() => handleSend(email.id)}
                                            className="px-3 py-1 bg-white hover:bg-zinc-100 text-black text-[9px] font-bold uppercase rounded transition-colors"
                                        >
                                            Send Now
                                        </button>
                                    )}
                                </div>
                            </div>

                            <div>
                                <h4 className="text-sm font-bold text-white mb-2">{email.subject}</h4>
                                <div className="p-4 bg-zinc-950 rounded-lg text-xs text-zinc-400 leading-relaxed whitespace-pre-wrap italic border-l-2 border-zinc-800">
                                    {email.body}
                                </div>
                            </div>

                            <div className="flex items-center gap-6 pt-2 text-[9px] text-zinc-600 uppercase tracking-widest font-bold">
                                {email.sent_at && (
                                    <div className="flex items-center gap-1.5">
                                        <div className="w-1 h-1 rounded-full bg-emerald-500" />
                                        Sent {new Date(email.sent_at).toLocaleDateString()}
                                    </div>
                                )}
                                {email.opened_at && (
                                    <div className="flex items-center gap-1.5 text-emerald-500">
                                        <div className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
                                        Opened
                                    </div>
                                )}
                                {email.replied_at && (
                                    <div className="flex items-center gap-1.5 text-indigo-500">
                                        <div className="w-1 h-1 rounded-full bg-indigo-500 animate-pulse" />
                                        Replied
                                    </div>
                                )}
                            </div>
                        </div>
                    ))
                ) : (
                    <div className="text-center py-20 border border-dashed border-zinc-900 rounded-xl">
                        <p className="text-[10px] text-zinc-700 uppercase tracking-widest">No emails found</p>
                    </div>
                )}
            </div>
        </div>
    );
}
