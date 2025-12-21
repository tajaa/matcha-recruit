import { useState, useMemo, useEffect } from 'react';
import { jobSearch } from '../api/client';
import { Button, Card, CardContent } from '../components';
import type { JobSearchResponse, JobListing, DatePostedFilter, JobEmploymentTypeFilter, SavedJob } from '../types';

type ViewMode = 'search' | 'saved';

export function JobSearch() {
  const [viewMode, setViewMode] = useState<ViewMode>('search');
  const [query, setQuery] = useState('');
  const [location, setLocation] = useState('');
  const [datePosted, setDatePosted] = useState<DatePostedFilter | ''>('');
  const [employmentType, setEmploymentType] = useState<JobEmploymentTypeFilter | ''>('');
  const [searchResult, setSearchResult] = useState<JobSearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());

  // Saved jobs state
  const [savedJobIds, setSavedJobIds] = useState<Set<string>>(new Set());
  const [savedJobs, setSavedJobs] = useState<SavedJob[]>([]);
  const [savingJobs, setSavingJobs] = useState<Set<string>>(new Set());
  const [loadingSaved, setLoadingSaved] = useState(false);

  // Client-side result filters
  const [filterKeyword, setFilterKeyword] = useState('');
  const [filterRemoteOnly, setFilterRemoteOnly] = useState(false);
  const [filterHasSalary, setFilterHasSalary] = useState(false);
  const [filterCompany, setFilterCompany] = useState('');
  const [filterScheduleType, setFilterScheduleType] = useState('');

  // Load saved job IDs on mount
  useEffect(() => {
    loadSavedJobIds();
  }, []);

  // Load saved jobs when switching to saved view
  useEffect(() => {
    if (viewMode === 'saved') {
      loadSavedJobs();
    }
  }, [viewMode]);

  const loadSavedJobIds = async () => {
    try {
      const ids = await jobSearch.getSavedIds();
      setSavedJobIds(new Set(ids));
    } catch (err) {
      console.error('Failed to load saved job IDs:', err);
    }
  };

  const loadSavedJobs = async () => {
    setLoadingSaved(true);
    try {
      const jobs = await jobSearch.listSaved();
      setSavedJobs(jobs);
    } catch (err) {
      console.error('Failed to load saved jobs:', err);
    } finally {
      setLoadingSaved(false);
    }
  };

  const handleSaveJob = async (job: JobListing) => {
    const jobKey = job.job_id || `${job.title}-${job.company_name}`;
    if (savingJobs.has(jobKey)) return;

    setSavingJobs(prev => new Set(prev).add(jobKey));
    try {
      const extensions = job.detected_extensions;
      const salary = extensions?.salary || job.extensions?.find(ext => ext.includes('$') || ext.toLowerCase().includes('year') || ext.toLowerCase().includes('hour'));

      await jobSearch.save({
        job_id: job.job_id,
        title: job.title,
        company_name: job.company_name,
        location: job.location,
        description: job.description,
        salary: salary,
        schedule_type: extensions?.schedule_type,
        work_from_home: extensions?.work_from_home || false,
        posted_at: extensions?.posted_at,
        apply_link: job.apply_links?.[0]?.link,
        thumbnail: job.thumbnail,
        extensions: job.extensions,
        job_highlights: job.job_highlights,
        apply_links: job.apply_links,
      });

      setSavedJobIds(prev => new Set(prev).add(job.job_id || jobKey));
    } catch (err) {
      console.error('Failed to save job:', err);
    } finally {
      setSavingJobs(prev => {
        const next = new Set(prev);
        next.delete(jobKey);
        return next;
      });
    }
  };

  const handleUnsaveJob = async (jobId: string) => {
    if (savingJobs.has(jobId)) return;

    setSavingJobs(prev => new Set(prev).add(jobId));
    try {
      await jobSearch.deleteSaved(jobId);
      setSavedJobIds(prev => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
      setSavedJobs(prev => prev.filter(j => j.job_id !== jobId && j.id !== jobId));
    } catch (err) {
      console.error('Failed to unsave job:', err);
    } finally {
      setSavingJobs(prev => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
    }
  };

  // Get unique companies from results for filter dropdown
  const uniqueCompanies = useMemo(() => {
    if (!searchResult?.jobs) return [];
    return [...new Set(searchResult.jobs.map(j => j.company_name))].sort();
  }, [searchResult?.jobs]);

  // Get unique schedule types from results
  const uniqueScheduleTypes = useMemo(() => {
    if (!searchResult?.jobs) return [];
    const types = new Set<string>();
    searchResult.jobs.forEach(job => {
      if (job.detected_extensions?.schedule_type) {
        types.add(job.detected_extensions.schedule_type);
      }
    });
    return [...types].sort();
  }, [searchResult?.jobs]);

  // Filter jobs client-side
  const filteredJobs = useMemo(() => {
    if (!searchResult?.jobs) return [];

    return searchResult.jobs.filter(job => {
      if (filterKeyword) {
        const keyword = filterKeyword.toLowerCase();
        const searchableText = `${job.title} ${job.company_name} ${job.description} ${job.location}`.toLowerCase();
        if (!searchableText.includes(keyword)) return false;
      }
      if (filterRemoteOnly && !job.detected_extensions?.work_from_home) return false;
      if (filterHasSalary) {
        const hasSalary = job.detected_extensions?.salary ||
          job.extensions?.some(ext => ext.includes('$') || ext.toLowerCase().includes('year') || ext.toLowerCase().includes('hour'));
        if (!hasSalary) return false;
      }
      if (filterCompany && job.company_name !== filterCompany) return false;
      if (filterScheduleType && job.detected_extensions?.schedule_type !== filterScheduleType) return false;
      return true;
    });
  }, [searchResult?.jobs, filterKeyword, filterRemoteOnly, filterHasSalary, filterCompany, filterScheduleType]);

  const clearResultFilters = () => {
    setFilterKeyword('');
    setFilterRemoteOnly(false);
    setFilterHasSalary(false);
    setFilterCompany('');
    setFilterScheduleType('');
  };

  const hasActiveResultFilters = filterKeyword || filterRemoteOnly || filterHasSalary || filterCompany || filterScheduleType;

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setError(null);
    setSearchResult(null);
    setExpandedJobs(new Set());
    clearResultFilters();

    try {
      const result = await jobSearch.search({
        query: query.trim(),
        location: location.trim() || undefined,
        date_posted: datePosted || undefined,
        employment_type: employmentType || undefined,
      });
      setSearchResult(result);
    } catch (err) {
      console.error('Job search error:', err);
      setError(err instanceof Error ? err.message : 'Job search failed. Make sure SearchAPI is configured.');
    } finally {
      setIsSearching(false);
    }
  };

  const handleLoadMore = async () => {
    if (!searchResult?.next_page_token || isLoadingMore) return;

    setIsLoadingMore(true);
    try {
      const result = await jobSearch.search({
        query: searchResult.query,
        location: searchResult.location || undefined,
        next_page_token: searchResult.next_page_token,
        date_posted: datePosted || undefined,
        employment_type: employmentType || undefined,
      });
      setSearchResult({
        ...result,
        jobs: [...searchResult.jobs, ...result.jobs],
      });
    } catch (err) {
      console.error('Load more error:', err);
    } finally {
      setIsLoadingMore(false);
    }
  };

  const toggleJobExpanded = (jobId: string) => {
    setExpandedJobs(prev => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  };

  const renderJobCard = (job: JobListing, index: number, isSavedView = false) => {
    const extensions = job.detected_extensions || {};
    const primaryApplyLink = job.apply_links?.[0]?.link;
    const jobKey = job.job_id || `job-${index}`;
    const isExpanded = expandedJobs.has(jobKey);
    const salary = extensions.salary || job.extensions?.find(ext => ext.includes('$') || ext.toLowerCase().includes('year') || ext.toLowerCase().includes('hour'));
    const isSaved = savedJobIds.has(job.job_id || jobKey);
    const isSaving = savingJobs.has(jobKey) || (job.job_id ? savingJobs.has(job.job_id) : false);

    return (
      <div key={jobKey} className="p-5 bg-zinc-800/50 rounded-lg border border-zinc-800/50 hover:border-zinc-700 transition-colors">
        <div className="flex gap-4">
          {/* Company Logo */}
          <div className="w-14 h-14 rounded-lg bg-zinc-900 flex items-center justify-center flex-shrink-0 overflow-hidden">
            {job.thumbnail ? (
              <img
                src={job.thumbnail}
                alt={job.company_name}
                className="w-full h-full object-contain"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            ) : (
              <svg className="w-6 h-6 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
            )}
          </div>

          {/* Job Details */}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold text-zinc-100 mb-0.5">{job.title}</h3>
                <div className="text-sm text-matcha-400 font-medium mb-2">{job.company_name}</div>
              </div>
              {/* Save/Unsave Button */}
              <button
                onClick={() => isSaved || isSavedView ? handleUnsaveJob(job.job_id || jobKey) : handleSaveJob(job)}
                disabled={isSaving}
                className={`flex-shrink-0 p-2 rounded-lg transition-all ${
                  isSaved || isSavedView
                    ? 'text-amber-400 bg-amber-500/15 hover:bg-amber-500/25'
                    : 'text-zinc-500 hover:text-amber-400 hover:bg-amber-500/10'
                } ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
                title={isSaved || isSavedView ? 'Remove from saved' : 'Save job'}
              >
                {isSaving ? (
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill={isSaved || isSavedView ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                  </svg>
                )}
              </button>
            </div>

            {/* Location & Meta */}
            <div className="flex flex-wrap gap-3 mb-3 text-xs text-zinc-500">
              {job.location && (
                <div className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {job.location}
                </div>
              )}
              {extensions.posted_at && (
                <div className="flex items-center gap-1">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {extensions.posted_at}
                </div>
              )}
            </div>

            {/* Badges Row 1 - Main Info */}
            <div className="flex flex-wrap gap-2 mb-2">
              {salary && (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {salary}
                </span>
              )}
              {extensions.schedule_type && (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-400">
                  {extensions.schedule_type}
                </span>
              )}
              {extensions.work_from_home && (
                <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-violet-500/15 text-violet-400">
                  Remote
                </span>
              )}
            </div>

            {/* Badges Row 2 - Benefits */}
            {(extensions.health_insurance || extensions.dental_coverage || extensions.paid_time_off) && (
              <div className="flex flex-wrap gap-2 mb-3">
                {extensions.health_insurance && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-pink-500/15 text-pink-400 flex items-center gap-1">
                    <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                    Health Insurance
                  </span>
                )}
                {extensions.dental_coverage && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-pink-500/15 text-pink-400">
                    Dental
                  </span>
                )}
                {extensions.paid_time_off && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-yellow-500/15 text-yellow-400 flex items-center gap-1">
                    <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    PTO
                  </span>
                )}
              </div>
            )}

            {/* Description */}
            <p className={`text-sm text-zinc-400 leading-relaxed mb-3 ${isExpanded ? '' : 'line-clamp-3'}`}>
              {job.description}
            </p>

            {/* Job Highlights (expanded view) */}
            {isExpanded && job.job_highlights && job.job_highlights.length > 0 && (
              <div className="mb-4 text-sm">
                {job.job_highlights.map((section, sectionIdx) => (
                  section.items && section.items.length > 0 && (
                    <div key={sectionIdx} className="mb-3">
                      <strong className="text-zinc-200 block mb-1">{section.title}:</strong>
                      <ul className="list-disc list-inside text-zinc-400 space-y-0.5">
                        {section.items.slice(0, 5).map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap gap-2 items-center">
              {primaryApplyLink && (
                <a
                  href={primaryApplyLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-matcha-500 text-zinc-950 rounded-lg text-sm font-medium hover:bg-matcha-400 transition-colors"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  Apply
                </a>
              )}
              {job.apply_links.length > 1 && (
                <div className="flex gap-1">
                  {job.apply_links.slice(1, 4).map((link, idx) => (
                    <a
                      key={idx}
                      href={link.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2 py-1 bg-zinc-700 text-zinc-300 rounded text-[10px] font-medium hover:bg-zinc-600 transition-colors"
                      title={link.source}
                    >
                      {link.source}
                    </a>
                  ))}
                </div>
              )}
              {(job.job_highlights || job.description.length > 200) && (
                <button
                  onClick={() => toggleJobExpanded(jobKey)}
                  className="ml-auto flex items-center gap-1 px-2 py-1 text-zinc-400 hover:text-zinc-200 text-xs transition-colors"
                >
                  {isExpanded ? (
                    <>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                      </svg>
                      Less
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                      More
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderSavedJobCard = (savedJob: SavedJob, index: number) => {
    // Convert SavedJob to JobListing format for rendering
    const job: JobListing = {
      title: savedJob.title,
      company_name: savedJob.company_name,
      location: savedJob.location || '',
      description: savedJob.description || '',
      detected_extensions: {
        salary: savedJob.salary,
        schedule_type: savedJob.schedule_type,
        work_from_home: savedJob.work_from_home,
        posted_at: savedJob.posted_at,
      },
      extensions: savedJob.extensions,
      job_highlights: savedJob.job_highlights,
      apply_links: savedJob.apply_links || [],
      thumbnail: savedJob.thumbnail,
      job_id: savedJob.job_id,
    };
    return renderJobCard(job, index, true);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <svg className="w-8 h-8 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            Job Search
          </h1>
          <p className="text-zinc-400 mt-1">Search for open positions using Google Jobs</p>
        </div>
      </div>

      {/* View Toggle */}
      <div className="flex gap-2">
        <button
          onClick={() => setViewMode('search')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            viewMode === 'search'
              ? 'bg-matcha-500 text-zinc-950'
              : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300'
          }`}
        >
          Search
        </button>
        <button
          onClick={() => setViewMode('saved')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors flex items-center gap-2 ${
            viewMode === 'saved'
              ? 'bg-matcha-500 text-zinc-950'
              : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300'
          }`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
          </svg>
          Saved
          {savedJobIds.size > 0 && (
            <span className={`px-1.5 py-0.5 text-xs rounded-full ${viewMode === 'saved' ? 'bg-zinc-950/20' : 'bg-zinc-700'}`}>
              {savedJobIds.size}
            </span>
          )}
        </button>
      </div>

      {viewMode === 'search' ? (
        <>
          {/* Search Form */}
          <Card>
            <CardContent className="p-6">
              <form onSubmit={handleSearch}>
                {/* Search inputs row */}
                <div className="flex gap-3 flex-wrap mb-4">
                  <div className="flex-[2] min-w-[250px] relative">
                    <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      className="w-full pl-10 pr-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-transparent text-zinc-100 outline-none transition-all"
                      placeholder="Job title, keywords..."
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                    />
                  </div>
                  <div className="flex-1 min-w-[180px] relative">
                    <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-zinc-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <input
                      type="text"
                      className="w-full pl-10 pr-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg focus:ring-2 focus:ring-matcha-500 focus:border-transparent text-zinc-100 outline-none transition-all"
                      placeholder="Location (optional)"
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                    />
                  </div>
                </div>

                {/* Filters row */}
                <div className="flex gap-3 flex-wrap items-center">
                  <div className="flex items-center gap-2 text-zinc-500 text-sm">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                    </svg>
                    Filters:
                  </div>
                  <select
                    className="px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 text-sm outline-none focus:ring-2 focus:ring-matcha-500"
                    value={datePosted}
                    onChange={(e) => setDatePosted(e.target.value as DatePostedFilter | '')}
                  >
                    <option value="">Date Posted</option>
                    <option value="today">Today</option>
                    <option value="3days">Last 3 days</option>
                    <option value="week">Past week</option>
                    <option value="month">Past month</option>
                  </select>
                  <select
                    className="px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 text-sm outline-none focus:ring-2 focus:ring-matcha-500"
                    value={employmentType}
                    onChange={(e) => setEmploymentType(e.target.value as JobEmploymentTypeFilter | '')}
                  >
                    <option value="">Job Type</option>
                    <option value="FULLTIME">Full-time</option>
                    <option value="PARTTIME">Part-time</option>
                    <option value="CONTRACTOR">Contractor</option>
                    <option value="INTERN">Internship</option>
                  </select>
                  <Button
                    type="submit"
                    disabled={isSearching || !query.trim()}
                    className="ml-auto flex items-center gap-2"
                  >
                    {isSearching ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Searching...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                        </svg>
                        Search Jobs
                      </>
                    )}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {/* Error */}
          {error && (
            <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
              <div className="flex items-center gap-2 text-red-400">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>{error}</span>
              </div>
            </div>
          )}

          {/* Results */}
          {searchResult && (
            <Card>
              <CardContent className="p-6">
                {/* Results Header */}
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-base font-semibold text-zinc-100">
                    {filteredJobs.length === searchResult.jobs.length
                      ? `${searchResult.jobs.length} Jobs Found`
                      : `${filteredJobs.length} of ${searchResult.jobs.length} Jobs`
                    }
                    {searchResult.location && <span className="text-zinc-500 font-normal"> in {searchResult.location}</span>}
                  </h2>
                  {(datePosted || employmentType) && (
                    <div className="flex gap-2">
                      {datePosted && (
                        <span className="text-xs px-2 py-1 bg-zinc-800 rounded-full text-zinc-400">
                          {datePosted === 'today' ? 'Today' : datePosted === '3days' ? 'Last 3 days' : datePosted === 'week' ? 'Past week' : 'Past month'}
                        </span>
                      )}
                      {employmentType && (
                        <span className="text-xs px-2 py-1 bg-zinc-800 rounded-full text-zinc-400">
                          {employmentType === 'FULLTIME' ? 'Full-time' : employmentType === 'PARTTIME' ? 'Part-time' : employmentType === 'CONTRACTOR' ? 'Contractor' : 'Internship'}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Result Filters Bar */}
                <div className="mb-4 p-4 bg-zinc-900/50 rounded-lg border border-zinc-800">
                  <div className="flex items-center gap-2 mb-3 text-zinc-500 text-sm">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                    </svg>
                    <span>Filter Results</span>
                    {hasActiveResultFilters && (
                      <button
                        onClick={clearResultFilters}
                        className="ml-auto flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                      >
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        Clear filters
                      </button>
                    )}
                  </div>
                  <div className="flex gap-3 flex-wrap items-center">
                    <input
                      type="text"
                      className="flex-1 min-w-[180px] px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 text-sm outline-none focus:ring-2 focus:ring-matcha-500"
                      placeholder="Filter by keyword..."
                      value={filterKeyword}
                      onChange={(e) => setFilterKeyword(e.target.value)}
                    />
                    {uniqueCompanies.length > 1 && (
                      <select
                        className="px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 text-sm outline-none focus:ring-2 focus:ring-matcha-500"
                        value={filterCompany}
                        onChange={(e) => setFilterCompany(e.target.value)}
                      >
                        <option value="">All Companies</option>
                        {uniqueCompanies.map(company => (
                          <option key={company} value={company}>{company}</option>
                        ))}
                      </select>
                    )}
                    {uniqueScheduleTypes.length > 1 && (
                      <select
                        className="px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-zinc-100 text-sm outline-none focus:ring-2 focus:ring-matcha-500"
                        value={filterScheduleType}
                        onChange={(e) => setFilterScheduleType(e.target.value)}
                      >
                        <option value="">All Types</option>
                        {uniqueScheduleTypes.map(type => (
                          <option key={type} value={type}>{type}</option>
                        ))}
                      </select>
                    )}
                    <label className={`flex items-center gap-2 cursor-pointer text-sm px-3 py-2 rounded-lg border transition-all ${filterRemoteOnly ? 'text-violet-400 bg-violet-500/15 border-violet-500/30' : 'text-zinc-500 border-zinc-800 hover:border-zinc-700'}`}>
                      <input
                        type="checkbox"
                        checked={filterRemoteOnly}
                        onChange={(e) => setFilterRemoteOnly(e.target.checked)}
                        className="hidden"
                      />
                      Remote Only
                    </label>
                    <label className={`flex items-center gap-2 cursor-pointer text-sm px-3 py-2 rounded-lg border transition-all ${filterHasSalary ? 'text-emerald-400 bg-emerald-500/15 border-emerald-500/30' : 'text-zinc-500 border-zinc-800 hover:border-zinc-700'}`}>
                      <input
                        type="checkbox"
                        checked={filterHasSalary}
                        onChange={(e) => setFilterHasSalary(e.target.checked)}
                        className="hidden"
                      />
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      Has Salary
                    </label>
                  </div>
                </div>

                {/* Job Cards */}
                <div className="flex flex-col gap-4">
                  {filteredJobs.length > 0 ? (
                    filteredJobs.map((job, idx) => renderJobCard(job, idx))
                  ) : (
                    <div className="text-center py-8 text-zinc-500">
                      No jobs match your filters. Try adjusting your criteria.
                    </div>
                  )}
                </div>

                {/* Load More */}
                {searchResult.next_page_token && (
                  <div className="mt-6 text-center">
                    <Button
                      variant="secondary"
                      onClick={handleLoadMore}
                      disabled={isLoadingMore}
                    >
                      {isLoadingMore ? (
                        <>
                          <svg className="w-4 h-4 animate-spin mr-2" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                          </svg>
                          Loading...
                        </>
                      ) : (
                        'Load More Jobs'
                      )}
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Empty State */}
          {!searchResult && !isSearching && !error && (
            <Card>
              <CardContent className="text-center py-16">
                <svg className="w-12 h-12 mx-auto mb-4 text-violet-500 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <h3 className="text-xl font-semibold text-zinc-100 mb-2">Search for Jobs</h3>
                <p className="text-zinc-500 max-w-md mx-auto">
                  Enter a job title or keywords to search Google Jobs. Use filters to narrow down by date posted or job type.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        /* Saved Jobs View */
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-zinc-100">Saved Jobs</h2>
              {savedJobs.length > 0 && (
                <span className="text-sm text-zinc-500">{savedJobs.length} job{savedJobs.length !== 1 ? 's' : ''} saved</span>
              )}
            </div>

            {loadingSaved ? (
              <div className="text-center py-12">
                <svg className="w-8 h-8 animate-spin mx-auto text-zinc-500" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <p className="text-zinc-500 mt-4">Loading saved jobs...</p>
              </div>
            ) : savedJobs.length > 0 ? (
              <div className="flex flex-col gap-4">
                {savedJobs.map((job, idx) => renderSavedJobCard(job, idx))}
              </div>
            ) : (
              <div className="text-center py-12">
                <svg className="w-12 h-12 mx-auto mb-4 text-zinc-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                </svg>
                <h3 className="text-lg font-semibold text-zinc-100 mb-2">No Saved Jobs</h3>
                <p className="text-zinc-500 max-w-md mx-auto">
                  Search for jobs and click the bookmark icon to save them for later reference.
                </p>
                <Button
                  variant="secondary"
                  onClick={() => setViewMode('search')}
                  className="mt-4"
                >
                  Search Jobs
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
