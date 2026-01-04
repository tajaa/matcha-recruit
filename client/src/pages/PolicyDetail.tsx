import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Modal } from '../components/Modal';
import { policies, candidates } from '../api/client';
import type { Policy, PolicySignature, SignatureRequest } from '../types';

// Mock data for test policies
const MOCK_POLICIES: Record<string, Policy> = {
  'p1': {
    id: 'p1',
    company_id: 'c1',
    company_name: 'Matcha Recruit',
    title: 'Remote Work Policy',
    description: 'Guidelines and requirements for employees working remotely or in a hybrid capacity.',
    content: `REMOTE WORK POLICY

1. PURPOSE
This policy establishes guidelines for employees who work from a location other than our primary offices.

2. ELIGIBILITY
Remote work is available to employees whose duties can be fulfilled effectively from a remote location.

3. WORKSPACE
Employees must have a designated workspace that is quiet, safe, and free from distractions.

4. HOURS OF WORK
Remote employees are expected to work their standard scheduled hours unless approved otherwise.

5. COMMUNICATION
Regular communication via Slack, Email, and Video calls is required.`,
    file_url: null,
    version: '1.2',
    status: 'active',
    signature_count: 45,
    signed_count: 42,
    pending_signatures: 3,
    created_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    created_by: 'admin1'
  },
  'p2': {
    id: 'p2',
    company_id: 'c1',
    company_name: 'Matcha Recruit',
    title: 'Code of Conduct',
    description: 'Expected behavior and professional standards for all members of the organization.',
    content: `CODE OF CONDUCT

1. PROFESSIONALISM
Treat all colleagues, clients, and partners with respect and dignity.

2. INTEGRITY
Act with honesty and transparency in all business dealings.

3. CONFIDENTIALITY
Protect sensitive company and client information.

4. DIVERSITY & INCLUSION
We are committed to maintaining a diverse and inclusive workplace free from discrimination.`,
    file_url: null,
    version: '2.0',
    status: 'active',
    signature_count: 120,
    signed_count: 118,
    pending_signatures: 2,
    created_at: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 120 * 24 * 60 * 60 * 1000).toISOString(),
    created_by: 'admin1'
  },
  'p3': {
    id: 'p3',
    company_id: 'c1',
    company_name: 'Matcha Recruit',
    title: '2026 Bonus Structure',
    description: 'Proposed annual performance bonus criteria and payout schedules for the upcoming year.',
    content: 'CONFIDENTIAL: 2026 BONUS STRUCTURE DRAFT...',
    file_url: null,
    version: '0.1',
    status: 'draft',
    signature_count: 0,
    signed_count: 0,
    pending_signatures: 0,
    created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    created_by: 'admin1'
  }
};

const MOCK_SIGNATURES: Record<string, PolicySignature[]> = {
  'p1': [
    {
      id: 's1',
      policy_id: 'p1',
      policy_title: 'Remote Work Policy',
      signer_type: 'employee',
      signer_id: 'u1',
      signer_name: 'Alice Johnson',
      signer_email: 'alice@matcha.dev',
      status: 'signed',
      signed_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      signature_data: 'signed',
      ip_address: '192.168.1.1',
      token: 'tok1',
      expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString()
    },
    {
      id: 's2',
      policy_id: 'p1',
      policy_title: 'Remote Work Policy',
      signer_type: 'employee',
      signer_id: 'u2',
      signer_name: 'Bob Smith',
      signer_email: 'bob@matcha.dev',
      status: 'pending',
      signed_at: null,
      signature_data: null,
      ip_address: null,
      token: 'tok2',
      expires_at: new Date(Date.now() + 25 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString()
    }
  ],
  'p2': [
    {
      id: 's3',
      policy_id: 'p2',
      policy_title: 'Code of Conduct',
      signer_type: 'employee',
      signer_id: 'u1',
      signer_name: 'Alice Johnson',
      signer_email: 'alice@matcha.dev',
      status: 'signed',
      signed_at: new Date(Date.now() - 300 * 24 * 60 * 60 * 1000).toISOString(),
      signature_data: 'signed',
      ip_address: '192.168.1.1',
      token: 'tok3',
      expires_at: new Date(Date.now() - 200 * 24 * 60 * 60 * 1000).toISOString(),
      created_at: new Date(Date.now() - 360 * 24 * 60 * 60 * 1000).toISOString()
    }
  ],
  'p3': []
};

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
  const [signers, setSigners] = useState<SignatureRequest[]>([
    { name: '', email: '', type: 'candidate' as const }
  ]);
  const [candidateList, setCandidateList] = useState<CandidateOption[]>([]);
  const [showCandidateSelector, setShowCandidateSelector] = useState(false);
  const [showSignatureModal, setShowSignatureModal] = useState(false);

  const loadPolicy = async () => {
    try {
      setLoading(true);
      if (id && MOCK_POLICIES[id]) {
        setPolicy(MOCK_POLICIES[id]);
        return;
      }
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
      if (id && MOCK_SIGNATURES[id]) {
        setSignatures(MOCK_SIGNATURES[id]);
        return;
      }
      const data = await policies.listSignatures(id!);
      setSignatures(data);
    } catch (error) {
      console.error('Failed to load signatures:', error);
    }
  };

  const loadCandidates = async () => {
    try {
      const data = await candidates.listForCompany();
      // If API returns empty or fails, provide mock candidates for testing
      if (!data || data.length === 0) {
        setCandidateList([
          { id: 'mc1', name: 'Sarah Miller', email: 'sarah.m@example.com' },
          { id: 'mc2', name: 'James Wilson', email: 'james.w@example.com' },
          { id: 'mc3', name: 'Emily Chen', email: 'emily.c@example.com' }
        ]);
      } else {
        setCandidateList(data);
      }
    } catch (error) {
      console.warn('Failed to load candidates from API, using mocks');
      setCandidateList([
        { id: 'mc1', name: 'Sarah Miller', email: 'sarah.m@example.com' },
        { id: 'mc2', name: 'James Wilson', email: 'james.w@example.com' },
        { id: 'mc3', name: 'Emily Chen', email: 'emily.c@example.com' }
      ]);
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
      // If the first row is empty, replace it
      if (signers.length === 1 && !signers[0].name && !signers[0].email) {
        setSigners([{ 
          name: candidate.name, 
          email: candidate.email, 
          type: 'candidate' as const,
          id: candidate.id 
        }]);
      } else {
        setSigners([...signers, { 
          name: candidate.name, 
          email: candidate.email, 
          type: 'candidate' as const,
          id: candidate.id 
        }]);
      }
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
      // Handle mock policies
      if (id && MOCK_POLICIES[id]) {
        // Simulate API delay
        await new Promise(resolve => setTimeout(resolve, 800));
        
        const newSignatures: PolicySignature[] = validSigners.map((signer, idx) => ({
          id: `new_sig_${Date.now()}_${idx}`,
          policy_id: id,
          policy_title: MOCK_POLICIES[id].title,
          signer_type: signer.type,
          signer_id: signer.id || null,
          signer_name: signer.name,
          signer_email: signer.email,
          status: 'pending',
          signed_at: null,
          signature_data: null,
          ip_address: null,
          token: `mock_token_${Date.now()}`,
          expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
          created_at: new Date().toISOString()
        }));

        // Update local mock data (for this session)
        if (MOCK_SIGNATURES[id]) {
          MOCK_SIGNATURES[id] = [...newSignatures, ...MOCK_SIGNATURES[id]];
        }

        setSignatures(prev => [...newSignatures, ...prev]);
        setShowSignatureModal(false);
        setSigners([{ name: '', email: '', type: 'candidate' as const }]);
        alert(`Successfully sent ${validSigners.length} signature requests (Simulation)`);
        return;
      }

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
                {candidateList.length === 0 ? (
                  <p className="text-sm text-zinc-500 text-center py-4">No candidates found</p>
                ) : (
                  <div className="space-y-1">
                    {candidateList.map((candidate) => {
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

            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                 <div className="flex items-center justify-between mb-2">
                    <label className="block text-xs tracking-wider uppercase text-zinc-500">
                      Bulk Add Emails
                    </label>
                    <label className="text-xs text-blue-400 hover:text-blue-300 cursor-pointer flex items-center gap-1">
                      <input
                        type="file"
                        accept=".csv"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            const reader = new FileReader();
                            reader.onload = (event) => {
                              const text = event.target?.result as string;
                              const lines = text.split('\n');
                              const newSigners: SignatureRequest[] = [];
                              
                              lines.forEach(line => {
                                const [email, name] = line.split(',').map(s => s.trim());
                                if (email && email.includes('@')) {
                                  newSigners.push({
                                    name: name || email.split('@')[0],
                                    email: email,
                                    type: 'external' // Default to external for CSV imports
                                  });
                                }
                              });

                              if (newSigners.length > 0) {
                                // Filter out duplicates based on email
                                const uniqueNewSigners = newSigners.filter(ns => 
                                  !signers.some(existing => existing.email === ns.email)
                                );
                                
                                if (uniqueNewSigners.length > 0) {
                                  // If the current list has only one empty entry, replace it
                                  if (signers.length === 1 && !signers[0].email) {
                                     setSigners(uniqueNewSigners);
                                  } else {
                                     setSigners([...signers, ...uniqueNewSigners]);
                                  }
                                  alert(`Added ${uniqueNewSigners.length} signers from CSV`);
                                } else {
                                  alert('No new unique emails found in CSV');
                                }
                              }
                            };
                            reader.readAsText(file);
                          }
                          // Reset input
                          e.target.value = '';
                        }}
                      />
                      <span>Upload CSV</span>
                    </label>
                 </div>
                 <textarea 
                    className="w-full px-4 py-2 bg-zinc-950 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 rounded-md h-24 placeholder:text-zinc-600"
                    placeholder="Paste emails here (one per line or comma separated)..."
                    onBlur={(e) => {
                      const text = e.target.value;
                      if (!text.trim()) return;

                      // Split by newlines or commas
                      const emails = text.split(/[\n,]+/).map(s => s.trim()).filter(s => s.includes('@'));
                      
                      const newSigners: SignatureRequest[] = [];
                      emails.forEach(email => {
                         if (!signers.some(s => s.email === email)) {
                            newSigners.push({
                              name: email.split('@')[0], // Default name from email
                              email: email,
                              type: 'external'
                            });
                         }
                      });

                      if (newSigners.length > 0) {
                         if (signers.length === 1 && !signers[0].email) {
                            setSigners(newSigners);
                         } else {
                            setSigners([...signers, ...newSigners]);
                         }
                      }
                      
                      // Clear textarea
                      e.target.value = '';
                    }}
                 />
                 <p className="text-[10px] text-zinc-500 mt-1">
                   Format: Email only, or "Email, Name" per line for CSV
                 </p>
              </div>
            </div>

            <div className="border-t border-zinc-800 pt-4 space-y-4 max-h-60 overflow-y-auto">
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
            </div>

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
