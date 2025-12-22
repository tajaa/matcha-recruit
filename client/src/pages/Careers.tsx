import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { positions as positionsApi } from '../api/client';
import type { Position, ExperienceLevel, RemotePolicy } from '../types';

export function Careers() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [experienceFilter, setExperienceFilter] = useState<ExperienceLevel | ''>('');
  const [remoteFilter, setRemoteFilter] = useState<RemotePolicy | ''>('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadPositions();
  }, [experienceFilter, remoteFilter, searchQuery]);

  const loadPositions = async () => {
    try {
      setLoading(true);
      const data = await positionsApi.list({
        status: 'active',
        experience_level: experienceFilter || undefined,
        remote_policy: remoteFilter || undefined,
        search: searchQuery || undefined,
      });
      setPositions(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load positions');
    } finally {
      setLoading(false);
    }
  };

  const formatSalary = (min: number | null, max: number | null, currency: string) => {
    if (!min && !max) return null;
    const formatter = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    });
    if (min && max) return `${formatter.format(min)} - ${formatter.format(max)}`;
    if (min) return `From ${formatter.format(min)}`;
    if (max) return `Up to ${formatter.format(max)}`;
    return null;
  };

  const remotePolicyLabels = {
    remote: 'Remote',
    hybrid: 'Hybrid',
    onsite: 'On-site',
  };

  const inputClasses =
    'px-4 py-2.5 bg-zinc-950 border border-zinc-800 text-white text-sm tracking-wide placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 transition-all font-mono';

  return (
    <div>
      {/* Hero */}
      <section className="mb-8">
        <h1 className="text-3xl font-bold tracking-[-0.02em] text-white mb-2">CAREERS</h1>
        <p className="text-[11px] tracking-[0.3em] uppercase text-zinc-500 mb-4">
          Browse Open Positions
        </p>
        <p className="text-zinc-400 max-w-xl text-sm leading-relaxed">
          Find opportunities from companies using Matcha Recruit.
        </p>
      </section>

      {/* Filters */}
      <section className="mb-8 p-4 bg-zinc-900/30 border border-zinc-800">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex-1 min-w-[200px]">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search positions..."
              className={`${inputClasses} w-full`}
            />
          </div>
          <select
            value={experienceFilter}
            onChange={(e) => setExperienceFilter(e.target.value as ExperienceLevel | '')}
            className={`${inputClasses} appearance-none cursor-pointer min-w-[140px]`}
            style={{
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
              backgroundRepeat: 'no-repeat',
              backgroundPosition: 'right 12px center',
              backgroundSize: '14px',
            }}
          >
            <option value="">All Levels</option>
            <option value="entry">Entry</option>
            <option value="mid">Mid</option>
            <option value="senior">Senior</option>
            <option value="lead">Lead</option>
            <option value="executive">Executive</option>
          </select>
          <select
            value={remoteFilter}
            onChange={(e) => setRemoteFilter(e.target.value as RemotePolicy | '')}
            className={`${inputClasses} appearance-none cursor-pointer min-w-[140px]`}
            style={{
              backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2371717a'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`,
              backgroundRepeat: 'no-repeat',
              backgroundPosition: 'right 12px center',
              backgroundSize: '14px',
            }}
          >
            <option value="">All Locations</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
            <option value="onsite">On-site</option>
          </select>
          <div className="text-[10px] tracking-[0.15em] uppercase text-zinc-600">
            {positions.length} position{positions.length !== 1 ? 's' : ''}
          </div>
        </div>
      </section>

      {/* Positions List */}
      {error && (
        <div className="mb-8 p-4 border border-red-500/30 bg-red-500/5 text-red-400 text-sm">
          <span className="text-red-500 mr-2">!</span>
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
            <span className="text-[11px] tracking-[0.2em] uppercase text-zinc-500">
              Loading positions
            </span>
          </div>
        </div>
      ) : positions.length === 0 ? (
        <div className="text-center py-24">
          <div className="w-16 h-16 mx-auto mb-6 border border-zinc-800 flex items-center justify-center">
            <svg className="w-8 h-8 text-zinc-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <p className="text-[11px] tracking-[0.15em] uppercase text-zinc-600 mb-2">
            No positions available
          </p>
          <p className="text-zinc-500 text-sm">
            Check back soon for new opportunities
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {positions.map((position) => {
            const salary = formatSalary(position.salary_min, position.salary_max, position.salary_currency);

            return (
              <div
                key={position.id}
                className="relative group"
              >
                {/* Corner brackets */}
                <div className="absolute -top-1.5 -left-1.5 w-3 h-3 border-t border-l border-zinc-800 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -top-1.5 -right-1.5 w-3 h-3 border-t border-r border-zinc-800 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -bottom-1.5 -left-1.5 w-3 h-3 border-b border-l border-zinc-800 group-hover:border-zinc-700 transition-colors" />
                <div className="absolute -bottom-1.5 -right-1.5 w-3 h-3 border-b border-r border-zinc-800 group-hover:border-zinc-700 transition-colors" />

                <div className="bg-zinc-900/50 border border-zinc-800 p-6 group-hover:border-zinc-700 transition-colors">
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-start gap-4 mb-3">
                        <div>
                          <h2 className="text-lg font-semibold text-white group-hover:text-matcha-400 transition-colors">
                            {position.title}
                          </h2>
                          {position.company_name && (
                            <p className="text-sm text-matcha-500 mt-0.5">{position.company_name}</p>
                          )}
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-3 mb-4 text-[11px] tracking-wide">
                        {position.location && (
                          <span className="flex items-center gap-1.5 text-zinc-500">
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                            </svg>
                            {position.location}
                          </span>
                        )}
                        {position.remote_policy && (
                          <span className="flex items-center gap-1.5 text-zinc-500">
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                            </svg>
                            {remotePolicyLabels[position.remote_policy]}
                          </span>
                        )}
                        {position.experience_level && (
                          <span className="text-zinc-500 capitalize">
                            {position.experience_level} level
                          </span>
                        )}
                        {position.employment_type && (
                          <span className="text-zinc-500 capitalize">
                            {position.employment_type}
                          </span>
                        )}
                      </div>

                      {position.required_skills && position.required_skills.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {position.required_skills.slice(0, 5).map((skill) => (
                            <span
                              key={skill}
                              className="px-2 py-0.5 text-[10px] tracking-wide bg-zinc-800 text-zinc-400 border border-zinc-700"
                            >
                              {skill}
                            </span>
                          ))}
                          {position.required_skills.length > 5 && (
                            <span className="px-2 py-0.5 text-[10px] text-zinc-600">
                              +{position.required_skills.length - 5} more
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col items-end gap-3">
                      {salary && (
                        <span className="text-sm font-medium text-matcha-400">{salary}</span>
                      )}
                      <Link
                        to={`/app/positions/${position.id}`}
                        className="px-4 py-2 bg-matcha-500 text-black text-[10px] tracking-[0.15em] uppercase font-medium hover:bg-matcha-400 transition-all hover:shadow-[0_0_15px_rgba(34,197,94,0.3)]"
                      >
                        View Details
                      </Link>
                    </div>
                  </div>

                  {position.department && (
                    <p className="mt-4 pt-4 border-t border-zinc-800 text-[10px] tracking-wide text-zinc-600 uppercase">
                      Department: {position.department}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
