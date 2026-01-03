import { useState } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';

interface OfferLetter {
  id: string;
  candidate_name: string;
  position_title: string;
  company_name: string;
  status: 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired';
  created_at: string;
  sent_at?: string;
}

export function OfferLetters() {
  const [offerLetters] = useState<OfferLetter[]>([]);
  const [isLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

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
        <Button onClick={() => setShowCreateForm(true)}>Create Offer Letter</Button>
      </div>

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
            <Card key={letter.id} className="p-4 hover:border-zinc-700 transition-colors">
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
