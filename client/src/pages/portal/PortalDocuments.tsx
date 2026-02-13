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
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
            <Clock className="w-3 h-3" /> Pending Signature
          </span>
        );
      case 'signed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle className="w-3 h-3" /> Signed
          </span>
        );
      case 'expired':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <AlertCircle className="w-3 h-3" /> Expired
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-zinc-100 text-zinc-800">
            {status}
          </span>
        );
    }
  };

  if (loading && documents.length === 0) {
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
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-mono font-medium text-zinc-900">My Documents</h1>
            <FeatureGuideTrigger guideId="portal-documents" variant="light" />
          </div>
          <p className="text-sm text-zinc-500 mt-1">View and sign assigned documents</p>
        </div>
      </div>

      {/* Filters */}
      <div data-tour="portal-docs-filters" className="flex gap-2">
        <button
          onClick={() => setFilter('')}
          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
            filter === '' ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'
          }`}
        >
          All
        </button>
        <button
          onClick={() => setFilter('pending_signature')}
          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
            filter === 'pending_signature'
              ? 'bg-zinc-900 text-white'
              : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'
          }`}
        >
          Pending
        </button>
        <button
          onClick={() => setFilter('signed')}
          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
            filter === 'signed' ? 'bg-zinc-900 text-white' : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'
          }`}
        >
          Signed
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error}</span>
        </div>
      )}

      {/* Documents List */}
      <div data-tour="portal-docs-list" className="bg-white border border-zinc-200 rounded-lg divide-y divide-zinc-100">
        {documents.length === 0 ? (
          <div className="p-8 text-center text-zinc-500">
            <FileText className="w-12 h-12 mx-auto text-zinc-300 mb-3" />
            <p>No documents found</p>
          </div>
        ) : (
          documents.map((doc) => (
            <div key={doc.id} className="p-5 hover:bg-zinc-50 transition-colors">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-zinc-100 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5 text-zinc-600" />
                  </div>
                  <div>
                    <h3 className="font-medium text-zinc-900">{doc.title}</h3>
                    {doc.description && (
                      <p className="text-sm text-zinc-500 mt-1">{doc.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-2">
                      <span className="text-xs text-zinc-400 font-mono uppercase">
                        {doc.doc_type}
                      </span>
                      {doc.expires_at && (
                        <span className="text-xs text-zinc-400">
                          Expires: {new Date(doc.expires_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div data-tour="portal-docs-status" className="flex items-center gap-3">
                  {getStatusBadge(doc.status)}
                  {doc.status === 'pending_signature' && (
                    <button
                      data-tour="portal-docs-sign-btn"
                      onClick={() => setSigningDoc(doc)}
                      className="px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg hover:bg-zinc-800 transition-colors"
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
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-zinc-900">Sign Document</h2>
              <button
                onClick={() => setSigningDoc(null)}
                className="p-1 hover:bg-zinc-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-zinc-500" />
              </button>
            </div>
            <div className="mb-4">
              <p className="text-sm text-zinc-600 mb-4">
                By typing your name below, you agree to sign "{signingDoc.title}".
              </p>
              <label className="block text-sm font-medium text-zinc-700 mb-2">
                Type your full legal name
              </label>
              <input
                type="text"
                value={signatureName}
                onChange={(e) => setSignatureName(e.target.value)}
                placeholder="Enter your full name"
                className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent"
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setSigningDoc(null)}
                className="flex-1 px-4 py-2 border border-zinc-200 text-zinc-700 rounded-lg hover:bg-zinc-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSign}
                disabled={!signatureName.trim() || signing}
                className="flex-1 px-4 py-2 bg-zinc-900 text-white rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
