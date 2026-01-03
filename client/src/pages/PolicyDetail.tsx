import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Modal } from '../components/Modal';
import { policies, candidates } from '../api/client';
import type { Policy, PolicySignature, SignatureRequest } from '../types';

interface CandidateOption {
  id: string;
  name: string;
  email: string;
}

export function PolicyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [signatures, setSignatures] = useState<PolicySignature[]>([]);
  const [loading, setLoading] = useState(true);
  const [showSignatureModal, setShowSignatureModal] = useState(false);
  const [signers, setSigners] = useState<SignatureRequest[]>([
    { name: '', email: '', type: 'candidate' as const }
  ]);
  const [candidates, setCandidates] = useState<CandidateOption[]>([]);
  const [showCandidateSelector, setShowCandidateSelector] = useState(false);

  const loadPolicy = async () => {
    try {
      setLoading(true);
      const data = await policies.get(id!);
      setPolicy(data);
    } catch (error) {
      console.error('Failed to load policy:', error);
      alert('Failed to load policy');
    } finally {
      setLoading(false);
    }
  };

  const loadSignatures = async () => {
    try {
      const data = await policies.listSignatures(id!);
      setSignatures(data);
    } catch (error) {
      console.error('Failed to load signatures:', error);
    }
  };

  const loadCandidates = async () => {
    try {
      const data = await candidates.listForCompany();
      setCandidates(data);
    } catch (error) {
      console.error('Failed to load candidates:', error);
    }
  };

  useEffect(() => {
    loadPolicy();
    loadSignatures();
  }, [id]);

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this policy?')) return;

    try {
      await policies.delete(id!);
      navigate('/app/policies');
    } catch (error) {
      console.error('Failed to delete policy:', error);
      alert('Failed to delete policy');
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
    const newSigners = [...signers] as { name: string; email: string; type: string }[];
    (newSigners[index] as any)[field] = value;
    setSigners(newSigners as SignatureRequest[]);
  };

  const handleCandidateSelect = (candidate: CandidateOption) => {
    const exists = signers.some(s => s.email === candidate.email);
    if (!exists) {
      setSigners([...signers, { 
        name: candidate.name, 
        email: candidate.email, 
        type: 'candidate' as const,
        id: candidate.id 
      }]);
    }
    setShowCandidateSelector(false);
  };

  const handleSendSignatures = async () => {
    const validSigners = signers.filter(s => s.name.trim() && s.email.trim());

    if (validSigners.length === 0) {
      alert('Please add at least one signer with a valid name and email');
      return;
    }

    try {
      await policies.sendSignatures(id!, validSigners);
      setShowSignatureModal(false);
      setSigners([{ name: '', email: '', type: 'candidate' as const }]);
      loadSignatures();
      alert(`Sent ${validSigners.length} signature requests`);
    } catch (error) {
      console.error('Failed to send signature requests:', error);
      alert('Failed to send signature requests');
    }
  };

  const handleCancelSignature = async (signatureId: string) => {
    if (!confirm('Cancel this signature request?')) return;

    try {
      await policies.cancelSignature(signatureId);
      loadSignatures();
    } catch (error) {
      console.error('Failed to cancel signature:', error);
      alert('Failed to cancel signature');
    }
  };

  const handleResendSignature = async (signatureId: string) => {
    try {
      await policies.resendSignature(signatureId);
      alert('Signature request resent');
    } catch (error) {
      console.error('Failed to resend signature:', error);
      alert('Failed to resend signature');
    }
  };

  const statusColors = {
    pending: 'bg-yellow-900/30 text-yellow-400',
    signed: 'bg-green-900/30 text-green-400',
    declined: 'bg-red-900/30 text-red-400',
    expired: 'bg-zinc-700 text-zinc-400',
  };

  if (loading || !policy) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-zinc-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">{policy.title}</h1>
          <p className="text-sm text-zinc-500 mt-1">Version {policy.version}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => navigate('/app/policies')}>
            Back
          </Button>
          <Button onClick={() => { loadCandidates(); setShowSignatureModal(true); }}>
            Send Signatures
          </Button>
          <Button variant="secondary" onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>

      <Card>
        <div className="p-6 border-b border-zinc-800">
          <h2 className="text-lg font-semibold text-white mb-4">Policy Details</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-zinc-500">Status</span>
              <div className="text-white mt-1">
                <span className={`px-2 py-0.5 rounded text-[10px] tracking-wider uppercase ${
                  policy.status === 'active' ? 'bg-green-900/30 text-green-400' :
                  policy.status === 'draft' ? 'bg-zinc-700 text-zinc-300' :
                  'bg-zinc-700 text-zinc-400'
                }`}>
                  {policy.status}
                </span>
              </div>
            </div>
            <div>
              <span className="text-zinc-500">Signatures</span>
              <div className="text-white mt-1">
                {signatures.length} total ({signatures.filter(s => s.status === 'signed').length} signed)
              </div>
            </div>
            <div>
              <span className="text-zinc-500">Created</span>
              <div className="text-white mt-1">{new Date(policy.created_at).toLocaleDateString()}</div>
            </div>
            <div>
              <span className="text-zinc-500">Updated</span>
              <div className="text-white mt-1">{new Date(policy.updated_at).toLocaleDateString()}</div>
            </div>
          </div>
        </div>

        {policy.description && (
          <div className="p-6 border-b border-zinc-800">
            <h3 className="text-sm font-medium text-zinc-500 mb-2">Description</h3>
            <p className="text-white">{policy.description}</p>
          </div>
        )}

        <div className="p-6">
          <h3 className="text-sm font-medium text-zinc-500 mb-4">Policy Content</h3>
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 text-white text-sm whitespace-pre-wrap leading-relaxed max-h-[600px] overflow-y-auto">
            {policy.content}
          </div>
        </div>
      </Card>

      <Card>
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Signatures</h2>
          </div>

          {signatures.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-zinc-500 mb-4">No signature requests sent yet</p>
              <Button onClick={() => { loadCandidates(); setShowSignatureModal(true); }}>Send Signatures</Button>
            </div>
          ) : (
            <div className="space-y-3">
              {signatures.map((sig) => (
                <div key={sig.id} className="p-4 bg-zinc-900/50 border border-zinc-800 rounded-lg">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-base font-medium text-white">{sig.signer_name}</h3>
                        <span className={`px-2 py-0.5 rounded text-[10px] tracking-wider uppercase ${statusColors[sig.status as keyof typeof statusColors]}`}>
                          {sig.status}
                        </span>
                      </div>
                      <p className="text-sm text-zinc-400 mb-1">{sig.signer_email}</p>
                      <div className="text-xs text-zinc-500 space-x-4">
                        <span>Expires: {new Date(sig.expires_at).toLocaleDateString()}</span>
                        {sig.signed_at && (
                          <span>Signed: {new Date(sig.signed_at).toLocaleDateString()}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {sig.status === 'pending' && (
                        <>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleResendSignature(sig.id)}
                          >
                            Resend
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleCancelSignature(sig.id)}
                          >
                            Cancel
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {showSignatureModal && (
        <Modal
          isOpen={showSignatureModal}
          onClose={() => setShowSignatureModal(false)}
          title="Send Signature Requests"
        >
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowCandidateSelector(!showCandidateSelector)}
              >
                {showCandidateSelector ? 'Hide Candidates' : 'Select from Candidates'}
              </Button>
              <span className="text-xs text-zinc-500">
                {signers.filter(s => s.name && s.email).length} selected
              </span>
            </div>

            {showCandidateSelector && (
              <div className="p-4 bg-zinc-900 border border-zinc-800 rounded-lg max-h-48 overflow-y-auto">
                {candidates.length === 0 ? (
                  <p className="text-sm text-zinc-500 text-center py-4">No candidates found</p>
                ) : (
                  <div className="space-y-1">
                    {candidates.map((candidate) => {
                      const isSelected = signers.some(s => s.email === candidate.email);
                      return (
                        <button
                          key={candidate.id}
                          onClick={() => handleCandidateSelect(candidate)}
                          disabled={isSelected}
                          className={`w-full text-left px-3 py-2 rounded text-sm transition-colors ${
                            isSelected 
                              ? 'bg-green-900/20 text-green-400 cursor-default' 
                              : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                          }`}
                        >
                          <span className="font-medium">{candidate.name}</span>
                          <span className="text-zinc-500 ml-2">{candidate.email}</span>
                          {isSelected && <span className="float-right">✓</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {signers.map((signer, index) => (
              <div key={index} className="p-4 bg-zinc-900 border border-zinc-800 rounded-lg">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-medium text-white">Signer {index + 1}</h3>
                  {signers.length > 1 && (
                    <button
                      type="button"
                      onClick={() => handleRemoveSigner(index)}
                      className="text-xs text-zinc-500 hover:text-red-400 transition-colors"
                    >
                      Remove
                    </button>
                  )}
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                      Name *
                    </label>
                    <input
                      type="text"
                      value={signer.name}
                      onChange={(e) => handleSignerChange(index, 'name', e.target.value)}
                      className="w-full px-4 py-2 bg-zinc-950 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                      placeholder="Full name"
                    />
                  </div>

                  <div>
                    <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                      Email *
                    </label>
                    <input
                      type="email"
                      value={signer.email}
                      onChange={(e) => handleSignerChange(index, 'email', e.target.value)}
                      className="w-full px-4 py-2 bg-zinc-950 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md"
                      placeholder="email@example.com"
                    />
                  </div>
                </div>
              </div>
            ))}

            <Button
              variant="secondary"
              onClick={handleAddSigner}
              className="w-full"
            >
              Add Another Signer
            </Button>

            <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800">
              <Button
                variant="secondary"
                onClick={() => setShowSignatureModal(false)}
              >
                Cancel
              </Button>
              <Button onClick={handleSendSignatures}>
                Send Signature Requests
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default PolicyDetail;
