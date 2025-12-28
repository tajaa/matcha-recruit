import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { publicJobs } from '../api/client';
import type { PublicJobListing } from '../types';

export function PublicJobs() {
  const [jobs, setJobs] = useState<PublicJobListing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  // Filters
  const [locationFilter, setLocationFilter] = useState('');
  const [remoteOnly, setRemoteOnly] = useState(false);

  useEffect(() => {
    loadJobs();
  }, [remoteOnly]);

  const loadJobs = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await publicJobs.list({
        location: locationFilter || undefined,
        remote: remoteOnly || undefined,
        limit: 50,
      });
      setJobs(result.jobs);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    loadJobs();
  };

  const formatSalary = (min: number | null, max: number | null, currency: string) => {
    if (!min && !max) return null;
    const fmt = (n: number) => `${currency === 'USD' ? '$' : currency}${(n / 1000).toFixed(0)}k`;
    if (min && max) return `${fmt(min)} - ${fmt(max)}`;
    if (min) return `${fmt(min)}+`;
    return `Up to ${fmt(max!)}`;
  };

  const formatEmploymentType = (type: string | null) => {
    if (!type) return null;
    return type.replace('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-white overflow-hidden relative font-mono selection:bg-matcha-500 selection:text-black">
      {/* Grid background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `
              linear-gradient(to right, #22c55e 1px, transparent 1px),
              linear-gradient(to bottom, #22c55e 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px',
          }}
        />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,#09090b_70%)]" />
      </div>

      {/* Header */}
      <header className="relative z-10 flex items-center justify-between px-4 sm:px-8 py-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-2 h-2 rounded-full bg-matcha-500 shadow-[0_0_10px_rgba(34,197,94,0.8)] group-hover:scale-125 transition-transform" />
          <span className="text-xs tracking-[0.3em] uppercase text-matcha-500 font-medium">
            Matcha
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
          >
            Login
          </Link>
          <Link
            to="/register"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 border border-zinc-700 px-5 py-2 hover:border-matcha-500 hover:text-matcha-400 transition-all"
          >
            Sign Up
          </Link>
        </nav>
      </header>

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-12 max-w-5xl">
        <div className="space-y-8">
          {/* Title */}
          <div className="space-y-4">
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-white">
              Open Positions
            </h1>
            <p className="text-zinc-400 text-lg">
              {total} {total === 1 ? 'opportunity' : 'opportunities'} available
            </p>
          </div>

          {/* Filters */}
          <form onSubmit={handleSearch} className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-[10px] tracking-[0.2em] uppercase text-zinc-500 mb-2">
                Location
              </label>
              <input
                type="text"
                value={locationFilter}
                onChange={(e) => setLocationFilter(e.target.value)}
                placeholder="e.g., San Francisco, Remote"
                className="w-full bg-zinc-900/50 border border-zinc-800 px-4 py-2.5 text-sm text-white placeholder-zinc-600 focus:border-matcha-500 focus:outline-none transition-colors"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={remoteOnly}
                onChange={(e) => setRemoteOnly(e.target.checked)}
                className="w-4 h-4 bg-zinc-900 border-zinc-700 rounded text-matcha-500 focus:ring-matcha-500 focus:ring-offset-zinc-950"
              />
              <span className="text-sm text-zinc-400">Remote only</span>
            </label>
            <button
              type="submit"
              className="px-6 py-2.5 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors"
            >
              Search
            </button>
          </form>

          {/* Job List */}
          {loading ? (
            <div className="flex justify-center py-20">
              <div className="w-6 h-6 border-2 border-matcha-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : error ? (
            <div className="text-center py-20">
              <p className="text-red-400">{error}</p>
              <button
                onClick={loadJobs}
                className="mt-4 text-sm text-matcha-500 hover:text-matcha-400"
              >
                Try again
              </button>
            </div>
          ) : jobs.length === 0 ? (
            <div className="text-center py-20 border border-zinc-800 bg-zinc-900/30">
              <p className="text-zinc-500">No positions available at the moment</p>
              <p className="text-zinc-600 text-sm mt-2">Check back soon for new opportunities</p>
            </div>
          ) : (
            <div className="space-y-4">
              {jobs.map((job) => (
                <Link
                  key={job.id}
                  to={`/careers/${job.id}`}
                  className="block border border-zinc-800 bg-zinc-900/30 p-6 hover:border-matcha-500/50 hover:bg-zinc-900/50 transition-all group"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                    <div className="space-y-2">
                      <h2 className="text-lg font-medium text-white group-hover:text-matcha-400 transition-colors">
                        {job.title}
                      </h2>
                      <p className="text-zinc-400">{job.company_name}</p>
                      <div className="flex flex-wrap gap-3 text-sm">
                        {job.location && (
                          <span className="text-zinc-500">{job.location}</span>
                        )}
                        {job.remote_policy === 'remote' && (
                          <span className="text-matcha-500">Remote</span>
                        )}
                        {formatEmploymentType(job.employment_type) && (
                          <span className="text-zinc-500">
                            {formatEmploymentType(job.employment_type)}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col items-start sm:items-end gap-2">
                      {formatSalary(job.salary_min, job.salary_max, job.salary_currency) && (
                        <span className="text-matcha-400 font-medium">
                          {formatSalary(job.salary_min, job.salary_max, job.salary_currency)}
                        </span>
                      )}
                      <span className="text-[10px] tracking-[0.2em] uppercase text-zinc-600">
                        {new Date(job.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-zinc-800 mt-20">
        <div className="container mx-auto px-4 sm:px-8 py-8 max-w-5xl">
          <div className="flex flex-col sm:flex-row justify-between items-center gap-4 text-zinc-600 text-xs">
            <span>&copy; {new Date().getFullYear()} Matcha Recruit</span>
            <div className="flex gap-6">
              <Link to="/" className="hover:text-matcha-500 transition-colors">Home</Link>
              <Link to="/for-candidates" className="hover:text-matcha-500 transition-colors">For Candidates</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default PublicJobs;
