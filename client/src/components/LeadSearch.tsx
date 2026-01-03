import { useState } from 'react';
import { leadsAgent } from '../api/client';
import type { SearchRequest, SearchResult } from '../types/leads';

const INDUSTRY_OPTIONS = [
    'Technology', 'Finance', 'Healthcare', 'Manufacturing', 'Retail',
    'Energy', 'Real Estate', 'Transportation', 'Entertainment', 'Education',
    'AI/ML', 'SaaS', 'Fintech', 'Healthtech', 'Sustainability', 'Logistics'
];

const SALARY_STEPS = Array.from({ length: 22 }, (_, i) => 80000 + (i * 20000));

export default function LeadSearch({ onSearchComplete }: { onSearchComplete: () => void }) {
    const [roleTypes, setRoleTypes] = useState<string[]>(['Chief Executive Officer', 'VP Engineering', 'CTO', 'Head of Sales']);
    const [locations, setLocations] = useState<string[]>(['San Francisco', 'New York', 'Remote']);
    const [industries, setIndustries] = useState<string[]>(['Technology']);
    const [salaryMin, setSalaryMin] = useState<number>(200000);
    const [isSearching, setIsSearching] = useState(false);
    const [searchResult, setSearchResult] = useState<SearchResult | null>(null);

    const toggleRole = (role: string) => {
        setRoleTypes(prev =>
            prev.includes(role) ? prev.filter(r => r !== role) : [...prev, role]
        );
    };

    const toggleIndustry = (industry: string) => {
        setIndustries(prev =>
            prev.includes(industry) ? prev.filter(i => i !== industry) : [...prev, industry]
        );
    };

    const handleSearch = async (preview: boolean = false) => {
        setIsSearching(true);
        setSearchResult(null);
        try {
            const request: SearchRequest = {
                role_types: roleTypes,
                locations: locations,
                industries: industries,
                salary_min: salaryMin,
            };

            const response = await leadsAgent.search({ ...request, preview });
            setSearchResult(response);
            if (!preview) {
                onSearchComplete();
            }
        } catch (error) {
            console.error('Search failed:', error);
            alert('Search failed. Please check backend logs.');
        } finally {
            setIsSearching(false);
        }
    };

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Search Configuration */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <div className="space-y-6">
                    <section>
                        <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-4 px-1">Target Roles</h3>
                        <div className="flex flex-wrap gap-2">
                            {['Chief Executive Officer', 'CTO', 'CFO', 'CMO', 'COO', 'VP Engineering', 'VP Sales', 'VP of People', 'CHRO', 'Head of HR', 'Director'].map(role => (
                                <button
                                    key={role}
                                    onClick={() => toggleRole(role)}
                                    className={`px-3 py-1.5 rounded text-[10px] uppercase tracking-wider border transition-all ${roleTypes.includes(role)
                                        ? 'bg-white text-black border-white'
                                        : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-700'
                                        }`}
                                >
                                    {role}
                                </button>
                            ))}
                        </div>
                    </section>

                    <section>
                        <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-4 px-1">Locations</h3>
                        <div className="relative">
                            <input
                                type="text"
                                placeholder="Add location (e.g. London)..."
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && e.currentTarget.value) {
                                        setLocations([...locations, e.currentTarget.value]);
                                        e.currentTarget.value = '';
                                    }
                                }}
                                className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-xs text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-700 transition-colors"
                            />
                        </div>
                        <div className="flex flex-wrap gap-2 mt-3">
                            {locations.map(loc => (
                                <span key={loc} className="flex items-center gap-2 px-2 py-1 bg-zinc-800/50 border border-zinc-700 rounded text-[10px] text-zinc-400">
                                    {loc}
                                    <button onClick={() => setLocations(locations.filter(l => l !== loc))} className="hover:text-white transition-colors">
                                        ×
                                    </button>
                                </span>
                            ))}
                        </div>
                    </section>
                </div>

                <div className="space-y-6">
                    <section>
                        <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-4 px-1">Industries</h3>
                        <div className="flex flex-wrap gap-2">
                            {INDUSTRY_OPTIONS.map(industry => (
                                <button
                                    key={industry}
                                    onClick={() => toggleIndustry(industry)}
                                    className={`px-3 py-1.5 rounded text-[10px] uppercase tracking-wider border transition-all ${industries.includes(industry)
                                        ? 'bg-zinc-100 text-black border-zinc-100'
                                        : 'bg-zinc-900 text-zinc-500 border-zinc-800 hover:border-zinc-700'
                                        }`}
                                >
                                    {industry}
                                </button>
                            ))}
                        </div>
                    </section>

                    <section>
                        <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 mb-4 px-1">Min Salary ($)</h3>
                        <select
                            value={salaryMin}
                            onChange={(e) => setSalaryMin(parseInt(e.target.value))}
                            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-2 text-xs text-zinc-300 focus:outline-none focus:border-zinc-700 transition-colors appearance-none cursor-pointer"
                        >
                            {SALARY_STEPS.map(step => (
                                <option key={step} value={step}>
                                    ${step.toLocaleString()}
                                </option>
                            ))}
                            <option value={500000}>$500,000+</option>
                        </select>
                    </section>

                    <div className="flex items-center gap-4 pt-4">
                        <button
                            onClick={() => handleSearch(true)}
                            disabled={isSearching}
                            className="flex-1 px-4 py-3 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 text-[10px] font-bold uppercase tracking-[0.2em] border border-zinc-800 rounded-lg transition-all disabled:opacity-50"
                        >
                            {isSearching ? 'Processing...' : 'Preview Search'}
                        </button>
                        <button
                            onClick={() => handleSearch(false)}
                            disabled={isSearching}
                            className="flex-1 px-4 py-3 bg-white hover:bg-zinc-100 text-black text-[10px] font-bold uppercase tracking-[0.2em] rounded-lg transition-all disabled:opacity-50"
                        >
                            {isSearching ? 'Processing...' : 'Run & Save Leads'}
                        </button>
                    </div>
                </div>
            </div>

            {/* Results Preview */}
            {searchResult && (
                <div className="space-y-6 pt-8 border-t border-zinc-900">
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-bold text-white tracking-widest uppercase flex items-center gap-3">
                            Search Results
                            <span className="text-[10px] font-normal text-zinc-500 normal-case tracking-normal">
                                Found {searchResult.jobs_found} jobs, {searchResult.jobs_qualified} qualified
                            </span>
                        </h2>
                        <div className="flex gap-4">
                            <div className="text-right">
                                <div className="text-[10px] text-zinc-500 uppercase tracking-tighter">Created</div>
                                <div className="text-xs text-emerald-500 font-bold">{searchResult.leads_created}</div>
                            </div>
                            <div className="text-right">
                                <div className="text-[10px] text-zinc-500 uppercase tracking-tighter">Deduped</div>
                                <div className="text-xs text-zinc-500 font-bold">{searchResult.leads_deduplicated}</div>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 gap-4">
                        {searchResult.jobs_found > 0 && searchResult.jobs_qualified === 0 && (
                            <div className="p-8 border border-dashed border-zinc-800 rounded-xl bg-zinc-900/20 text-center">
                                <p className="text-xs text-zinc-500">
                                    Jobs were found, but none met the minimum qualification threshold (5/10) to be saved as leads.
                                    <br />
                                    <span className="text-[10px] opacity-60 mt-1 block">Try broadening your role types or reducing the minimum salary.</span>
                                </p>
                            </div>
                        )}
                        {searchResult.items.map((item, idx) => (
                            <div
                                key={idx}
                                className={`p-4 rounded-xl border transition-all ${item.gemini_analysis?.is_qualified
                                    ? 'bg-zinc-900/40 border-zinc-800 group hover:border-zinc-700'
                                    : 'bg-zinc-950 border-zinc-900 opacity-50 grayscale'
                                    }`}
                            >
                                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-3">
                                            <h4 className="text-sm font-bold text-white">{item.title}</h4>
                                            {item.gemini_analysis?.is_qualified && (
                                                <span className="px-1.5 py-0.5 bg-emerald-500/10 text-emerald-500 text-[8px] font-bold uppercase tracking-widest rounded border border-emerald-500/20">
                                                    Qualified {item.gemini_analysis.relevance_score}/10
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-xs text-zinc-400 font-medium">
                                            {item.company_name} • {item.location || 'Remote'}
                                        </div>
                                        {item.salary_text && (
                                            <div className="text-[10px] text-zinc-500 italic mt-1">{item.salary_text}</div>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2 self-end md:self-start">
                                        {item.source_url && (
                                            <a
                                                href={item.source_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="p-2 bg-zinc-800 text-zinc-400 hover:text-white rounded-lg transition-colors border border-zinc-700"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                                </svg>
                                            </a>
                                        )}
                                    </div>
                                </div>

                                {item.gemini_analysis && (
                                    <div className="mt-4 pt-4 border-t border-zinc-800/50">
                                        <p className="text-[10px] text-zinc-500 italic leading-relaxed">
                                            <span className="text-zinc-400 font-bold not-italic mr-1">Gemini AI:</span>
                                            {item.gemini_analysis.reasoning}
                                        </p>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
