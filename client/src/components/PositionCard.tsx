import type { Position } from '../types';
import { Card } from './Card';

interface PositionCardProps {
  position: Position;
  onClick?: () => void;
  showCompany?: boolean;
}

export function PositionCard({ position, onClick, showCompany = true }: PositionCardProps) {
  const formatSalary = (min: number | null, max: number | null, currency: string) => {
    if (!min && !max) return null;
    const formatter = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    });
    if (min && max) {
      return `${formatter.format(min)} - ${formatter.format(max)}`;
    }
    if (min) return `From ${formatter.format(min)}`;
    if (max) return `Up to ${formatter.format(max)}`;
    return null;
  };

  const salaryDisplay = formatSalary(position.salary_min, position.salary_max, position.salary_currency);

  const statusColors = {
    active: 'bg-zinc-800 text-white border-zinc-700',
    closed: 'bg-zinc-700/50 text-zinc-400 border-zinc-600',
    draft: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  };

  const remotePolicyLabels = {
    remote: 'Remote',
    hybrid: 'Hybrid',
    onsite: 'On-site',
  };

  return (
    <Card
      className={`transition-all duration-200 ${onClick ? 'cursor-pointer hover:border-zinc-700 hover:shadow-lg' : ''}`}
      onClick={onClick}
    >
      <div className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-zinc-100 truncate">{position.title}</h3>
            {showCompany && position.company_name && (
              <p className="text-sm text-zinc-400 mt-0.5">{position.company_name}</p>
            )}
          </div>
          <span className={`ml-3 px-2 py-1 text-xs font-medium rounded-md border ${statusColors[position.status]}`}>
            {position.status}
          </span>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          {position.location && (
            <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              {position.location}
            </span>
          )}
          {position.remote_policy && (
            <span className="inline-flex items-center gap-1 text-xs text-zinc-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              {remotePolicyLabels[position.remote_policy]}
            </span>
          )}
          {position.employment_type && (
            <span className="inline-flex items-center text-xs text-zinc-400 capitalize">
              {position.employment_type}
            </span>
          )}
          {position.experience_level && (
            <span className="inline-flex items-center text-xs text-zinc-400 capitalize">
              {position.experience_level} level
            </span>
          )}
        </div>

        {salaryDisplay && (
          <p className="text-sm font-medium text-white mb-3">{salaryDisplay}</p>
        )}

        {position.required_skills && position.required_skills.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {position.required_skills.slice(0, 4).map(skill => (
              <span
                key={skill}
                className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-300 rounded border border-zinc-700"
              >
                {skill}
              </span>
            ))}
            {position.required_skills.length > 4 && (
              <span className="px-2 py-0.5 text-xs text-zinc-500">
                +{position.required_skills.length - 4} more
              </span>
            )}
          </div>
        )}

        {position.department && (
          <p className="text-xs text-zinc-500 mt-3">{position.department}</p>
        )}
      </div>
    </Card>
  );
}
