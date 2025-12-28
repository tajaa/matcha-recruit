import { useState } from 'react';
import type { PositionMatchResult } from '../types';
import { Card } from './Card';

interface PositionMatchCardProps {
  match: PositionMatchResult;
}

export function PositionMatchCard({ match }: PositionMatchCardProps) {
  const [expanded, setExpanded] = useState(false);

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-white';
    if (score >= 60) return 'text-amber-400';
    return 'text-red-400';
  };

  const getScoreBg = (score: number) => {
    if (score >= 80) return 'bg-zinc-800 border-zinc-700';
    if (score >= 60) return 'bg-amber-500/10 border-amber-500/20';
    return 'bg-red-500/10 border-red-500/20';
  };

  const ScoreBar = ({ label, score }: { label: string; score: number }) => (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-zinc-400">{label}</span>
        <span className={getScoreColor(score)}>{score}%</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            score >= 80 ? 'bg-matcha-500' : score >= 60 ? 'bg-amber-500' : 'bg-red-500'
          }`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );

  return (
    <Card>
      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h4 className="font-semibold text-zinc-100">{match.candidate_name || 'Unknown Candidate'}</h4>
            <p className="text-xs text-zinc-500 mt-0.5">
              Matched on {new Date(match.created_at).toLocaleDateString()}
            </p>
          </div>
          <div className={`px-3 py-1.5 rounded-lg border ${getScoreBg(match.overall_score)}`}>
            <span className={`text-xl font-bold ${getScoreColor(match.overall_score)}`}>
              {match.overall_score}
            </span>
            <span className="text-xs text-zinc-500 ml-1">/ 100</span>
          </div>
        </div>

        {/* Score Breakdown */}
        <div className="space-y-3 mb-4">
          <ScoreBar label="Skills Match" score={match.skills_match_score} />
          <ScoreBar label="Experience Match" score={match.experience_match_score} />
          <ScoreBar label="Culture Fit" score={match.culture_fit_score} />
        </div>

        {/* Expand/Collapse */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm text-zinc-400 hover:text-zinc-300 transition-colors w-full"
        >
          <svg
            className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          {expanded ? 'Hide details' : 'Show details'}
        </button>

        {/* Expanded Details */}
        {expanded && (
          <div className="mt-4 pt-4 border-t border-zinc-800 space-y-4">
            {/* Skills Breakdown */}
            {match.skills_breakdown && (
              <div>
                <h5 className="text-sm font-medium text-zinc-300 mb-2">Skills Analysis</h5>
                <div className="space-y-2 text-sm">
                  {match.skills_breakdown.matched_required?.length > 0 && (
                    <div>
                      <span className="text-zinc-500">Matched Required: </span>
                      <span className="text-white">
                        {match.skills_breakdown.matched_required.join(', ')}
                      </span>
                    </div>
                  )}
                  {match.skills_breakdown.missing_required?.length > 0 && (
                    <div>
                      <span className="text-zinc-500">Missing Required: </span>
                      <span className="text-red-400">
                        {match.skills_breakdown.missing_required.join(', ')}
                      </span>
                    </div>
                  )}
                  {match.skills_breakdown.matched_preferred?.length > 0 && (
                    <div>
                      <span className="text-zinc-500">Matched Preferred: </span>
                      <span className="text-amber-400">
                        {match.skills_breakdown.matched_preferred.join(', ')}
                      </span>
                    </div>
                  )}
                  {match.skills_breakdown.reasoning && (
                    <p className="text-zinc-400 text-xs mt-2 italic">
                      {match.skills_breakdown.reasoning}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Experience Breakdown */}
            {match.experience_breakdown && (
              <div>
                <h5 className="text-sm font-medium text-zinc-300 mb-2">Experience Analysis</h5>
                <div className="grid grid-cols-2 gap-2 text-sm mb-2">
                  {match.experience_breakdown.candidate_level && (
                    <div>
                      <span className="text-zinc-500">Candidate Level: </span>
                      <span className="text-zinc-300 capitalize">{match.experience_breakdown.candidate_level}</span>
                    </div>
                  )}
                  {match.experience_breakdown.required_level && (
                    <div>
                      <span className="text-zinc-500">Required: </span>
                      <span className="text-zinc-300 capitalize">{match.experience_breakdown.required_level}</span>
                    </div>
                  )}
                </div>
                {match.experience_breakdown.reasoning && (
                  <p className="text-zinc-400 text-xs italic">
                    {match.experience_breakdown.reasoning}
                  </p>
                )}
              </div>
            )}

            {/* Culture Fit Breakdown */}
            {match.culture_fit_breakdown && (
              <div>
                <h5 className="text-sm font-medium text-zinc-300 mb-2">Culture Fit Analysis</h5>
                <div className="space-y-2 text-sm">
                  {match.culture_fit_breakdown.strengths?.length > 0 && (
                    <div>
                      <span className="text-zinc-500">Strengths: </span>
                      <span className="text-white">
                        {match.culture_fit_breakdown.strengths.join(', ')}
                      </span>
                    </div>
                  )}
                  {match.culture_fit_breakdown.concerns?.length > 0 && (
                    <div>
                      <span className="text-zinc-500">Concerns: </span>
                      <span className="text-amber-400">
                        {match.culture_fit_breakdown.concerns.join(', ')}
                      </span>
                    </div>
                  )}
                  {match.culture_fit_breakdown.reasoning && (
                    <p className="text-zinc-400 text-xs mt-2 italic">
                      {match.culture_fit_breakdown.reasoning}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Overall Reasoning */}
            {match.match_reasoning && (
              <div>
                <h5 className="text-sm font-medium text-zinc-300 mb-2">Overall Assessment</h5>
                <p className="text-sm text-zinc-400 whitespace-pre-line">
                  {match.match_reasoning}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
