import { useState } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { FileText, ListChecks, BarChart3, Target, Send } from 'lucide-react';

interface OfferLetter {
  id: string;
  candidate_name: string;
  position_title: string;
  company_name: string;
  status: 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired';
  created_at: string;
  sent_at?: string;
  expiration_date?: string;
  salary?: string;
  bonus?: string;
  stock_options?: string;
  start_date?: string;
  employment_type?: string;
  location?: string;
  benefits?: string;
  manager_name?: string;
  manager_title?: string;
}

export function OfferLetters() {
  const [offerLetters] = useState<OfferLetter[]>([
    {
      id: '1',
      candidate_name: 'Sarah Anderson',
      position_title: 'Senior Software Engineer',
      company_name: 'Matcha Tech, Inc.',
      status: 'draft',
      created_at: new Date().toISOString(),
      expiration_date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(), // 7 days from now
      salary: '$165,000',
      bonus: '15% Annual Performance Bonus',
      stock_options: '5,000 RSUs (vesting over 4 years)',
      start_date: '2026-02-15',
      employment_type: 'Full-time',
      location: 'Remote (San Francisco HQ)',
      benefits: 'Comprehensive Health, Dental, Vision, 401k with 4% match, Unlimited PTO, $2,000 Home Office Stipend',
      manager_name: 'David Chen',
      manager_title: 'VP of Engineering',
    }
  ]);
  const [selectedLetter, setSelectedLetter] = useState<OfferLetter | null>(null);
  const [isLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  const statusColors = {
    draft: 'bg-zinc-700 text-zinc-300',
    sent: 'bg-blue-900/30 text-blue-400',
    accepted: 'bg-green-900/30 text-green-400',
    rejected: 'bg-red-900/30 text-red-400',
    expired: 'bg-zinc-700 text-zinc-400',
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Offer Letters</h1>
          <p className="text-sm text-zinc-500 mt-1">Generate and manage offer letters for candidates</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            onClick={() => setShowHelp(!showHelp)}
          >
            {showHelp ? 'Hide Help' : 'Show Help'}
          </Button>
          <Button onClick={() => setShowCreateForm(true)}>Create Offer Letter</Button>
        </div>
      </div>

      {showHelp && (
        <Card>
          <div className="p-6 space-y-4">
            <h2 className="text-lg font-semibold text-white mb-4">How to Use Offer Letters</h2>
            {/* ... help content ... */}
            <div className="space-y-4">
              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-blue-400" />
                  Creating Offer Letters
                </h3>
                <p className="text-sm text-zinc-300">
                  Click "Create Offer Letter" to generate a new offer letter for a candidate.
                  Fill in candidate details, select a position, and specify compensation and
                  employment terms. The system will generate a professional offer letter.
                </p>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-yellow-400" />
                  Required Information
                </h3>
                <p className="text-sm text-zinc-300">
                  You'll need to provide:
                </p>
                <ul className="text-sm text-zinc-400 mt-2 space-y-1 ml-4">
                  <li>• Candidate name and contact information</li>
                  <li>• Position title and company details</li>
                  <li>• Salary/compensation details</li>
                  <li>• Employment type (full-time, part-time, contract)</li>
                  <li>• Start date and benefits information</li>
                </ul>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-purple-400" />
                  Managing Offers
                </h3>
                <p className="text-sm text-zinc-300">
                  Track the status of your offer letters in the dashboard. Status indicators show
                  whether offers are drafts, sent, accepted, rejected, or expired. Use this to
                  follow up with candidates and manage your hiring pipeline.
                </p>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <Target className="w-4 h-4 text-red-400" />
                  Best Practices
                </h3>
                <div className="bg-zinc-900 p-4 rounded-lg text-sm">
                  <ul className="text-zinc-300 space-y-2">
                    <li><strong>Accuracy:</strong> Double-check all compensation and benefit details</li>
                    <li><strong>Timeline:</strong> Set reasonable expiration dates for offers</li>
                    <li><strong>Follow-up:</strong> Monitor acceptance status and follow up promptly</li>
                    <li><strong>Documentation:</strong> Keep records of all offers for compliance</li>
                  </ul>
                </div>
              </div>

              <div>
                <h3 className="text-base font-medium text-white mb-2 flex items-center gap-2">
                  <Send className="w-4 h-4 text-emerald-400" />
                  Offer Letter Workflow
                </h3>
                <div className="bg-zinc-900 p-4 rounded-lg text-sm">
                  <ol className="text-zinc-300 space-y-2">
                    <li><strong>1. Gather Information:</strong> Collect candidate and position details</li>
                    <li><strong>2. Create Offer:</strong> Fill in the offer letter form with all details</li>
                    <li><strong>3. Review & Send:</strong> Preview the generated letter and send to candidate</li>
                    <li><strong>4. Track Response:</strong> Monitor acceptance/rejection status</li>
                    <li><strong>5. Follow-up:</strong> Contact candidates who haven't responded</li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {offerLetters.length === 0 && !isLoading && (
        <Card className="p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-zinc-900 flex items-center justify-center">
            <svg className="w-8 h-8 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 className="text-lg font-medium text-white mb-2">No offer letters yet</h3>
          <p className="text-sm text-zinc-500 mb-6">Create your first offer letter to get started</p>
          <Button onClick={() => setShowCreateForm(true)}>Create Offer Letter</Button>
        </Card>
      )}

      {offerLetters.length > 0 && (
        <div className="space-y-3">
          {offerLetters.map((letter) => (
            <Card 
              key={letter.id} 
              className="p-4 hover:border-zinc-700 transition-colors cursor-pointer"
              onClick={() => setSelectedLetter(letter)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-sm font-medium text-white">{letter.candidate_name}</h3>
                    <span className={`px-2 py-0.5 rounded text-[10px] tracking-wider uppercase ${statusColors[letter.status]}`}>
                      {letter.status}
                    </span>
                  </div>
                  <p className="text-sm text-zinc-400 mb-1">{letter.position_title}</p>
                  <p className="text-xs text-zinc-500">{letter.company_name}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-zinc-600">
                    {new Date(letter.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedLetter && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-2xl p-6 relative">
            <button
              onClick={() => setSelectedLetter(null)}
              className="absolute top-4 right-4 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            
            <div className="space-y-6">
              <div className="flex items-center justify-between pr-8">
                <div>
                  <h2 className="text-xl font-bold text-white">{selectedLetter.candidate_name}</h2>
                  <p className="text-sm text-zinc-500">{selectedLetter.position_title}</p>
                </div>
                <span className={`px-2 py-0.5 rounded text-[10px] tracking-wider uppercase ${statusColors[selectedLetter.status]}`}>
                  {selectedLetter.status}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="text-xs text-zinc-500 uppercase tracking-wider block mb-1">Company</label>
                  <p className="text-sm text-white">{selectedLetter.company_name}</p>
                </div>
                <div>
                  <label className="text-xs text-zinc-500 uppercase tracking-wider block mb-1">Created Date</label>
                  <p className="text-sm text-white">{new Date(selectedLetter.created_at).toLocaleDateString()}</p>
                </div>
              </div>

              <div className="bg-white rounded-lg p-8 border border-zinc-200 text-zinc-900 font-serif shadow-inner max-h-[600px] overflow-y-auto">
                <div className="space-y-8 text-[13px] leading-relaxed">
                  {/* Header */}
                  <div className="flex justify-between items-start border-b border-zinc-100 pb-6">
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
                      {selectedLetter.expiration_date && (
                        <div>
                          <p className="font-sans text-[10px] text-rose-400 uppercase tracking-widest">Expires</p>
                          <p className="font-bold text-rose-600">{new Date(selectedLetter.expiration_date).toLocaleDateString()}</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Body */}
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

              <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800">
                <Button variant="secondary" onClick={() => setSelectedLetter(null)}>Close</Button>
                {selectedLetter.status === 'draft' && (
                  <Button>Edit Offer</Button>
                )}
              </div>
            </div>
          </Card>
        </div>
      )}

      {showCreateForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-white">Create Offer Letter</h2>
              <button
                onClick={() => setShowCreateForm(false)}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form className="space-y-4">
              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Candidate Name
                </label>
                <input
                  type="text"
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700"
                  placeholder="Enter candidate name"
                />
              </div>

              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Position
                </label>
                <select className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700">
                  <option value="">Select a position</option>
                </select>
              </div>

              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Start Date
                </label>
                <input
                  type="date"
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                    Salary
                  </label>
                  <input
                    type="text"
                    className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700"
                    placeholder="$120,000"
                  />
                </div>

                <div>
                  <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                    Employment Type
                  </label>
                  <select className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700">
                    <option value="full-time">Full-time</option>
                    <option value="part-time">Part-time</option>
                    <option value="contract">Contract</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs tracking-wider uppercase text-zinc-500 mb-2">
                  Benefits
                </label>
                <textarea
                  className="w-full px-4 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-zinc-700 min-h-[100px]"
                  placeholder="Enter benefits details..."
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-zinc-800">
                <Button variant="secondary" onClick={() => setShowCreateForm(false)}>
                  Cancel
                </Button>
                <Button disabled={isLoading}>
                  {isLoading ? 'Creating...' : 'Generate Offer Letter'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}

export default OfferLetters;
