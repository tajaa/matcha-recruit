import { useEffect, useState } from 'react';
import { FileText, CheckCircle, Clock, AlertCircle, X } from 'lucide-react';
import { FeatureGuideTrigger } from '../../features/feature-guides';
import { portalApi } from '../../api/portal';

interface Document {
  id: string;
  doc_type: string;
  title: string;
  description: string | null;
  status: string;
  expires_at: string | null;
  signed_at: string | null;
  created_at: string;
}

export function PortalDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('');
  const [signingDoc, setSigningDoc] = useState<Document | null>(null);
  const [signatureName, setSignatureName] = useState('');
  const [signing, setSigning] = useState(false);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const data = await portalApi.getDocuments(filter || undefined);
      setDocuments(data.documents);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, [filter]);

  const handleSign = async () => {
    if (!signingDoc || !signatureName.trim()) return;

    setSigning(true);
    try {
      await portalApi.signDocument(signingDoc.id, signatureName);
      setSigningDoc(null);
      setSignatureName('');
      fetchDocuments();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to sign document');
    } finally {
      setSigning(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending_signature':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[9px] uppercase tracking-widest font-bold">
            <Clock className="w-3 h-3 mr-1.5" /> Pending Signature
          </span>
        );
      case 'signed':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[9px] uppercase tracking-widest font-bold">
            <CheckCircle className="w-3 h-3 mr-1.5" /> Signed
          </span>
        );
      case 'expired':
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-red-500/10 text-red-400 border border-red-500/20 text-[9px] uppercase tracking-widest font-bold">
            <AlertCircle className="w-3 h-3 mr-1.5" /> Expired
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-1 bg-zinc-500/10 text-zinc-400 border border-zinc-500/20 text-[9px] uppercase tracking-widest font-bold">
            {status}
          </span>
        );
    }
  };

  if (loading && documents.length === 0) {
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
      <div className="flex items-center justify-between border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white uppercase">My Documents</h1>
            <FeatureGuideTrigger guideId="portal-documents" variant="light" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">View and sign assigned documents</p>
        </div>
      </div>

      {/* Filters */}
      <div data-tour="portal-docs-filters" className="flex items-center gap-3 bg-zinc-900/50 p-1 border border-white/5 w-fit">
        <button
          onClick={() => setFilter('')}
          className={`px-6 py-2 text-[10px] uppercase tracking-widest font-bold transition-all ${
            filter === '' ? 'bg-white text-black' : 'text-zinc-500 hover:text-white'
          }`}
        >
          All
        </button>
        <button
          onClick={() => setFilter('pending_signature')}
          className={`px-6 py-2 text-[10px] uppercase tracking-widest font-bold transition-all ${
            filter === 'pending_signature' ? 'bg-white text-black' : 'text-zinc-500 hover:text-white'
          }`}
        >
          Pending
        </button>
        <button
          onClick={() => setFilter('signed')}
          className={`px-6 py-2 text-[10px] uppercase tracking-widest font-bold transition-all ${
            filter === 'signed' ? 'bg-white text-black' : 'text-zinc-500 hover:text-white'
          }`}
        >
          Signed
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400 font-mono text-sm uppercase">{error}</span>
        </div>
      )}

      {/* Documents List */}
      <div data-tour="portal-docs-list" className="bg-zinc-900/30 border border-white/10 divide-y divide-white/5">
        {documents.length === 0 ? (
          <div className="p-16 text-center">
            <FileText className="w-12 h-12 mx-auto text-zinc-700 mb-4 opacity-50" />
            <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">No documents found</p>
          </div>
        ) : (
          documents.map((doc) => (
            <div key={doc.id} className="p-6 hover:bg-white/5 transition-colors group">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-5">
                  <div className="w-10 h-10 border border-white/10 bg-white/5 flex items-center justify-center group-hover:bg-white/10 transition-colors">
                    <FileText className="w-4 h-4 text-zinc-500 group-hover:text-white transition-colors" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white tracking-tight">{doc.title}</h3>
                    {doc.description && (
                      <p className="text-[11px] text-zinc-500 mt-1 max-w-2xl leading-relaxed">{doc.description}</p>
                    )}
                    <div className="flex items-center gap-4 mt-3">
                      <span className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest border border-white/5 px-1.5 py-0.5">
                        {doc.doc_type}
                      </span>
                      {doc.expires_at && (
                        <span className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">
                          Expires: {new Date(doc.expires_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div data-tour="portal-docs-status" className="flex items-center gap-4">
                  {getStatusBadge(doc.status)}
                  {doc.status === 'pending_signature' && (
                    <button
                      data-tour="portal-docs-sign-btn"
                      onClick={() => setSigningDoc(doc)}
                      className="px-8 py-2 bg-white text-black text-[10px] uppercase tracking-widest font-bold border border-white hover:bg-zinc-200 transition-colors"
                    >
                      Sign
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Sign Modal */}
      {signingDoc && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-950 border border-white/10 p-8 w-full max-w-md animate-in fade-in zoom-in duration-200 shadow-2xl">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-lg font-bold text-white uppercase tracking-tight">Sign Document</h2>
              <button
                onClick={() => setSigningDoc(null)}
                className="p-1 hover:bg-white/5 transition-colors"
              >
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>
            <div className="mb-8">
              <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono mb-6 leading-relaxed">
                By typing your name below, you agree to legally sign <span className="text-white font-bold">"{signingDoc.title}"</span>.
              </p>
              <label className="block text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-2 ml-1">
                Type your full legal name
              </label>
              <input
                type="text"
                value={signatureName}
                onChange={(e) => setSignatureName(e.target.value)}
                placeholder="Enter your full name"
                className="w-full bg-zinc-900 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
              />
            </div>
            <div className="flex gap-4">
              <button
                onClick={() => setSigningDoc(null)}
                className="flex-1 px-4 py-3 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSign}
                disabled={!signatureName.trim() || signing}
                className="flex-1 px-4 py-3 bg-white text-black text-[10px] font-bold uppercase tracking-widest border border-white hover:bg-zinc-200 transition-colors disabled:opacity-50"
              >
                {signing ? 'Signing...' : 'Sign Document'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PortalDocuments;
