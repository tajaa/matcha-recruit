import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardHeader, CardContent, Modal } from '../components';
import { companies as companiesApi, interviews as interviewsApi, matching as matchingApi } from '../api/client';
import type { Company, Interview, MatchResult } from '../types';

export function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [company, setCompany] = useState<Company | null>(null);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [matches, setMatches] = useState<MatchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInterviewModal, setShowInterviewModal] = useState(false);
  const [showTranscriptModal, setShowTranscriptModal] = useState(false);
  const [selectedInterview, setSelectedInterview] = useState<Interview | null>(null);
  const [interviewForm, setInterviewForm] = useState({ interviewer_name: '', interviewer_role: '' });
  const [aggregating, setAggregating] = useState(false);
  const [matching, setMatching] = useState(false);

  const fetchData = async () => {
    if (!id) return;
    try {
      const [companyData, interviewsData, matchesData] = await Promise.all([
        companiesApi.get(id),
        interviewsApi.list(id),
        matchingApi.list(id).catch(() => []),
      ]);
      setCompany(companyData);
      setInterviews(interviewsData);
      setMatches(matchesData);
    } catch (err) {
      console.error('Failed to fetch data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  const handleStartInterview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    try {
      const result = await interviewsApi.create(id, interviewForm);
      setShowInterviewModal(false);
      navigate(`/interview/${result.interview_id}`);
    } catch (err) {
      console.error('Failed to create interview:', err);
    }
  };

  const handleViewTranscript = (interview: Interview) => {
    setSelectedInterview(interview);
    setShowTranscriptModal(true);
  };

  const handleAggregate = async () => {
    if (!id) return;
    setAggregating(true);
    try {
      await companiesApi.aggregateCulture(id);
      fetchData();
    } catch (err) {
      console.error('Failed to aggregate:', err);
    } finally {
      setAggregating(false);
    }
  };

  const handleRunMatching = async () => {
    if (!id) return;
    setMatching(true);
    try {
      await matchingApi.run(id);
      fetchData();
    } catch (err) {
      console.error('Failed to run matching:', err);
    } finally {
      setMatching(false);
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-zinc-500">Loading...</div>;
  }

  if (!company) {
    return <div className="text-center py-12 text-zinc-500">Company not found</div>;
  }

  const completedInterviews = interviews.filter((i) => i.status === 'completed');

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/')} className="text-zinc-500 hover:text-zinc-300 transition-colors">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">{company.name}</h1>
          <p className="text-zinc-400 mt-1">
            {company.industry} {company.size && <span className="text-zinc-600 mx-2">•</span>} {company.size}
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Interviews Section */}
        <Card>
          <CardHeader className="flex justify-between items-center border-zinc-800">
            <h2 className="text-lg font-semibold text-zinc-100">Culture Interviews</h2>
            <Button size="sm" onClick={() => setShowInterviewModal(true)}>
              New Interview
            </Button>
          </CardHeader>
          <CardContent>
            {interviews.length === 0 ? (
              <p className="text-zinc-500 text-center py-8">No interviews yet</p>
            ) : (
              <div className="space-y-3 mt-2">
                {interviews.map((interview) => (
                  <div
                    key={interview.id}
                    onClick={() => handleViewTranscript(interview)}
                    className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg border border-zinc-800/50 hover:border-zinc-600 cursor-pointer transition-colors"
                  >
                    <div>
                      <p className="font-medium text-zinc-200">
                        {interview.interviewer_name || 'Anonymous'}
                      </p>
                      <p className="text-sm text-zinc-500">
                        {interview.interviewer_role || 'Unknown role'}
                      </p>
                    </div>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                        interview.status === 'completed'
                          ? 'bg-matcha-500/10 text-matcha-400 border-matcha-500/20'
                          : interview.status === 'in_progress'
                          ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
                          : 'bg-zinc-700/50 text-zinc-400 border-zinc-700'
                      }`}
                    >
                      {interview.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {completedInterviews.length > 0 && (
              <div className="mt-6 pt-4 border-t border-zinc-800">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleAggregate}
                  disabled={aggregating}
                  className="w-full"
                >
                  {aggregating ? 'Aggregating...' : 'Aggregate Culture Profile'}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Culture Profile Section */}
        <Card>
          <CardHeader className="border-zinc-800">
            <h2 className="text-lg font-semibold text-zinc-100">Culture Profile</h2>
          </CardHeader>
          <CardContent>
            {company.culture_profile ? (
              <div className="space-y-6 mt-2">
                <p className="text-zinc-300 leading-relaxed">{company.culture_profile.culture_summary}</p>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Collaboration</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.collaboration_style}</span>
                  </div>
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Pace</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.pace}</span>
                  </div>
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Hierarchy</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.hierarchy}</span>
                  </div>
                  <div className="bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-500 block mb-1">Remote</span>
                    <span className="font-medium text-zinc-200">{company.culture_profile.remote_policy}</span>
                  </div>
                </div>
                {company.culture_profile.values.length > 0 && (
                  <div>
                    <span className="text-sm text-zinc-500 block mb-2">Values</span>
                    <div className="flex flex-wrap gap-2">
                      {company.culture_profile.values.map((value) => (
                        <span
                          key={value}
                          className="px-2.5 py-1 bg-matcha-500/10 text-matcha-400 border border-matcha-500/20 rounded-md text-xs font-medium"
                        >
                          {value}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-zinc-500 text-center py-8">
                Complete interviews and aggregate to build culture profile
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Matches Section */}
      {company.culture_profile && (
        <Card>
          <CardHeader className="flex justify-between items-center border-zinc-800">
            <h2 className="text-lg font-semibold text-zinc-100">Candidate Matches</h2>
            <Button size="sm" onClick={handleRunMatching} disabled={matching}>
              {matching ? 'Matching...' : 'Run Matching'}
            </Button>
          </CardHeader>
          <CardContent>
            {matches.length === 0 ? (
              <p className="text-zinc-500 text-center py-8">
                No matches yet. Upload candidates and run matching.
              </p>
            ) : (
              <div className="space-y-4 mt-2">
                {matches.map((match) => (
                  <div
                    key={match.id}
                    className="flex items-center justify-between p-4 bg-zinc-800/30 rounded-lg border border-zinc-800/50 hover:border-zinc-700 transition-colors"
                  >
                    <div className="flex-1 pr-4">
                      <p className="font-medium text-zinc-200 text-lg mb-1">{match.candidate_name || 'Unknown'}</p>
                      <p className="text-sm text-zinc-400 line-clamp-2 leading-relaxed">
                        {match.match_reasoning}
                      </p>
                    </div>
                    <div className="ml-4 text-center min-w-[80px]">
                      <div
                        className={`text-3xl font-bold ${
                          match.match_score >= 80
                            ? 'text-matcha-400'
                            : match.match_score >= 60
                            ? 'text-yellow-400'
                            : 'text-red-400'
                        }`}
                      >
                        {Math.round(match.match_score)}
                      </div>
                      <div className="text-xs text-zinc-500 mt-1 uppercase tracking-wide font-medium">Match Score</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Interview Modal */}
      <Modal
        isOpen={showInterviewModal}
        onClose={() => setShowInterviewModal(false)}
        title="Start Culture Interview"
      >
        <form onSubmit={handleStartInterview} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">
              Interviewer Name
            </label>
            <input
              type="text"
              value={interviewForm.interviewer_name}
              onChange={(e) =>
                setInterviewForm({ ...interviewForm, interviewer_name: e.target.value })
              }
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-transparent text-zinc-100 outline-none transition-all"
              placeholder="John Smith"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-1">Role</label>
            <input
              type="text"
              value={interviewForm.interviewer_role}
              onChange={(e) =>
                setInterviewForm({ ...interviewForm, interviewer_role: e.target.value })
              }
              className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-transparent text-zinc-100 outline-none transition-all"
              placeholder="VP of Engineering"
            />
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-zinc-800 mt-6">
            <Button type="button" variant="secondary" onClick={() => setShowInterviewModal(false)}>
              Cancel
            </Button>
            <Button type="submit">Start Interview</Button>
          </div>
        </form>
      </Modal>

      {/* Transcript Modal */}
      <Modal
        isOpen={showTranscriptModal}
        onClose={() => setShowTranscriptModal(false)}
        title={`Interview: ${selectedInterview?.interviewer_name}`}
      >
        <div className="space-y-6 max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar">
          <div>
            <h4 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-2">Transcript</h4>
            {selectedInterview?.transcript ? (
              <div className="bg-zinc-950 rounded-lg p-4 border border-zinc-800">
                <pre className="text-sm text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
                  {selectedInterview.transcript}
                </pre>
              </div>
            ) : (
              <p className="text-zinc-500 text-sm italic">No transcript available for this session.</p>
            )}
          </div>

          {selectedInterview?.raw_culture_data && (
            <div>
              <h4 className="text-sm font-semibold text-zinc-500 uppercase tracking-wider mb-2">Extracted Culture Data</h4>
              <div className="bg-zinc-800/30 rounded-lg p-4 border border-zinc-800">
                <pre className="text-xs text-matcha-400 overflow-x-auto">
                  {JSON.stringify(selectedInterview.raw_culture_data, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
        <div className="flex justify-end mt-6 pt-4 border-t border-zinc-800">
          <Button onClick={() => setShowTranscriptModal(false)} variant="secondary">
            Close
          </Button>
        </div>
      </Modal>
    </div>
  );
}
