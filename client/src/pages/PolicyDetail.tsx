import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { policies, candidates } from '../api/client';
import type { Policy, PolicySignature, SignatureRequest } from '../types';
import { ChevronLeft, Trash2, Plus, X, FileText, ExternalLink } from 'lucide-react';

interface CandidateOption {
  id: string;
  name: string;
  email: string;
}

const parseRecipient = (text: string): { name: string; email: string } | null => {
  const line = text.trim();
  if (!line) return null;
  const bracketMatch = line.match(/^(.*?)\s*<(.+@.+)>$/);
  if (bracketMatch) return { name: bracketMatch[1].trim() || bracketMatch[2].split('@')[0], email: bracketMatch[2].trim() };
  if (line.includes(',')) {
    const parts = line.split(',').map(s => s.trim());
    const emailIndex = parts.findIndex(p => p.includes('@'));
    if (emailIndex !== -1) {
      const email = parts[emailIndex];
      const name = parts.filter((_, i) => i !== emailIndex).join(' ').trim();
      return { name: name || email.split('@')[0], email };
    }
  }
  if (line.includes('@') && !line.includes(' ')) return { name: line.split('@')[0], email: line };
  return null;
};

export function PolicyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [signatures, setSignatures] = useState<PolicySignature[]>([]);
  const [loading, setLoading] = useState(true);
  const [signers, setSigners] = useState<SignatureRequest[]>([
    { name: '', email: '', type: 'candidate' as const }
  ]);
  const [candidateList, setCandidateList] = useState<CandidateOption[]>([]);
  const [showCandidateSelector, setShowCandidateSelector] = useState(false);
  const [showSignatureModal, setShowSignatureModal] = useState(false);

  const loadPolicy = useCallback(async () => {
    try {
      setLoading(true);
      const data = await policies.get(id!);
      setPolicy(data);
    } catch (error) {
      console.error('Failed to load policy:', error);
    } finally {
      setLoading(false);
    }
  }, [id]);

  const loadSignatures = useCallback(async () => {
    try {
      const data = await policies.listSignatures(id!);
      setSignatures(data);
    } catch (error) {
      console.error('Failed to load signatures:', error);
    }
  }, [id]);

  const loadCandidates = async () => {
    try {
      const data = await candidates.listForCompany();
      if (data) setCandidateList(data);
    } catch (error) {
      console.error('Failed to load candidates:', error);
    }
  };

  useEffect(() => {
    loadPolicy();
    loadSignatures();
  }, [loadPolicy, loadSignatures]);

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this policy?')) return;
    try {
      await policies.delete(id!);
      navigate('/app/policies');
    } catch (error) {
      console.error('Failed to delete policy:', error);
    }
  };

  const handleAddSigner = () => {
    setSigners([...signers, { name: '', email: '', type: 'candidate' as const }]);
  };

  const handleRemoveSigner = (index: number) => {
    if (signers.length > 1) {
      setSigners(signers.filter((_, i) => i !== index));
    }
  };

  const handleSignerChange = (index: number, field: 'name' | 'email' | 'type', value: string) => {
    const newSigners = [...signers];
    const signer = newSigners[index];
    if (field === 'name') signer.name = value;
    else if (field === 'email') signer.email = value;
    else if (field === 'type') signer.type = value as 'candidate' | 'external';
    setSigners(newSigners);
  };

  const handleCandidateSelect = (candidate: CandidateOption) => {
    const exists = signers.some(s => s.email === candidate.email);
    if (!exists) {
      if (signers.length === 1 && !signers[0].name && !signers[0].email) {
        setSigners([{ name: candidate.name, email: candidate.email, type: 'candidate' as const, id: candidate.id }]);
      } else {
        setSigners([...signers, { name: candidate.name, email: candidate.email, type: 'candidate' as const, id: candidate.id }]);
      }
    }
    setShowCandidateSelector(false);
  };

  const handleSendSignatures = async () => {
    const validSigners = signers.filter(s => s.name.trim() && s.email.trim());
    if (validSigners.length === 0) return;

    try {
      await policies.sendSignatures(id!, validSigners);
      setShowSignatureModal(false);
      setSigners([{ name: '', email: '', type: 'candidate' as const }]);
      loadSignatures();
    } catch (error) {
      console.error('Failed to send signature requests:', error);
    }
  };

  const handleCancelSignature = async (signatureId: string) => {
    if (!confirm('Cancel this signature request?')) return;
    try {
      await policies.cancelSignature(signatureId);
      setSignatures(signatures.filter(s => s.id !== signatureId));
    } catch (error) {
      console.error('Failed to cancel signature:', error);
    }
  };

  const handleResendSignature = async (signatureId: string) => {
    try {
      await policies.resendSignature(signatureId);
      alert('Signature request resent');
    } catch (error) {
      console.error('Failed to resend signature:', error);
    }
  };

  const sigStatusColors = {
    pending: 'text-amber-600 font-medium',
    signed: 'text-emerald-600 font-medium',
    declined: 'text-rose-600 font-medium',
    expired: 'text-zinc-400 font-medium',
  };

  if (loading || !policy) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading policy...</div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-4">
          <button 
            onClick={() => navigate('/app/policies')}
            className="text-[10px] text-zinc-500 hover:text-zinc-900 transition-colors uppercase tracking-wider flex items-center gap-1"
          >
            <ChevronLeft size={12} /> Back to Policies
          </button>
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="text-[10px] text-zinc-400 font-mono tracking-wide">POLICY</span>
              <span className="text-[10px] uppercase tracking-wide font-medium text-zinc-500 bg-zinc-100 px-1.5 py-0.5 rounded border border-zinc-200">
                v{policy.version}
              </span>
            </div>
            <h1 className="text-3xl font-light tracking-tight text-zinc-900">{policy.title}</h1>
          </div>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={handleDelete}
            className="text-[10px] text-zinc-400 hover:text-red-600 uppercase tracking-wider font-medium px-3 py-2 transition-colors"
          >
            Delete
          </button>
          <button 
            onClick={() => { loadCandidates(); setShowSignatureModal(true); }}
            className="bg-zinc-900 hover:bg-zinc-800 text-white text-[10px] uppercase tracking-wider font-medium px-4 py-2 transition-colors"
          >
            Send Signatures
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
        <div className="lg:col-span-2 space-y-8">
          {/* Document Section - Shown prominently when file is uploaded */}
          {policy.file_url && (
            <div className="space-y-4">
              <div className="border-b border-zinc-200 pb-2">
                <h2 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Policy Document</h2>
              </div>
              <a
                href={policy.file_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-4 p-6 bg-zinc-50 border border-zinc-200 hover:border-zinc-300 hover:bg-zinc-100 transition-colors group"
              >
                <div className="w-12 h-12 bg-white border border-zinc-200 flex items-center justify-center">
                  <FileText size={24} className="text-zinc-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-zinc-900 group-hover:text-zinc-700">View Policy Document</div>
                  <div className="text-[10px] text-zinc-500 font-mono truncate mt-0.5">
                    {policy.file_url.split('/').pop()}
                  </div>
                </div>
                <ExternalLink size={16} className="text-zinc-400 group-hover:text-zinc-600" />
              </a>
            </div>
          )}

          {/* Text Content Section */}
          {policy.content && (
            <div className="space-y-4">
              <div className="border-b border-zinc-200 pb-2">
                <h2 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">
                  {policy.file_url ? 'Additional Notes' : 'Policy Content'}
                </h2>
              </div>
              <div className="prose prose-zinc max-w-none">
                <div className="text-zinc-800 text-sm font-serif leading-relaxed whitespace-pre-wrap">
                  {policy.content}
                </div>
              </div>
            </div>
          )}

          {/* Empty state if neither exists */}
          {!policy.file_url && !policy.content && (
            <div className="space-y-4">
              <div className="border-b border-zinc-200 pb-2">
                <h2 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Policy Content</h2>
              </div>
              <div className="py-8 text-center text-zinc-400 text-xs">
                No content or document uploaded.
              </div>
            </div>
          )}
        </div>

        <div className="space-y-12">
          {/* Overview Section */}
          <div className="space-y-6">
            <div className="border-b border-zinc-200 pb-2">
              <h2 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Overview</h2>
            </div>
            <div className="space-y-4">
               <div>
                  <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Company</label>
                  <p className="text-sm text-zinc-900">{policy.company_name}</p>
               </div>
               <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Created</label>
                    <p className="text-xs text-zinc-600 font-mono">{new Date(policy.created_at).toLocaleDateString()}</p>
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Status</label>
                    <p className="text-xs text-zinc-900 font-medium uppercase tracking-wide">{policy.status}</p>
                  </div>
               </div>
               {policy.description && (
                 <div>
                    <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Description</label>
                    <p className="text-xs text-zinc-500 leading-relaxed italic">{policy.description}</p>
                 </div>
               )}
            </div>
          </div>

          {/* Signatures Section */}
          <div className="space-y-6">
            <div className="border-b border-zinc-200 pb-2 flex items-center justify-between">
               <h2 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Signatures</h2>
               <div className="text-[10px] font-mono text-zinc-400">{signatures.length} TOTAL</div>
            </div>
            
            <div className="space-y-1 divide-y divide-zinc-100">
               {signatures.length === 0 ? (
                 <div className="py-8 text-center text-zinc-400 text-xs">
                    No requests sent.
                 </div>
               ) : (
                 signatures.map((sig) => (
                   <div key={sig.id} className="py-4 hover:bg-zinc-50/50 transition-colors group">
                      <div className="flex items-start justify-between mb-1">
                         <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-zinc-900 truncate">{sig.signer_name}</div>
                            <div className="text-[10px] text-zinc-500 font-mono truncate">{sig.signer_email}</div>
                         </div>
                         <span className={`text-[10px] uppercase tracking-wider ${sigStatusColors[sig.status as keyof typeof sigStatusColors] || 'text-zinc-500'}`}>
                            {sig.status}
                         </span>
                      </div>
                      <div className="flex items-center justify-between mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                         <div className="text-[9px] text-zinc-400 uppercase tracking-wide">
                            {sig.signed_at ? `Signed ${new Date(sig.signed_at).toLocaleDateString()}` : `Expires ${new Date(sig.expires_at).toLocaleDateString()}`}
                         </div>
                         <div className="flex gap-3">
                            {sig.status === 'pending' && (
                              <>
                                <button onClick={() => handleResendSignature(sig.id)} className="text-[9px] text-zinc-500 hover:text-zinc-900 uppercase tracking-widest font-bold">Resend</button>
                                <button onClick={() => handleCancelSignature(sig.id)} className="text-[9px] text-zinc-400 hover:text-rose-600 uppercase tracking-widest font-bold">Cancel</button>
                              </>
                            )}
                         </div>
                      </div>
                   </div>
                 ))
               )}
            </div>
          </div>
        </div>
      </div>

      {/* Signature Modal - Inline implementation */}
      {showSignatureModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/20 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-white shadow-2xl rounded-sm flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between p-6 border-b border-zinc-100">
              <h3 className="text-sm font-light text-zinc-900 uppercase tracking-wider">Send Signature Requests</h3>
              <button onClick={() => setShowSignatureModal(false)} className="text-zinc-400 hover:text-zinc-600">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-8 space-y-8 overflow-y-auto">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Add Recipients</label>
                  <button onClick={() => setShowCandidateSelector(!showCandidateSelector)} className="text-[10px] text-zinc-900 hover:underline uppercase tracking-widest font-medium">
                    {showCandidateSelector ? 'Hide Candidates' : 'Select Candidates'}
                  </button>
                </div>

                {showCandidateSelector && (
                  <div className="p-4 bg-zinc-50 border border-zinc-200 rounded-sm max-h-48 overflow-y-auto">
                    {candidateList.length === 0 ? (
                      <p className="text-xs text-zinc-400 text-center py-4">No candidates found</p>
                    ) : (
                      <div className="space-y-1">
                        {candidateList.map((candidate) => {
                          const isSelected = signers.some(s => s.email === candidate.email);
                          return (
                            <button
                              key={candidate.id}
                              onClick={() => handleCandidateSelect(candidate)}
                              disabled={isSelected}
                              className={`w-full text-left px-3 py-2 rounded-sm text-xs transition-colors ${isSelected ? 'text-emerald-600 cursor-default opacity-50' : 'text-zinc-600 hover:bg-zinc-100'}`}
                            >
                              {candidate.name} <span className="text-zinc-400 font-mono ml-1">[{candidate.email}]</span>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                <textarea 
                  className="w-full px-0 py-2 bg-transparent border-b border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-900 transition-colors h-20 placeholder:text-zinc-300 resize-none"
                  placeholder="Paste emails (newline or comma separated)..."
                  onBlur={(e) => {
                    const text = e.target.value;
                    if (!text.trim()) return;
                    const emails = text.split(/[\n,]+/).map(s => s.trim()).filter(s => s.includes('@'));
                    const newSigners: SignatureRequest[] = [];
                    emails.forEach(email => {
                      const parsed = parseRecipient(email);
                      if (parsed && !signers.some(s => s.email === parsed.email)) {
                        newSigners.push({ ...parsed, type: 'external' });
                      }
                    });
                    if (newSigners.length > 0) {
                      if (signers.length === 1 && !signers[0].email) { setSigners(newSigners); }
                      else { setSigners([...signers, ...newSigners]); }
                    }
                    e.target.value = '';
                  }}
                />
              </div>

              <div className="space-y-4">
                <h3 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Review List ({signers.filter(s => s.email).length})</h3>
                <div className="space-y-3">
                  {signers.map((signer, index) => (
                    <div key={index} className="flex items-center gap-4 group">
                      <div className="flex-1 grid grid-cols-2 gap-4">
                        <input
                          type="text"
                          value={signer.name}
                          onChange={(e) => handleSignerChange(index, 'name', e.target.value)}
                          className="bg-transparent border-b border-zinc-100 text-sm text-zinc-900 focus:outline-none focus:border-zinc-900 pb-1"
                          placeholder="Name"
                        />
                        <input
                          type="email"
                          value={signer.email}
                          onChange={(e) => handleSignerChange(index, 'email', e.target.value)}
                          className="bg-transparent border-b border-zinc-100 text-sm text-zinc-900 focus:outline-none focus:border-zinc-900 pb-1 font-mono"
                          placeholder="Email"
                        />
                      </div>
                      <button onClick={() => handleRemoveSigner(index)} className="text-zinc-300 hover:text-red-600 opacity-0 group-hover:opacity-100 p-1">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <button onClick={handleAddSigner} className="text-[10px] text-zinc-500 hover:text-zinc-900 uppercase tracking-widest font-medium flex items-center gap-1 transition-colors">
                  <Plus size={12} /> Add another
                </button>
              </div>
            </div>

            <div className="p-6 border-t border-zinc-100 bg-zinc-50/50 flex justify-end gap-3">
              <button 
                onClick={() => setShowSignatureModal(false)}
                className="px-4 py-2 text-zinc-500 hover:text-zinc-900 text-xs font-medium uppercase tracking-wider transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={handleSendSignatures}
                className="bg-zinc-900 hover:bg-zinc-800 text-white text-xs uppercase tracking-wider font-medium px-6 py-2 transition-colors disabled:opacity-50"
              >
                Send Requests
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PolicyDetail;
