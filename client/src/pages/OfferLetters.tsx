import { useState, useEffect, type FormEvent } from 'react';
import { Button } from '../components/Button';
import { ChevronRight } from 'lucide-react';
import { offerLetters as offerLettersApi } from '../api/client';
import type { OfferLetter, OfferLetterCreate } from '../types';

export function OfferLetters() {
  const [offerLetters, setOfferLetters] = useState<OfferLetter[]>([]);
  const [selectedLetter, setSelectedLetter] = useState<OfferLetter | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

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
      const payload = {
        ...formData,
        start_date: formData.start_date || undefined,
        expiration_date: formData.expiration_date || undefined,
      };
      
      await offerLettersApi.create(payload);
      await loadOfferLetters();
      setShowCreateForm(false);
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

  const statusColors: Record<string, string> = {
    draft: 'text-zinc-500',
    sent: 'text-blue-600',
    accepted: 'text-emerald-600',
    rejected: 'text-red-600',
    expired: 'text-zinc-400',
  };

  const statusDotColors: Record<string, string> = {
    draft: 'bg-zinc-400',
    sent: 'bg-blue-500',
    accepted: 'bg-emerald-500',
    rejected: 'bg-red-500',
    expired: 'bg-zinc-300',
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex justify-between items-start mb-12">
        <div>
          <h1 className="text-3xl font-light tracking-tight text-zinc-900">Offer Letters</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono tracking-wide uppercase">Manage & Generate Candidate Offers</p>
        </div>
        <div>
          <button
            onClick={() => setShowCreateForm(true)}
            className="px-4 py-2 bg-zinc-900 text-white text-xs font-medium hover:bg-zinc-800 uppercase tracking-wider transition-colors"
          >
            Create Offer
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center min-h-[20vh]">
           <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading...</div>
        </div>
      ) : offerLetters.length === 0 ? (
        <div className="text-center py-16 border-t border-zinc-200">
          <div className="text-xs text-zinc-500 mb-4">No offer letters generated</div>
          <button
            onClick={() => setShowCreateForm(true)}
            className="text-xs text-zinc-900 hover:text-zinc-700 font-medium uppercase tracking-wider"
          >
            Create your first offer
          </button>
        </div>
      ) : (
        <div className="space-y-1">
           {/* List Header */}
           <div className="flex items-center gap-4 py-2 text-[10px] text-zinc-500 uppercase tracking-wider border-b border-zinc-200">
             <div className="w-8"></div>
             <div className="flex-1">Candidate</div>
             <div className="w-48">Position</div>
             <div className="w-32">Status</div>
             <div className="w-32 text-right">Created</div>
             <div className="w-8"></div>
           </div>

          {offerLetters.map((letter) => (
            <div 
              key={letter.id} 
              className="group flex items-center gap-4 py-4 cursor-pointer border-b border-zinc-100 hover:bg-zinc-50 transition-colors"
              onClick={() => setSelectedLetter(letter)}
            >
              <div className="w-8 flex justify-center">
                 <div className={`w-1.5 h-1.5 rounded-full ${statusDotColors[letter.status] || 'bg-zinc-300'}`} />
              </div>
              
              <div className="flex-1">
                 <h3 className="text-sm font-medium text-zinc-900 group-hover:text-zinc-700">
                   {letter.candidate_name}
                 </h3>
                 <p className="text-xs text-zinc-500 mt-0.5">{letter.company_name}</p>
              </div>

              <div className="w-48 text-xs text-zinc-600">
                 {letter.position_title}
              </div>

              <div className={`w-32 text-xs font-medium ${statusColors[letter.status] || 'text-zinc-500'} uppercase tracking-wide text-[10px]`}>
                 {letter.status}
              </div>

              <div className="w-32 text-right text-xs text-zinc-500 font-mono">
                 {new Date(letter.created_at).toLocaleDateString()}
              </div>
              
              <div className="w-8 flex justify-center text-zinc-400 group-hover:text-zinc-600">
                 <ChevronRight className="w-4 h-4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedLetter && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/20 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="w-full max-w-4xl max-h-[90vh] flex flex-col bg-white shadow-2xl rounded-sm overflow-hidden">
             {/* Modal Header */}
             <div className="p-6 border-b border-zinc-100 flex items-center justify-between bg-zinc-50/50">
                <div>
                   <h2 className="text-xl font-light text-zinc-900">Offer Details</h2>
                   <p className="text-xs text-zinc-500 mt-1 font-mono uppercase tracking-wide">{selectedLetter.id}</p>
                </div>
                <div className="flex items-center gap-4">
                   <span className={`px-2 py-1 rounded-full text-[10px] uppercase tracking-wider font-medium ${statusColors[selectedLetter.status]} bg-zinc-100`}>
                      {selectedLetter.status}
                   </span>
                   <button
                    onClick={() => setSelectedLetter(null)}
                    className="p-2 hover:bg-zinc-100 rounded-full transition-colors text-zinc-400 hover:text-zinc-600"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
             </div>

             {/* Modal Content */}
             <div className="flex-1 overflow-y-auto p-8 bg-zinc-50/30">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                   {/* Left Sidebar: Metadata */}
                   <div className="space-y-6">
                      <div>
                         <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Candidate</label>
                         <p className="text-zinc-900 font-medium">{selectedLetter.candidate_name}</p>
                      </div>
                      <div>
                         <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Position</label>
                         <p className="text-zinc-700">{selectedLetter.position_title}</p>
                      </div>
                       <div>
                         <label className="text-[10px] text-zinc-400 uppercase tracking-widest block mb-1">Company</label>
                         <p className="text-zinc-700">{selectedLetter.company_name}</p>
                      </div>
                      
                      <div className="pt-6 border-t border-zinc-200 space-y-3">
                         <Button variant="secondary" className="w-full justify-center">Download PDF</Button>
                         {selectedLetter.status === 'draft' && (
                           <Button variant="secondary" className="w-full justify-center">Edit Offer</Button>
                         )}
                      </div>
                   </div>

                   {/* Right Content: Preview */}
                   <div className="lg:col-span-2">
                      <div className="bg-white border border-zinc-200 shadow-sm p-12 text-zinc-900 font-serif min-h-[600px] text-[13px] leading-relaxed">
                         <div className="space-y-8">
                            <div className="flex justify-between items-start border-b border-zinc-100 pb-6">
                              <div>
                                <h3 className="font-bold text-lg tracking-tight mb-1">{selectedLetter.company_name}</h3>
                                <p className="text-zinc-400 font-sans text-[10px] uppercase tracking-widest">Official Offer of Employment</p>
                              </div>
                              <div className="text-right">
                                  <p className="font-sans text-[10px] text-zinc-400 uppercase tracking-widest mb-1">Date</p>
                                  <p className="font-bold">{new Date(selectedLetter.created_at).toLocaleDateString()}</p>
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
                              <div className="bg-zinc-50 p-6 rounded border border-zinc-100 space-y-4 font-sans mt-6 mb-6">
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-400 border-b border-zinc-200 pb-2">Compensation & Terms</h4>
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
                                    <p className="text-[10px] text-zinc-400 uppercase mb-1">Equity / Options</p>
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
                                <h4 className="font-bold text-[10px] uppercase tracking-widest text-zinc-400 font-sans">Benefits Package</h4>
                                <p className="text-zinc-600 text-xs leading-relaxed">
                                  {selectedLetter.benefits || 'Standard company benefit package including health, dental, and vision insurance.'}
                                </p>
                              </div>
                            </div>

                            {/* Signature Section */}
                            <div className="mt-16 pt-8 border-t border-zinc-100 flex justify-between items-end">
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
          </div>
        </div>
      )}

      {showCreateForm && (
         <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/20 backdrop-blur-sm p-4">
            <div className="w-full max-w-2xl max-h-[90vh] bg-white shadow-2xl rounded-sm flex flex-col">
               <div className="flex items-center justify-between p-6 border-b border-zinc-100">
                  <h2 className="text-xl font-light text-zinc-900">Create Offer Letter</h2>
                  <button onClick={() => setShowCreateForm(false)} className="text-zinc-400 hover:text-zinc-600 transition-colors">
                     <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                     </svg>
                  </button>
               </div>
               
               <div className="flex-1 overflow-y-auto p-8">
                <form className="space-y-8" onSubmit={handleCreate}>
                    <div className="space-y-4">
                      <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Candidate & Role</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Candidate Name</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="Enter full name"
                            value={formData.candidate_name}
                            onChange={(e) => setFormData({...formData, candidate_name: e.target.value})}
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Role Title</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="e.g. Senior Engineer"
                            value={formData.position_title}
                            onChange={(e) => setFormData({...formData, position_title: e.target.value})}
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Start Date</label>
                          <input 
                            type="date" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                            value={formData.start_date ? new Date(formData.start_date).toISOString().split('T')[0] : ''}
                            onChange={(e) => setFormData({...formData, start_date: e.target.value})}
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Expiration Date</label>
                          <input 
                            type="date" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
                            value={formData.expiration_date ? new Date(formData.expiration_date).toISOString().split('T')[0] : ''}
                            onChange={(e) => setFormData({...formData, expiration_date: e.target.value})}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Compensation</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Annual Salary</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="e.g. $150,000"
                            value={formData.salary || ''}
                            onChange={(e) => setFormData({...formData, salary: e.target.value})}
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Bonus Potential</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="e.g. 15% Annual"
                            value={formData.bonus || ''}
                            onChange={(e) => setFormData({...formData, bonus: e.target.value})}
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Equity / Options</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="e.g. 5,000 RSUs"
                            value={formData.stock_options || ''}
                            onChange={(e) => setFormData({...formData, stock_options: e.target.value})}
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Employment Type</label>
                          <select 
                              className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors"
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
                      <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Reporting & Location</h3>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Manager Name</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="e.g. David Chen"
                            value={formData.manager_name || ''}
                            onChange={(e) => setFormData({...formData, manager_name: e.target.value})}
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Manager Title</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="e.g. VP of Engineering"
                            value={formData.manager_title || ''}
                            onChange={(e) => setFormData({...formData, manager_title: e.target.value})}
                          />
                        </div>
                        <div className="md:col-span-2">
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Location</label>
                          <input 
                            type="text" 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors" 
                            placeholder="e.g. San Francisco, CA (Hybrid)"
                            value={formData.location || ''}
                            onChange={(e) => setFormData({...formData, location: e.target.value})}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <h3 className="text-xs font-semibold text-zinc-900 uppercase tracking-wider border-b border-zinc-100 pb-2">Benefits & Details</h3>
                      <div>
                          <label className="block text-[10px] tracking-wider uppercase text-zinc-500 mb-1.5">Benefits Summary</label>
                          <textarea 
                            className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm focus:outline-none focus:border-zinc-400 focus:bg-white transition-colors h-24 resize-none"
                            placeholder="Describe benefits package..."
                            value={formData.benefits || ''}
                            onChange={(e) => setFormData({...formData, benefits: e.target.value})}
                          />
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-3 pt-6 border-t border-zinc-100">
                        <Button variant="secondary" type="button" onClick={() => setShowCreateForm(false)}>Cancel</Button>
                        <Button type="submit" disabled={isSubmitting} className="bg-zinc-900 text-white hover:bg-zinc-700">
                          {isSubmitting ? 'Generating...' : 'Generate Offer'}
                        </Button>
                    </div>
                </form>
               </div>
            </div>
         </div>
      )}
    </div>
  );
}

export default OfferLetters;