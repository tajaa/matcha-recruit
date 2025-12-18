import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import type { Position, PositionMatchResult } from '../types';
import { positions as positionsApi } from '../api/client';
import { Button, Card, CardHeader, CardContent, PositionMatchCard } from '../components';

export function PositionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [position, setPosition] = useState<Position | null>(null);
  const [matches, setMatches] = useState<PositionMatchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [matchLoading, setMatchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (id) {
      loadPosition();
      loadMatches();
    }
  }, [id]);

  const loadPosition = async () => {
    try {
      setLoading(true);
      const data = await positionsApi.get(id!);
      setPosition(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load position');
    } finally {
      setLoading(false);
    }
  };

  const loadMatches = async () => {
    try {
      const data = await positionsApi.getMatches(id!);
      setMatches(data);
    } catch (err) {
      console.error('Failed to load matches:', err);
    }
  };

  const handleRunMatching = async () => {
    try {
      setMatchLoading(true);
      await positionsApi.match(id!);
      await loadMatches();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run matching');
    } finally {
      setMatchLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this position?')) return;

    try {
      await positionsApi.delete(id!);
      navigate('/positions');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete position');
    }
  };

  const formatSalary = (min: number | null, max: number | null, currency: string) => {
    if (!min && !max) return 'Not specified';
    const formatter = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    });
    if (min && max) return `${formatter.format(min)} - ${formatter.format(max)}`;
    if (min) return `From ${formatter.format(min)}`;
    if (max) return `Up to ${formatter.format(max)}`;
    return 'Not specified';
  };

  const statusColors = {
    active: 'bg-matcha-500/10 text-matcha-400 border-matcha-500/20',
    closed: 'bg-zinc-700/50 text-zinc-400 border-zinc-600',
    draft: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-matcha-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !position) {
    return (
      <div className="text-center py-16">
        <p className="text-red-400 mb-4">{error || 'Position not found'}</p>
        <Button variant="secondary" onClick={() => navigate('/positions')}>
          Back to Positions
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link
            to="/positions"
            className="inline-flex items-center text-sm text-zinc-400 hover:text-zinc-300 mb-4"
          >
            <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Positions
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold text-white tracking-tight">{position.title}</h1>
            <span className={`px-2.5 py-1 text-xs font-medium rounded-md border ${statusColors[position.status]}`}>
              {position.status}
            </span>
          </div>
          {position.company_name && (
            <Link
              to={`/companies/${position.company_id}`}
              className="text-zinc-400 hover:text-matcha-400 transition-colors mt-1 inline-block"
            >
              {position.company_name}
            </Link>
          )}
        </div>
        <div className="flex gap-3">
          <Button variant="danger" onClick={handleDelete}>Delete</Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main Info */}
        <div className="lg:col-span-2 space-y-6">
          {/* Overview Card */}
          <Card>
            <CardHeader>
              <h2 className="text-lg font-semibold text-zinc-100">Overview</h2>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <p className="text-sm text-zinc-500 mb-1">Location</p>
                  <p className="text-zinc-200">{position.location || 'Not specified'}</p>
                </div>
                <div>
                  <p className="text-sm text-zinc-500 mb-1">Remote Policy</p>
                  <p className="text-zinc-200 capitalize">{position.remote_policy || 'Not specified'}</p>
                </div>
                <div>
                  <p className="text-sm text-zinc-500 mb-1">Employment Type</p>
                  <p className="text-zinc-200 capitalize">{position.employment_type || 'Not specified'}</p>
                </div>
                <div>
                  <p className="text-sm text-zinc-500 mb-1">Experience Level</p>
                  <p className="text-zinc-200 capitalize">{position.experience_level || 'Not specified'}</p>
                </div>
                <div>
                  <p className="text-sm text-zinc-500 mb-1">Salary Range</p>
                  <p className="text-matcha-400 font-medium">
                    {formatSalary(position.salary_min, position.salary_max, position.salary_currency)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-zinc-500 mb-1">Visa Sponsorship</p>
                  <p className="text-zinc-200">{position.visa_sponsorship ? 'Available' : 'Not available'}</p>
                </div>
                {position.department && (
                  <div>
                    <p className="text-sm text-zinc-500 mb-1">Department</p>
                    <p className="text-zinc-200">{position.department}</p>
                  </div>
                )}
                {position.reporting_to && (
                  <div>
                    <p className="text-sm text-zinc-500 mb-1">Reports To</p>
                    <p className="text-zinc-200">{position.reporting_to}</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Skills */}
          {(position.required_skills?.length || position.preferred_skills?.length) && (
            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold text-zinc-100">Skills</h2>
              </CardHeader>
              <CardContent>
                {position.required_skills && position.required_skills.length > 0 && (
                  <div className="mb-4">
                    <p className="text-sm text-zinc-500 mb-2">Required</p>
                    <div className="flex flex-wrap gap-2">
                      {position.required_skills.map(skill => (
                        <span
                          key={skill}
                          className="px-2.5 py-1 bg-matcha-500/10 text-matcha-400 rounded-md text-sm border border-matcha-500/20"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {position.preferred_skills && position.preferred_skills.length > 0 && (
                  <div>
                    <p className="text-sm text-zinc-500 mb-2">Preferred</p>
                    <div className="flex flex-wrap gap-2">
                      {position.preferred_skills.map(skill => (
                        <span
                          key={skill}
                          className="px-2.5 py-1 bg-zinc-800 text-zinc-300 rounded-md text-sm border border-zinc-700"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Requirements & Responsibilities */}
          {(position.requirements?.length || position.responsibilities?.length) && (
            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold text-zinc-100">Details</h2>
              </CardHeader>
              <CardContent>
                {position.requirements && position.requirements.length > 0 && (
                  <div className="mb-6">
                    <p className="text-sm text-zinc-500 mb-2">Requirements</p>
                    <ul className="list-disc list-inside space-y-1 text-zinc-300">
                      {position.requirements.map((req, i) => (
                        <li key={i}>{req}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {position.responsibilities && position.responsibilities.length > 0 && (
                  <div>
                    <p className="text-sm text-zinc-500 mb-2">Responsibilities</p>
                    <ul className="list-disc list-inside space-y-1 text-zinc-300">
                      {position.responsibilities.map((resp, i) => (
                        <li key={i}>{resp}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Benefits */}
          {position.benefits && position.benefits.length > 0 && (
            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold text-zinc-100">Benefits</h2>
              </CardHeader>
              <CardContent>
                <ul className="list-disc list-inside space-y-1 text-zinc-300">
                  {position.benefits.map((benefit, i) => (
                    <li key={i}>{benefit}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar - Matches */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-100">Candidate Matches</h2>
                <Button
                  size="sm"
                  onClick={handleRunMatching}
                  disabled={matchLoading}
                >
                  {matchLoading ? 'Matching...' : 'Run Matching'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {matches.length === 0 ? (
                <p className="text-zinc-500 text-sm text-center py-4">
                  No matches yet. Click "Run Matching" to find candidates.
                </p>
              ) : (
                <div className="space-y-4">
                  {matches.map(match => (
                    <PositionMatchCard key={match.id} match={match} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
