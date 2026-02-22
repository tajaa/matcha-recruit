import { useEffect, useState } from 'react';
import { FileText, Search, AlertCircle, ChevronRight, X, ExternalLink } from 'lucide-react';
import { portalApi } from '../../api/portal';

interface Policy {
  id: string;
  title: string;
  description: string | null;
  content: string | null;
  file_url: string | null;
  version: string;
  created_at: string | null;
}

export function PortalPolicies() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [fullPolicy, setFullPolicy] = useState<Policy | null>(null);
  const [loadingPolicy, setLoadingPolicy] = useState(false);

  const fetchPolicies = async (query?: string) => {
    try {
      setLoading(true);
      const data = await portalApi.searchPolicies(query);
      setPolicies(data.policies);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load policies');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchPolicies(searchQuery);
  };

  const handleViewPolicy = async (policy: Policy) => {
    setSelectedPolicy(policy);
    setLoadingPolicy(true);
    try {
      const data = await portalApi.getPolicy(policy.id);
      setFullPolicy(data);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to load policy');
      setSelectedPolicy(null);
    } finally {
      setLoadingPolicy(false);
    }
  };

  if (loading && policies.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-white/10 pb-6">
        <h1 className="text-2xl font-bold tracking-tight text-white uppercase">Company Policies</h1>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">Search and view company policies</p>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search policies..."
            className="w-full pl-12 pr-4 py-3 bg-zinc-900 border border-zinc-800 text-white text-sm focus:border-white transition-colors outline-none font-mono"
          />
        </div>
        <button
          type="submit"
          className="px-8 py-3 bg-white text-black text-[10px] uppercase tracking-widest font-bold border border-white hover:bg-zinc-200 transition-colors"
        >
          Search
        </button>
      </form>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400 font-mono text-sm uppercase">{error}</span>
        </div>
      )}

      {/* Policies List */}
      <div className="bg-zinc-900/30 border border-white/10 divide-y divide-white/5">
        {policies.length === 0 ? (
          <div className="p-16 text-center">
            <FileText className="w-12 h-12 mx-auto text-zinc-700 mb-4 opacity-50" />
            <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">No policies found</p>
          </div>
        ) : (
          policies.map((policy) => (
            <button
              key={policy.id}
              onClick={() => handleViewPolicy(policy)}
              className="w-full p-6 flex items-center justify-between hover:bg-white/5 transition-colors text-left group"
            >
              <div className="flex items-center gap-5">
                <div className="w-10 h-10 border border-white/10 bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
                  <FileText className="w-4 h-4 text-zinc-500 group-hover:text-white transition-colors" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white tracking-tight">{policy.title}</h3>
                  {policy.description && (
                    <p className="text-[11px] text-zinc-500 mt-1 line-clamp-2 max-w-2xl leading-relaxed">{policy.description}</p>
                  )}
                  <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest mt-2 inline-block">
                    Version {policy.version}
                  </span>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
            </button>
          ))
        )}
      </div>

      {/* Policy Detail Modal */}
      {selectedPolicy && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-950 border border-white/10 w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="px-8 py-6 border-b border-white/10 bg-white/5 flex items-center justify-between flex-shrink-0">
              <div>
                <h2 className="text-lg font-bold text-white uppercase tracking-tight">{selectedPolicy.title}</h2>
                <span className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">Version {selectedPolicy.version}</span>
              </div>
              <button
                onClick={() => {
                  setSelectedPolicy(null);
                  setFullPolicy(null);
                }}
                className="p-1 hover:bg-white/5 transition-colors"
              >
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>
            <div className="p-8 overflow-y-auto">
              {loadingPolicy ? (
                <div className="flex items-center justify-center py-24">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
                    <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading Policy Content</span>
                  </div>
                </div>
              ) : fullPolicy ? (
                <div className="space-y-8">
                  {fullPolicy.description && (
                    <p className="text-sm text-zinc-400 leading-relaxed font-mono uppercase tracking-wide">{fullPolicy.description}</p>
                  )}

                  {/* Document link - shown prominently when available */}
                  {fullPolicy.file_url && (
                    <a
                      href={fullPolicy.file_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-5 p-6 bg-white/5 border border-dashed border-white/10 hover:border-white/30 hover:bg-white/10 transition-colors group"
                    >
                      <div className="w-10 h-10 border border-white/10 bg-zinc-950 flex items-center justify-center">
                        <FileText size={18} className="text-zinc-500 group-hover:text-white transition-colors" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] font-bold text-white uppercase tracking-widest group-hover:text-white transition-colors">View Policy Document</div>
                        <div className="text-[9px] text-zinc-500 font-mono truncate mt-1">
                          {fullPolicy.file_url.split('/').pop()}
                        </div>
                      </div>
                      <ExternalLink size={14} className="text-zinc-600 group-hover:text-white transition-colors" />
                    </a>
                  )}

                  {/* Text content - secondary when document exists */}
                  {fullPolicy.content && (
                    <div className="pt-4 border-t border-white/5">
                      {fullPolicy.file_url && (
                        <h3 className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-4 ml-1">Additional Policy Details</h3>
                      )}
                      <div className="prose prose-invert max-w-none">
                        <div className="whitespace-pre-wrap text-sm text-zinc-300 leading-relaxed font-sans">{fullPolicy.content}</div>
                      </div>
                    </div>
                  )}

                  {/* Empty state */}
                  {!fullPolicy.file_url && !fullPolicy.content && (
                    <p className="text-zinc-600 italic font-mono text-xs uppercase tracking-widest text-center py-12">No detailed content available for this policy version</p>
                  )}
                </div>
              ) : null}
            </div>
            <div className="p-6 border-t border-white/10 bg-zinc-900/50 flex justify-end">
                <button
                    onClick={() => {
                        setSelectedPolicy(null);
                        setFullPolicy(null);
                    }}
                    className="px-8 py-2 bg-white text-black text-[10px] font-bold uppercase tracking-widest border border-white hover:bg-zinc-200 transition-colors"
                >
                    Close
                </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PortalPolicies;
