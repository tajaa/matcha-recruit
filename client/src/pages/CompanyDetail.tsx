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
    return <div className="text-center py-12 text-gray-500">Loading...</div>;
  }

  if (!company) {
    return <div className="text-center py-12 text-gray-500">Company not found</div>;
  }

  const completedInterviews = interviews.filter((i) => i.status === 'completed');

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/')} className="text-gray-500 hover:text-gray-700">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{company.name}</h1>
          <p className="text-gray-500">
            {company.industry} {company.size && `• ${company.size}`}
          </p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Interviews Section */}
        <Card>
          <CardHeader className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">Culture Interviews</h2>
            <Button size="sm" onClick={() => setShowInterviewModal(true)}>
              New Interview
            </Button>
          </CardHeader>
          <CardContent>
            {interviews.length === 0 ? (
              <p className="text-gray-500 text-center py-4">No interviews yet</p>
            ) : (
              <div className="space-y-3">
                {interviews.map((interview) => (
                  <div
                    key={interview.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                  >
                    <div>
                      <p className="font-medium">
                        {interview.interviewer_name || 'Anonymous'}
                      </p>
                      <p className="text-sm text-gray-500">
                        {interview.interviewer_role || 'Unknown role'}
                      </p>
                    </div>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        interview.status === 'completed'
                          ? 'bg-matcha-100 text-matcha-800'
                          : interview.status === 'in_progress'
                          ? 'bg-yellow-100 text-yellow-800'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {interview.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {completedInterviews.length > 0 && (
              <div className="mt-4 pt-4 border-t border-gray-100">
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
          <CardHeader>
            <h2 className="text-lg font-semibold">Culture Profile</h2>
          </CardHeader>
          <CardContent>
            {company.culture_profile ? (
              <div className="space-y-4">
                <p className="text-gray-700">{company.culture_profile.culture_summary}</p>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500">Collaboration:</span>
                    <span className="ml-2 font-medium">{company.culture_profile.collaboration_style}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Pace:</span>
                    <span className="ml-2 font-medium">{company.culture_profile.pace}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Hierarchy:</span>
                    <span className="ml-2 font-medium">{company.culture_profile.hierarchy}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Remote:</span>
                    <span className="ml-2 font-medium">{company.culture_profile.remote_policy}</span>
                  </div>
                </div>
                {company.culture_profile.values.length > 0 && (
                  <div>
                    <span className="text-sm text-gray-500">Values:</span>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {company.culture_profile.values.map((value) => (
                        <span
                          key={value}
                          className="px-2 py-1 bg-matcha-50 text-matcha-700 rounded text-xs"
                        >
                          {value}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-500 text-center py-4">
                Complete interviews and aggregate to build culture profile
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Matches Section */}
      {company.culture_profile && (
        <Card>
          <CardHeader className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">Candidate Matches</h2>
            <Button size="sm" onClick={handleRunMatching} disabled={matching}>
              {matching ? 'Matching...' : 'Run Matching'}
            </Button>
          </CardHeader>
          <CardContent>
            {matches.length === 0 ? (
              <p className="text-gray-500 text-center py-4">
                No matches yet. Upload candidates and run matching.
              </p>
            ) : (
              <div className="space-y-3">
                {matches.map((match) => (
                  <div
                    key={match.id}
                    className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
                  >
                    <div className="flex-1">
                      <p className="font-medium">{match.candidate_name || 'Unknown'}</p>
                      <p className="text-sm text-gray-500 line-clamp-2">
                        {match.match_reasoning}
                      </p>
                    </div>
                    <div className="ml-4 text-center">
                      <div
                        className={`text-2xl font-bold ${
                          match.match_score >= 80
                            ? 'text-matcha-600'
                            : match.match_score >= 60
                            ? 'text-yellow-600'
                            : 'text-red-500'
                        }`}
                      >
                        {Math.round(match.match_score)}
                      </div>
                      <div className="text-xs text-gray-500">Match Score</div>
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
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Interviewer Name
            </label>
            <input
              type="text"
              value={interviewForm.interviewer_name}
              onChange={(e) =>
                setInterviewForm({ ...interviewForm, interviewer_name: e.target.value })
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-matcha-500"
              placeholder="John Smith"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
            <input
              type="text"
              value={interviewForm.interviewer_role}
              onChange={(e) =>
                setInterviewForm({ ...interviewForm, interviewer_role: e.target.value })
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-matcha-500"
              placeholder="VP of Engineering"
            />
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <Button type="button" variant="secondary" onClick={() => setShowInterviewModal(false)}>
              Cancel
            </Button>
            <Button type="submit">Start Interview</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
