import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { Modal } from '../components/Modal';
import { policies, candidates } from '../api/client';
import type { Policy, PolicySignature, SignatureRequest } from '../types';
import { ArrowLeft, Upload, Trash2, Mail } from 'lucide-react';

// Mock data for test policies (Preserved from previous implementation)
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

// Helper to parse recipients from various formats
const parseRecipient = (text: string): { name: string; email: string } | null => {
  const line = text.trim();
  if (!line) return null;

  // 1. Format: Name <email>
  const bracketMatch = line.match(/^(.*?)\s*<(.+@.+)>$/);
  if (bracketMatch) {
    return { name: bracketMatch[1].trim() || bracketMatch[2].split('@')[0], email: bracketMatch[2].trim() };
  }

  // 2. Format: CSV (Name, Email or Email, Name)
  if (line.includes(',')) {
    const parts = line.split(',').map(s => s.trim());
    const emailIndex = parts.findIndex(p => p.includes('@'));
    
    if (emailIndex !== -1) {
      const email = parts[emailIndex];
      // Join all other parts as the name
      const name = parts.filter((_, i) => i !== emailIndex).join(' ').trim();
      return { name: name || email.split('@')[0], email };
    }
  }

  // 3. Format: Just Email
  if (line.includes('@') && !line.includes(' ')) {
    return { name: line.split('@')[0], email: line };
  }

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
      if (id && !MOCK_POLICIES[id]) {
        await policies.delete(id!);
      }
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
    (newSigners[index] as any)[field] = value;
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
      if (id && MOCK_POLICIES[id]) {
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
    } catch (error) {
      console.error('Failed to send signature requests:', error);
    }
  };

  const handleCancelSignature = async (signatureId: string) => {
    if (!confirm('Cancel this signature request?')) return;
    try {
      if (!signatureId.startsWith('new_sig_')) {
        await policies.cancelSignature(signatureId);
      }
      setSignatures(signatures.filter(s => s.id !== signatureId));
    } catch (error) {
      console.error('Failed to cancel signature:', error);
    }
  };

  const handleResendSignature = async (signatureId: string) => {
    try {
      if (!signatureId.startsWith('new_sig_')) {
        await policies.resendSignature(signatureId);
      }
      alert('Signature request resent');
    } catch (error) {
      console.error('Failed to resend signature:', error);
    }
  };

  const statusColors = {
    pending: 'bg-amber-900/20 text-amber-400 border-amber-900/50',
    signed: 'bg-emerald-900/20 text-emerald-400 border-emerald-900/50',
    declined: 'bg-rose-900/20 text-rose-400 border-rose-900/50',
    expired: 'bg-zinc-800/80 text-zinc-500 border-zinc-700',
  };

  if (loading || !policy) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="w-2 h-2 rounded-full bg-white animate-ping" />
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-4">
          <button 
            onClick={() => navigate('/app/policies')}
            className="flex items-center gap-2 text-zinc-500 hover:text-zinc-300 transition-colors text-xs font-mono uppercase tracking-widest"
          >
            <ArrowLeft className="w-3 h-3" /> Back to Policies
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-light tracking-tight text-white">{policy.title}</h1>
              <span className="text-[10px] font-mono text-zinc-600 uppercase tracking-tighter bg-zinc-950 px-1.5 py-0.5 rounded border border-zinc-800">
                v{policy.version}
              </span>
            </div>
            <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">Policy Details & Distribution</p>
          </div>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={handleDelete}>
            Delete
          </Button>
          <Button onClick={() => { loadCandidates(); setShowSignatureModal(true); }}>
            Send Signatures
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Policy Content */}
        <div className="lg:col-span-2 space-y-6">
          <GlassCard className="p-8">
            <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
               <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-widest">Policy Content</h2>
               <span className={`px-2.5 py-0.5 rounded-full text-[10px] uppercase tracking-wider font-medium border ${policy.status === 'active' ? 'bg-emerald-900/20 text-emerald-400 border-emerald-900/50' : 'bg-zinc-800/80 text-zinc-400 border-zinc-700'}`}>
                  {policy.status}
               </span>
            </div>
            
            <div className="prose prose-invert max-w-none">
               <div className="bg-zinc-950/50 border border-zinc-800 rounded-lg p-6 text-zinc-300 text-sm font-serif leading-relaxed whitespace-pre-wrap min-h-[400px]">
                  {policy.content}
               </div>
            </div>
          </GlassCard>
        </div>

        {/* Sidebar Info & Signatures */}
        <div className="space-y-8">
          <GlassCard className="p-6 space-y-6">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-widest border-b border-white/5 pb-4">Overview</h2>
            <div className="space-y-4">
               <div>
                  <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Company</label>
                  <p className="text-sm text-white">{policy.company_name}</p>
               </div>
               <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Created</label>
                    <p className="text-xs text-zinc-300 font-mono">{new Date(policy.created_at).toLocaleDateString()}</p>
                  </div>
                  <div>
                    <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Updated</label>
                    <p className="text-xs text-zinc-300 font-mono">{new Date(policy.updated_at).toLocaleDateString()}</p>
                  </div>
               </div>
               {policy.description && (
                 <div className="pt-4 border-t border-white/5">
                    <label className="text-[10px] text-zinc-500 uppercase tracking-widest block mb-1">Description</label>
                    <p className="text-xs text-zinc-400 leading-relaxed italic">{policy.description}</p>
                 </div>
               )}
            </div>
          </GlassCard>

          <GlassCard className="flex flex-col">
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
               <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-widest">Signatures</h2>
               <div className="text-[10px] font-mono text-zinc-500">{signatures.length} TOTAL</div>
            </div>
            
            <div className="max-h-[500px] overflow-y-auto divide-y divide-white/5">
               {signatures.length === 0 ? (
                 <div className="p-12 text-center">
                    <Mail className="w-8 h-8 text-zinc-800 mx-auto mb-3" />
                    <p className="text-xs text-zinc-600 uppercase tracking-widest">No requests sent</p>
                 </div>
               ) : (
                 signatures.map((sig) => (
                   <div key={sig.id} className="p-4 hover:bg-white/5 transition-colors group">
                      <div className="flex items-start justify-between mb-2">
                         <div>
                            <div className="text-sm font-medium text-zinc-200">{sig.signer_name}</div>
                            <div className="text-[10px] text-zinc-500 font-mono">{sig.signer_email}</div>
                         </div>
                         <span className={`px-2 py-0.5 rounded text-[9px] uppercase tracking-wider font-medium border ${statusColors[sig.status as keyof typeof statusColors]}`}>
                            {sig.status}
                         </span>
                      </div>
                      <div className="flex items-center justify-between mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
                         <div className="text-[9px] text-zinc-600 uppercase tracking-tighter">
                            {sig.signed_at ? `Signed ${new Date(sig.signed_at).toLocaleDateString()}` : `Expires ${new Date(sig.expires_at).toLocaleDateString()}`}
                         </div>
                         <div className="flex gap-2">
                            {sig.status === 'pending' && (
                              <>
                                <button onClick={() => handleResendSignature(sig.id)} className="text-[9px] text-zinc-400 hover:text-white uppercase tracking-widest font-bold">Resend</button>
                                <button onClick={() => handleCancelSignature(sig.id)} className="text-[9px] text-zinc-600 hover:text-rose-400 uppercase tracking-widest font-bold">Cancel</button>
                              </>
                            )}
                         </div>
                      </div>
                   </div>
                 ))
               )}
            </div>
          </GlassCard>
        </div>
      </div>

      {showSignatureModal && (
        <Modal
          isOpen={showSignatureModal}
          onClose={() => setShowSignatureModal(false)}
          title="Send Signature Requests"
        >
          <div className="space-y-6">
            {/* CSV & Bulk Section */}
            <div className="grid grid-cols-1 gap-4">
               <div className="flex items-center justify-between">
                  <Button variant="secondary" size="sm" onClick={() => setShowCandidateSelector(!showCandidateSelector)}>
                    {showCandidateSelector ? 'Hide Candidates' : 'Select from Candidates'}
                  </Button>
                  <label className="text-[10px] text-blue-400 hover:text-blue-300 cursor-pointer flex items-center gap-1 uppercase tracking-widest font-bold">
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
                              const lines = text.split(/[\r\n]+/);
                              const newSigners: SignatureRequest[] = [];
                              
                              lines.forEach(line => {
                                const parsed = parseRecipient(line);
                                if (parsed) {
                                  newSigners.push({ ...parsed, type: 'external' });
                                }
                              });

                              if (newSigners.length > 0) {
                              const uniqueNewSigners = newSigners.filter(ns => !signers.some(existing => existing.email === ns.email));
                              if (uniqueNewSigners.length > 0) {
                                if (signers.length === 1 && !signers[0].email) { setSigners(uniqueNewSigners); }
                                else { setSigners([...signers, ...uniqueNewSigners]); }
                              }
                            }
                          };
                          reader.readAsText(file);
                        }
                        e.target.value = '';
                      }}
                    />
                    <Upload className="w-3 h-3" /> Upload CSV
                  </label>
               </div>

               {showCandidateSelector && (
                <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-lg max-h-48 overflow-y-auto shadow-inner">
                  {candidateList.length === 0 ? (
                    <p className="text-xs text-zinc-600 text-center py-4 font-mono">NO CANDIDATES FOUND</p>
                  ) : (
                    <div className="space-y-1">
                      {candidateList.map((candidate) => {
                        const isSelected = signers.some(s => s.email === candidate.email);
                        return (
                          <button
                            key={candidate.id}
                            onClick={() => handleCandidateSelect(candidate)}
                            disabled={isSelected}
                            className={`w-full text-left px-3 py-2 rounded text-xs transition-colors font-mono ${isSelected ? 'bg-emerald-900/10 text-emerald-500 cursor-default' : 'bg-zinc-900 text-zinc-400 hover:bg-zinc-800'}`}
                          >
                            <span>{candidate.name}</span>
                            <span className="text-zinc-600 ml-2">[{candidate.email}]</span>
                            {isSelected && <span className="float-right">SELECTED</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              <textarea 
                className="w-full px-4 py-3 bg-zinc-950 border border-zinc-800 text-white text-xs font-mono focus:outline-none focus:border-zinc-600 rounded-md h-24 placeholder:text-zinc-700"
                placeholder="Paste emails (newline or comma separated)..."
                onBlur={(e) => {
                  const text = e.target.value;
                  if (!text.trim()) return;
                  
                  // Split by newlines first
                  const lines = text.split(/[\r\n]+/);
                  const newSigners: SignatureRequest[] = [];
                  
                  lines.forEach(line => {
                    const parsed = parseRecipient(line);
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
              <p className="text-[10px] text-zinc-500 mt-2 font-mono">
                Supports: "email@co.com", "Name, email@co.com", or "Name &lt;email@co.com&gt;"
              </p>
            </div>

            {/* Individual Signer Entries */}
            <div className="border-t border-white/5 pt-6 space-y-4 max-h-[300px] overflow-y-auto pr-2">
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">Review Recipients ({signers.filter(s => s.email).length})</h3>
              {signers.map((signer, index) => (
                <div key={index} className="p-4 bg-zinc-950 border border-zinc-800 rounded-lg relative group">
                  <button
                    onClick={() => handleRemoveSigner(index)}
                    className="absolute top-2 right-2 p-1 text-zinc-700 hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="text-[9px] uppercase tracking-widest text-zinc-600">Full Name</label>
                      <input
                        type="text"
                        value={signer.name}
                        onChange={(e) => handleSignerChange(index, 'name', e.target.value)}
                        className="w-full bg-transparent border-b border-zinc-800 text-xs text-white focus:outline-none focus:border-zinc-600 pb-1"
                        placeholder="John Doe"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-[9px] uppercase tracking-widest text-zinc-600">Email Address</label>
                      <input
                        type="email"
                        value={signer.email}
                        onChange={(e) => handleSignerChange(index, 'email', e.target.value)}
                        className="w-full bg-transparent border-b border-zinc-800 text-xs text-white focus:outline-none focus:border-zinc-600 pb-1"
                        placeholder="john@example.com"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex flex-col gap-3 pt-4 border-t border-white/5">
              <Button variant="secondary" onClick={handleAddSigner} className="w-full">
                Add Another Signer
              </Button>
              <div className="flex gap-3 mt-2">
                <Button variant="outline" onClick={() => setShowSignatureModal(false)} className="flex-1">
                  Cancel
                </Button>
                <Button onClick={handleSendSignatures} className="flex-1">
                  Send Requests
                </Button>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default PolicyDetail;