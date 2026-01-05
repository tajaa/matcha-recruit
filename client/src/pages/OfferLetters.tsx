import { useState, useEffect, FormEvent } from 'react';
import { Button } from '../components/Button';
import { GlassCard } from '../components/GlassCard';
import { FileText, BarChart3, ChevronRight } from 'lucide-react';
import { offerLetters as offerLettersApi } from '../api/client';
import type { OfferLetter, OfferLetterCreate } from '../types';

export function OfferLetters() {
  const [offerLetters, setOfferLetters] = useState<OfferLetter[]>([]);
  const [selectedLetter, setSelectedLetter] = useState<OfferLetter | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  // Form state
  const [formData, setFormData] = useState<OfferLetterCreate>({
    candidate_name: '',
    position_title: '',
    company_name: 'Matcha Tech, Inc.',
    start_date: '',
    salary: '',
    bonus: '',
    stock_options: '',
    employment_type: 'Full-time',
    location: '',
    benefits: '',
    manager_name: '',
    manager_title: '',
    expiration_date: '',
  });

  useEffect(() => {
    loadOfferLetters();
  }, []);

  async function loadOfferLetters() {
    try {
      setIsLoading(true);
      const data = await offerLettersApi.list();
      setOfferLetters(data);
    } catch (error) {
      console.error('Failed to load offer letters:', error);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (isSubmitting) return;

    try {
      setIsSubmitting(true);
      // Clean up date fields (empty string -> undefined/null)
      const payload = {
        ...formData,
        start_date: formData.start_date || undefined,
        expiration_date: formData.expiration_date || undefined,
      };
      
      await offerLettersApi.create(payload);
      await loadOfferLetters();
      setShowCreateForm(false);
      // Reset form
      setFormData({
        candidate_name: '',
        position_title: '',
        company_name: 'Matcha Tech, Inc.',
        start_date: '',
        salary: '',
        bonus: '',
        stock_options: '',
        employment_type: 'Full-time',
        location: '',
        benefits: '',
        manager_name: '',
        manager_title: '',
        expiration_date: '',
      });
    } catch (error) {
      console.error('Failed to create offer letter:', error);
    } finally {
      setIsSubmitting(false);
    }
  }

  const statusColors = {
    draft: 'bg-zinc-800/80 text-zinc-300 border-zinc-700',
    sent: 'bg-blue-900/20 text-blue-300 border-blue-900/50',
    accepted: 'bg-emerald-900/20 text-emerald-300 border-emerald-900/50',
    rejected: 'bg-red-900/20 text-red-300 border-red-900/50',
    expired: 'bg-zinc-800/80 text-zinc-400 border-zinc-700',
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-white">Offer Letters</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">Manage & Generate Candidate Offers</p>
        </div>
        <div className="flex gap-3">
          <Button
            variant="secondary"
            onClick={() => setShowHelp(!showHelp)}
          >
            {showHelp ? 'Hide Help' : 'Help'}
          </Button>
          <Button onClick={() => setShowCreateForm(true)}>Create Offer</Button>
        </div>
      </div>

      {showHelp && (
        <GlassCard className="mb-6">
          <div className="p-8 space-y-8">
             <h2 className="text-lg font-light text-white mb-6">Quick Guide</h2>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div>
                   <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-blue-400" /> Creating Offers
                   </h3>
                   <p className="text-sm text-zinc-400 leading-relaxed">
                      Generate professional offer letters by filling in candidate details, role information, and compensation terms.
                   </p>
                </div>
                 <div>
                   <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-emerald-400" /> Tracking
                   </h3>
                   <p className="text-sm text-zinc-400 leading-relaxed">
                      Monitor the status of every offer sent. See when candidates view, accept, or decline in real-time.
                   </p>
                </div>
             </div>
          </div>
        </GlassCard>
      )}

      {offerLetters.length === 0 && !isLoading && (
        <GlassCard className="p-16 text-center">
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-zinc-900/50 border border-zinc-800 flex items-center justify-center">
            <FileText className="w-8 h-8 text-zinc-700" strokeWidth={1.5} />
          </div>
          <h3 className="text-xl font-light text-white mb-2">No offers generated</h3>
          <p className="text-sm text-zinc-500 mb-8 max-w-sm mx-auto">Start your hiring process by creating your first official offer letter.</p>
          <Button onClick={() => setShowCreateForm(true)}>Create Offer Letter</Button>
        </GlassCard>
      )}

      {offerLetters.length > 0 && (
        <div className="grid grid-cols-1 gap-4">
          {offerLetters.map((letter) => (
            <GlassCard 
              key={letter.id} 
              className="group cursor-pointer"
              hoverEffect
              onClick={() => setSelectedLetter(letter)}
            >
              <div className="p-6 flex items-center justify-between">
                <div className="flex items-center gap-6">
                   <div className="w-12 h-12 rounded-full bg-zinc-800/50 border border-zinc-700/50 flex items-center justify-center text-zinc-400 font-mono text-sm">
                      {letter.candidate_name.charAt(0)}
                   </div>
                   <div>
                      <h3 className="text-lg font-medium text-white group-hover:text-blue-200 transition-colors">
                        {letter.candidate_name}
                      </h3>
                      <div className="flex items-center gap-2 mt-1">
                         <span className="text-sm text-zinc-400">{letter.position_title}</span>
                         <span className="text-zinc-600">•</span>
                         <span className="text-sm text-zinc-500">{letter.company_name}</span>
                      </div>
                   </div>
                </div>

                <div className="flex items-center gap-6">
                  <div className="text-right hidden md:block">
                     <div className="text-[10px] uppercase tracking-wider text-zinc-600 mb-1">Created</div>
                     <div className="text-sm text-zinc-400 font-mono">{new Date(letter.created_at).toLocaleDateString()}</div>
                  </div>
                  
                  <span className={`px-3 py-1 rounded-full text-[10px] uppercase tracking-wider font-medium border ${statusColors[letter.status]}`}>
                    {letter.status}
                  </span>

                  <ChevronRight className="w-5 h-5 text-zinc-700 group-hover:text-zinc-400 transition-colors" />
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedLetter && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <GlassCard className="w-full max-w-4xl max-h-[90vh] flex flex-col relative bg-zinc-950/90">
             {/* Modal Header */}
             <div className="p-6 border-b border-white/5 flex items-center justify-between">
                <div>
                   <h2 className="text-xl font-light text-white">Offer Details</h2>
                   <p className="text-sm text-zinc-500 mt-1 font-mono">{selectedLetter.id.toUpperCase()}</p>
                </div>
                <div className="flex items-center gap-4">
                   <span className={`px-3 py-1 rounded-full text-[10px] uppercase tracking-wider font-medium border ${statusColors[selectedLetter.status]}`}>
                      {selectedLetter.status}
                   </span>
                   <button
                    onClick={() => setSelectedLetter(null)}
                    className="p-2 hover:bg-white/5 rounded-full transition-colors text-zinc-400 hover:text-white"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
             </div>

             {/* Modal Content */}
             <div className="flex-1 overflow-y-auto p-8">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                   {/* Left Sidebar: Metadata */}
                   <div className="space-y-6">
                      <div>
                         <label className="text-xs text-zinc-500 uppercase tracking-widest block mb-2">Candidate</label>
                         <p className="text-white font-medium">{selectedLetter.candidate_name}</p>
                      </div>
                      <div>
                         <label className="text-xs text-zinc-500 uppercase tracking-widest block mb-2">Position</label>
                         <p className="text-zinc-300">{selectedLetter.position_title}</p>
                      </div>
                       <div>
                         <label className="text-xs text-zinc-500 uppercase tracking-widest block mb-2">Company</label>
                         <p className="text-zinc-300">{selectedLetter.company_name}</p>
                      </div>
                      
                      <div className="pt-6 border-t border-white/5">
                         <Button className="w-full mb-3">Download PDF</Button>
                         {selectedLetter.status === 'draft' && (
                           <Button variant="secondary" className="w-full">Edit Offer</Button>
                         )}
                      </div>
                   </div>

                   {/* Right Content: Preview */}
                   <div className="lg:col-span-2">
                      <div className="bg-white rounded-sm p-8 text-zinc-900 font-serif shadow-2xl min-h-[600px] text-[13px] leading-relaxed relative">
                         {/* Paper Texture/Sheen */}
                         <div className="absolute inset-0 bg-gradient-to-br from-white via-zinc-50 to-zinc-100 opacity-50 pointer-events-none" />
                         
                         <div className="relative z-10 space-y-8">
                            <div className="flex justify-between items-start border-b border-zinc-200 pb-6">
                              <div>
                                <div className="flex items-center gap-2 mb-2">
                                  <div className="w-6 h-6 bg-zinc-900 rounded-full"></div>
                                  <h3 className="font-bold text-xl tracking-tight">{selectedLetter.company_name}</h3>
                                </div>
                                <p className="text-zinc-500 font-sans text-[10px] uppercase tracking-widest">Official Offer of Employment</p>
                              </div>
                              <div className="text-right space-y-1">
                                <div>
                                  <p className="font-sans text-[10px] text-zinc-400 uppercase tracking-widest">Date</p>
                                  <p className="font-bold">{new Date(selectedLetter.created_at).toLocaleDateString()}</p>
                                </div>
                              </div>
                            </div>

                            <div className="space-y-4">
                              <p>Dear <span className="font-bold">{selectedLetter.candidate_name}</span>,</p>
                              
                              <p>
                                We are pleased to offer you the position of <span className="font-bold">{selectedLetter.position_title}</span> at <span className="font-bold">{selectedLetter.company_name}</span>. 
                                We were very impressed with your background and believe your skills and experience will be a valuable addition to our team.
                              </p>

                              <p>
                                Should you accept this offer, you will report to <span className="font-bold">{selectedLetter.manager_name || 'the Hiring Manager'}</span>
                                {selectedLetter.manager_title && <span>, {selectedLetter.manager_title}</span>}.
                              </p>

                              {/* Terms Grid */}
                              <div className="bg-zinc-50 p-6 rounded-lg border border-zinc-100 space-y-4 font-sans mt-6 mb-6">
                                <h4 className="font-bold text-[11px] uppercase tracking-widest text-zinc-500 border-b border-zinc-200 pb-2">Compensation & Terms</h4>
                                <div className="grid grid-cols-2 gap-y-6 gap-x-4">
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Annual Salary</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.salary || 'TBD'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Start Date</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.start_date ? new Date(selectedLetter.start_date).toLocaleDateString() : 'TBD'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Bonus Potential</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.bonus || 'N/A'}</p>
                                  </div>
                                   <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Equity / Stock Options</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.stock_options || 'N/A'}</p>
                                  </div>
                                  <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Employment Type</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.employment_type || 'Full-time'}</p>
                                  </div>
                                   <div>
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Location</p>
                                    <p className="font-bold text-zinc-800 text-sm">{selectedLetter.location || 'Remote'}</p>
                                  </div>
                                </div>
                              </div>

                              <div className="space-y-2">
                                <h4 className="font-bold text-[11px] uppercase tracking-widest text-zinc-500 font-sans">Benefits Package</h4>
                                <p className="text-zinc-700 bg-white p-3 border border-zinc-100 rounded">
                                  {selectedLetter.benefits || 'Standard company benefit package including health, dental, and vision insurance.'}
                                </p>
                              </div>

                              <p className="pt-4 border-t border-zinc-100">
                                We look forward to having you join us. This offer is contingent upon the successful completion of standard background checks.
                              </p>
                            </div>

                            {/* Signature Section */}
                            <div className="mt-12 pt-8 border-t border-zinc-100 flex justify-between items-end">
                              <div>
                                <div className="w-48 h-px bg-zinc-300 mb-2"></div>
                                <p className="font-bold text-zinc-900">{selectedLetter.manager_name || 'Hiring Manager'}</p>
                                <p className="font-sans text-[10px] text-zinc-400 uppercase tracking-widest">Authorized Signature</p>
                              </div>
                              <div className="text-right">
                                 <p className="font-sans text-[10px] text-zinc-400 uppercase tracking-widest mb-1">Candidate Acceptance</p>
                                 <div className="w-48 h-10 border-b border-dashed border-zinc-300 mb-1"></div>
                              </div>
                            </div>
                         </div>
                      </div>
                   </div>
                </div>
             </div>
          </GlassCard>
        </div>
      )}

      {showCreateForm && (
         <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <GlassCard className="w-full max-w-2xl max-h-[90vh] overflow-y-auto p-8">
               <div className="flex items-center justify-between mb-8 border-b border-white/5 pb-4">
                  <h2 className="text-xl font-light text-white">Create Offer Letter</h2>
                  <button onClick={() => setShowCreateForm(false)} className="text-zinc-500 hover:text-white transition-colors">
                     <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                     </svg>
                  </button>
               </div>
               
               <form className="space-y-6" onSubmit={handleCreate}>
                  <div className="space-y-4">
                    <h3 className="text-sm font-medium text-white border-b border-white/10 pb-2">Candidate & Role</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Candidate Name</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="Enter full name"
                          value={formData.candidate_name}
                          onChange={(e) => setFormData({...formData, candidate_name: e.target.value})}
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Role Title</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="e.g. Senior Engineer"
                          value={formData.position_title}
                          onChange={(e) => setFormData({...formData, position_title: e.target.value})}
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Start Date</label>
                        <input 
                          type="date" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors"
                          value={formData.start_date ? new Date(formData.start_date).toISOString().split('T')[0] : ''}
                          onChange={(e) => setFormData({...formData, start_date: e.target.value})}
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Expiration Date</label>
                        <input 
                          type="date" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors"
                          value={formData.expiration_date ? new Date(formData.expiration_date).toISOString().split('T')[0] : ''}
                          onChange={(e) => setFormData({...formData, expiration_date: e.target.value})}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <h3 className="text-sm font-medium text-white border-b border-white/10 pb-2">Compensation</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Annual Salary</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="e.g. $150,000"
                          value={formData.salary || ''}
                          onChange={(e) => setFormData({...formData, salary: e.target.value})}
                        />
                      </div>
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Bonus Potential</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="e.g. 15% Annual"
                          value={formData.bonus || ''}
                          onChange={(e) => setFormData({...formData, bonus: e.target.value})}
                        />
                      </div>
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Equity / Options</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="e.g. 5,000 RSUs"
                          value={formData.stock_options || ''}
                          onChange={(e) => setFormData({...formData, stock_options: e.target.value})}
                        />
                      </div>
                      <div>
                         <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Employment Type</label>
                         <select 
                            className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors"
                            value={formData.employment_type || 'Full-time'}
                            onChange={(e) => setFormData({...formData, employment_type: e.target.value})}
                         >
                            <option value="Full-time">Full-time</option>
                            <option value="Part-time">Part-time</option>
                            <option value="Contract">Contract</option>
                            <option value="Internship">Internship</option>
                         </select>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <h3 className="text-sm font-medium text-white border-b border-white/10 pb-2">Reporting & Location</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Manager Name</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="e.g. David Chen"
                          value={formData.manager_name || ''}
                          onChange={(e) => setFormData({...formData, manager_name: e.target.value})}
                        />
                      </div>
                      <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Manager Title</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="e.g. VP of Engineering"
                          value={formData.manager_title || ''}
                          onChange={(e) => setFormData({...formData, manager_title: e.target.value})}
                        />
                      </div>
                      <div className="md:col-span-2">
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Location</label>
                        <input 
                          type="text" 
                          className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors" 
                          placeholder="e.g. San Francisco, CA (Hybrid)"
                          value={formData.location || ''}
                          onChange={(e) => setFormData({...formData, location: e.target.value})}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4">
                     <h3 className="text-sm font-medium text-white border-b border-white/10 pb-2">Benefits & Details</h3>
                     <div>
                        <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">Benefits Summary</label>
                        <textarea 
                           className="w-full px-4 py-3 bg-zinc-950/50 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-600 rounded-md transition-colors h-24 resize-none"
                           placeholder="Describe benefits package..."
                           value={formData.benefits || ''}
                           onChange={(e) => setFormData({...formData, benefits: e.target.value})}
                        />
                     </div>
                  </div>

                   <div className="flex items-center justify-end gap-3 pt-6 border-t border-white/5">
                      <Button variant="secondary" type="button" onClick={() => setShowCreateForm(false)}>Cancel</Button>
                      <Button type="submit" disabled={isSubmitting}>
                        {isSubmitting ? 'Generating...' : 'Generate Offer'}
                      </Button>
                   </div>
               </form>
            </GlassCard>
         </div>
      )}
    </div>
  );
}

export default OfferLetters;