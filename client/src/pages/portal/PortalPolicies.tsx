import { useEffect, useState } from 'react';
import { FileText, Search, AlertCircle, ChevronRight, X } from 'lucide-react';
import { portalApi } from '../../api/portal';

interface Policy {
  id: string;
  title: string;
  description: string | null;
  content: string | null;
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
          <div className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-mono font-medium text-zinc-900">Company Policies</h1>
        <p className="text-sm text-zinc-500 mt-1">Search and view company policies</p>
      </div>

      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search policies..."
            className="w-full pl-12 pr-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
          />
        </div>
        <button
          type="submit"
          className="px-6 py-3 bg-zinc-900 text-white font-medium rounded-lg hover:bg-zinc-800 transition-colors"
        >
          Search
        </button>
      </form>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error}</span>
        </div>
      )}

      {/* Policies List */}
      <div className="bg-white border border-zinc-200 rounded-lg">
        {policies.length === 0 ? (
          <div className="p-8 text-center text-zinc-500">
            <FileText className="w-12 h-12 mx-auto text-zinc-300 mb-3" />
            <p>No policies found</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-100">
            {policies.map((policy) => (
              <button
                key={policy.id}
                onClick={() => handleViewPolicy(policy)}
                className="w-full p-5 flex items-center justify-between hover:bg-zinc-50 transition-colors text-left"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5 text-zinc-600" />
                  </div>
                  <div>
                    <h3 className="font-medium text-zinc-900">{policy.title}</h3>
                    {policy.description && (
                      <p className="text-sm text-zinc-500 mt-1 line-clamp-2">{policy.description}</p>
                    )}
                    <span className="text-xs text-zinc-400 font-mono mt-1 inline-block">
                      Version {policy.version}
                    </span>
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-zinc-400 flex-shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Policy Detail Modal */}
      {selectedPolicy && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl w-full max-w-2xl max-h-[80vh] mx-4 overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-zinc-100 flex items-center justify-between flex-shrink-0">
              <div>
                <h2 className="text-lg font-medium text-zinc-900">{selectedPolicy.title}</h2>
                <span className="text-xs text-zinc-400 font-mono">Version {selectedPolicy.version}</span>
              </div>
              <button
                onClick={() => {
                  setSelectedPolicy(null);
                  setFullPolicy(null);
                }}
                className="p-1 hover:bg-zinc-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto">
              {loadingPolicy ? (
                <div className="flex items-center justify-center py-12">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse" />
                    <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
                  </div>
                </div>
              ) : fullPolicy ? (
                <div>
                  {fullPolicy.description && (
                    <p className="text-zinc-600 mb-4">{fullPolicy.description}</p>
                  )}
                  <div className="prose prose-zinc max-w-none">
                    {fullPolicy.content ? (
                      <div className="whitespace-pre-wrap text-sm text-zinc-700">{fullPolicy.content}</div>
                    ) : (
                      <p className="text-zinc-500 italic">No content available</p>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PortalPolicies;
