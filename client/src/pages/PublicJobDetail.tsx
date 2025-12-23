import { useState, useEffect } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { publicJobs } from '../api/client';
import type { PublicJobDetail as JobDetailType } from '../types';

export function PublicJobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<JobDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (jobId) {
      loadJob();
    }
  }, [jobId]);

  const loadJob = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await publicJobs.getDetail(jobId!);
      setJob(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load job');
    } finally {
      setLoading(false);
    }
  };

  const formatSalary = (min: number | null, max: number | null, currency: string) => {
    if (!min && !max) return null;
    const fmt = (n: number) => `${currency === 'USD' ? '$' : currency}${n.toLocaleString()}`;
    if (min && max) return `${fmt(min)} - ${fmt(max)} / year`;
    if (min) return `${fmt(min)}+ / year`;
    return `Up to ${fmt(max!)} / year`;
  };

  const formatEmploymentType = (type: string | null) => {
    if (!type) return null;
    return type.replace('-', ' ').replace(/\b\w/g, c => c.toUpperCase());
  };

  const formatExperienceLevel = (level: string | null) => {
    if (!level) return null;
    const map: Record<string, string> = {
      entry: 'Entry Level',
      mid: 'Mid Level',
      senior: 'Senior',
      lead: 'Lead / Principal',
      executive: 'Executive',
    };
    return map[level] || level;
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
            to="/careers"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-500 hover:text-matcha-400 transition-colors"
          >
            All Jobs
          </Link>
          <Link
            to="/login"
            className="text-[10px] tracking-[0.2em] uppercase text-zinc-400 border border-zinc-700 px-5 py-2 hover:border-matcha-500 hover:text-matcha-400 transition-all"
          >
            Login
          </Link>
        </nav>
      </header>

      {/* Main Content */}
      <main className="relative z-10 container mx-auto px-4 sm:px-8 py-12 max-w-4xl">
        {loading ? (
          <div className="flex justify-center py-20">
            <div className="w-6 h-6 border-2 border-matcha-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="text-center py-20">
            <p className="text-red-400">{error}</p>
            <button
              onClick={() => navigate('/careers')}
              className="mt-4 text-sm text-matcha-500 hover:text-matcha-400"
            >
              Back to all jobs
            </button>
          </div>
        ) : job ? (
          <div className="space-y-8">
            {/* Back link */}
            <Link
              to="/careers"
              className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-matcha-400 transition-colors"
            >
              <span>&larr;</span>
              <span>All positions</span>
            </Link>

            {/* Job Header */}
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                <div>
                  <h1 className="text-3xl font-bold text-white">{job.title}</h1>
                  <p className="text-xl text-zinc-400 mt-2">{job.company_name}</p>
                </div>
                <Link
                  to={`/careers/${job.id}/apply`}
                  className="inline-flex items-center justify-center px-8 py-3 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors shrink-0"
                >
                  Apply Now
                </Link>
              </div>

              {/* Quick Info */}
              <div className="flex flex-wrap gap-4 py-4 border-y border-zinc-800">
                {job.location && (
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-500">Location:</span>
                    <span className="text-white">{job.location}</span>
                  </div>
                )}
                {job.remote_policy && (
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-500">Remote:</span>
                    <span className={job.remote_policy === 'remote' ? 'text-matcha-400' : 'text-white'}>
                      {job.remote_policy.charAt(0).toUpperCase() + job.remote_policy.slice(1)}
                    </span>
                  </div>
                )}
                {formatEmploymentType(job.employment_type) && (
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-500">Type:</span>
                    <span className="text-white">{formatEmploymentType(job.employment_type)}</span>
                  </div>
                )}
                {formatExperienceLevel(job.experience_level) && (
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-500">Level:</span>
                    <span className="text-white">{formatExperienceLevel(job.experience_level)}</span>
                  </div>
                )}
                {job.department && (
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-500">Department:</span>
                    <span className="text-white">{job.department}</span>
                  </div>
                )}
              </div>

              {/* Salary */}
              {formatSalary(job.salary_min, job.salary_max, job.salary_currency) && (
                <div className="bg-zinc-900/50 border border-zinc-800 p-4">
                  <span className="text-zinc-500 text-sm">Compensation: </span>
                  <span className="text-matcha-400 text-lg font-medium">
                    {formatSalary(job.salary_min, job.salary_max, job.salary_currency)}
                  </span>
                </div>
              )}
            </div>

            {/* Job Details */}
            <div className="space-y-8">
              {/* Responsibilities */}
              {job.responsibilities && job.responsibilities.length > 0 && (
                <section className="space-y-4">
                  <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500">
                    Responsibilities
                  </h2>
                  <ul className="space-y-3">
                    {job.responsibilities.map((item, i) => (
                      <li key={i} className="flex gap-4 items-start">
                        <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-2 shrink-0" />
                        <span className="text-zinc-300">{item}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Requirements */}
              {job.requirements && job.requirements.length > 0 && (
                <section className="space-y-4">
                  <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500">
                    Requirements
                  </h2>
                  <ul className="space-y-3">
                    {job.requirements.map((item, i) => (
                      <li key={i} className="flex gap-4 items-start">
                        <span className="w-1.5 h-1.5 rounded-full bg-zinc-700 mt-2 shrink-0" />
                        <span className="text-zinc-300">{item}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Skills */}
              {((job.required_skills && job.required_skills.length > 0) ||
                (job.preferred_skills && job.preferred_skills.length > 0)) && (
                <section className="space-y-4">
                  <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500">
                    Skills
                  </h2>
                  <div className="space-y-4">
                    {job.required_skills && job.required_skills.length > 0 && (
                      <div>
                        <p className="text-zinc-500 text-sm mb-2">Required:</p>
                        <div className="flex flex-wrap gap-2">
                          {job.required_skills.map((skill, i) => (
                            <span
                              key={i}
                              className="px-3 py-1 text-sm bg-zinc-800 border border-zinc-700 text-zinc-300"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {job.preferred_skills && job.preferred_skills.length > 0 && (
                      <div>
                        <p className="text-zinc-500 text-sm mb-2">Nice to have:</p>
                        <div className="flex flex-wrap gap-2">
                          {job.preferred_skills.map((skill, i) => (
                            <span
                              key={i}
                              className="px-3 py-1 text-sm bg-zinc-900 border border-zinc-800 text-zinc-400"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </section>
              )}

              {/* Benefits */}
              {job.benefits && job.benefits.length > 0 && (
                <section className="space-y-4">
                  <h2 className="text-sm tracking-[0.2em] uppercase text-matcha-500">
                    Benefits
                  </h2>
                  <ul className="space-y-3">
                    {job.benefits.map((item, i) => (
                      <li key={i} className="flex gap-4 items-start">
                        <span className="w-1.5 h-1.5 rounded-full bg-matcha-500 mt-2 shrink-0" />
                        <span className="text-zinc-300">{item}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {/* Visa Sponsorship */}
              {job.visa_sponsorship && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-matcha-500">&#10003;</span>
                  <span className="text-zinc-400">Visa sponsorship available</span>
                </div>
              )}
            </div>

            {/* Apply CTA */}
            <div className="border-t border-zinc-800 pt-8">
              <div className="bg-zinc-900/50 border border-zinc-800 p-8 text-center">
                <h3 className="text-xl font-medium text-white mb-2">Interested in this role?</h3>
                <p className="text-zinc-400 mb-6">Submit your application and resume to be considered.</p>
                <Link
                  to={`/careers/${job.id}/apply`}
                  className="inline-flex items-center justify-center px-10 py-3 text-xs font-medium tracking-widest uppercase bg-matcha-500 text-black hover:bg-matcha-400 transition-colors"
                >
                  Apply for this position
                </Link>
              </div>
            </div>
          </div>
        ) : null}
      </main>

      {/* JSON-LD for SEO */}
      {job && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(job.json_ld) }}
        />
      )}
    </div>
  );
}
