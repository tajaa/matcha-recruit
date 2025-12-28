import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  openings,
  positions as positionsApi,
  type TrackedCompany,
  type TrackedCompanyJob,
  type JobSource,
  type ScrapedJob,
  type SavedOpening,
} from '../api/client';
import { Button, Card, CardContent, CompanySelectModal } from '../components';

type ViewMode = 'tracked' | 'discover' | 'saved';

export function Openings() {
  const navigate = useNavigate();
  const [viewMode, setViewMode] = useState<ViewMode>('tracked');

  // Convert to position state
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [convertingOpeningId, setConvertingOpeningId] = useState<string | null>(null);
  const [isConverting, setIsConverting] = useState(false);

  // Job board toggle state
  const [togglingJobBoard, setTogglingJobBoard] = useState<Set<string>>(new Set());

  // Tracked companies state
  const [trackedCompanies, setTrackedCompanies] = useState<TrackedCompany[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<TrackedCompany | null>(null);
  const [companyJobs, setCompanyJobs] = useState<TrackedCompanyJob[]>([]);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [addingCompany, setAddingCompany] = useState(false);
  const [newCompanyName, setNewCompanyName] = useState('');
  const [newCompanyUrl, setNewCompanyUrl] = useState('');

  // Discover state
  const [sources, setSources] = useState<JobSource[]>([]);
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [discoverQuery, setDiscoverQuery] = useState('');
  const [discoverLocation, setDiscoverLocation] = useState('');
  const [discoverJobs, setDiscoverJobs] = useState<ScrapedJob[]>([]);
  const [searching, setSearching] = useState(false);

  // Saved state
  const [savedOpenings, setSavedOpenings] = useState<SavedOpening[]>([]);
  const [savedUrls, setSavedUrls] = useState<Set<string>>(new Set());
  const [loadingSaved, setLoadingSaved] = useState(false);

  const [error, setError] = useState<string | null>(null);

  // Load initial data
  useEffect(() => {
    loadTrackedCompanies();
    loadSources();
    loadSavedUrls();
  }, []);

  // Load data when switching tabs
  useEffect(() => {
    if (viewMode === 'saved') {
      loadSavedOpenings();
    }
  }, [viewMode]);

  const loadTrackedCompanies = async () => {
    setLoadingCompanies(true);
    try {
      const companies = await openings.listCompanies();
      setTrackedCompanies(companies);
    } catch (err) {
      console.error('Failed to load tracked companies:', err);
    } finally {
      setLoadingCompanies(false);
    }
  };

  const loadSources = async () => {
    try {
      const srcs = await openings.listSources();
      setSources(srcs);
      // Select all sources by default
      setSelectedSources(new Set(srcs.map((s) => s.id)));
    } catch (err) {
      console.error('Failed to load sources:', err);
    }
  };

  const loadSavedUrls = async () => {
    try {
      const urls = await openings.getSavedUrls();
      setSavedUrls(new Set(urls));
    } catch (err) {
      console.error('Failed to load saved URLs:', err);
    }
  };

  const loadSavedOpenings = async () => {
    setLoadingSaved(true);
    try {
      const saved = await openings.listSaved();
      setSavedOpenings(saved);
    } catch (err) {
      console.error('Failed to load saved openings:', err);
    } finally {
      setLoadingSaved(false);
    }
  };

  const handleAddCompany = async () => {
    if (!newCompanyName.trim() || !newCompanyUrl.trim()) {
      setError('Please enter both company name and career page URL');
      return;
    }

    setAddingCompany(true);
    setError(null);

    try {
      const company = await openings.addCompany({
        name: newCompanyName.trim(),
        career_url: newCompanyUrl.trim(),
      });
      setTrackedCompanies((prev) => [company, ...prev]);
      setNewCompanyName('');
      setNewCompanyUrl('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add company');
    } finally {
      setAddingCompany(false);
    }
  };

  const handleDeleteCompany = async (companyId: string) => {
    try {
      await openings.deleteCompany(companyId);
      setTrackedCompanies((prev) => prev.filter((c) => c.id !== companyId));
      if (selectedCompany?.id === companyId) {
        setSelectedCompany(null);
        setCompanyJobs([]);
      }
    } catch (err) {
      console.error('Failed to delete company:', err);
    }
  };

  const handleRefreshAll = async () => {
    setRefreshing(true);
    setError(null);

    try {
      const result = await openings.refreshCompanies();
      // Reload companies to get updated job counts
      await loadTrackedCompanies();
      // Show result
      if (result.new_jobs_found > 0) {
        setError(`Found ${result.new_jobs_found} new jobs!`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh');
    } finally {
      setRefreshing(false);
    }
  };

  const handleSelectCompany = async (company: TrackedCompany) => {
    setSelectedCompany(company);
    try {
      const jobs = await openings.getCompanyJobs(company.id);
      setCompanyJobs(jobs);
      // Mark as seen
      if (company.new_job_count > 0) {
        await openings.markCompanySeen(company.id);
        setTrackedCompanies((prev) =>
          prev.map((c) => (c.id === company.id ? { ...c, new_job_count: 0 } : c))
        );
      }
    } catch (err) {
      console.error('Failed to load company jobs:', err);
    }
  };

  const handleDiscoverSearch = async () => {
    if (selectedSources.size === 0) {
      setError('Please select at least one source');
      return;
    }

    setSearching(true);
    setError(null);

    try {
      const result = await openings.searchSources({
        sources: Array.from(selectedSources),
        query: discoverQuery || undefined,
        location: discoverLocation || undefined,
        limit: 50,
      });
      setDiscoverJobs(result.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  const handleSaveJob = async (job: ScrapedJob) => {
    try {
      await openings.save({
        title: job.title,
        company_name: job.company_name,
        location: job.location || undefined,
        department: job.department || undefined,
        apply_url: job.apply_url,
        source_url: job.source_url,
      });
      setSavedUrls((prev) => new Set(prev).add(job.apply_url));
    } catch (err) {
      console.error('Failed to save job:', err);
    }
  };

  const handleUnsave = async (opening: SavedOpening) => {
    try {
      await openings.deleteSaved(opening.id);
      setSavedUrls((prev) => {
        const next = new Set(prev);
        next.delete(opening.apply_url);
        return next;
      });
      setSavedOpenings((prev) => prev.filter((o) => o.id !== opening.id));
    } catch (err) {
      console.error('Failed to unsave:', err);
    }
  };

  const toggleSource = (sourceId: string) => {
    setSelectedSources((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) {
        next.delete(sourceId);
      } else {
        next.add(sourceId);
      }
      return next;
    });
  };

  const handleConvertToPosition = (openingId: string) => {
    setConvertingOpeningId(openingId);
    setShowConvertModal(true);
  };

  const handleToggleJobBoard = async (opening: SavedOpening) => {
    if (togglingJobBoard.has(opening.id)) return;

    setTogglingJobBoard(prev => new Set(prev).add(opening.id));
    try {
      const newValue = !(opening as any).show_on_job_board;
      await openings.toggleJobBoard(opening.id, newValue);
      setSavedOpenings(prev => prev.map(o =>
        o.id === opening.id ? { ...o, show_on_job_board: newValue } as any : o
      ));
    } catch (err) {
      console.error('Failed to toggle job board:', err);
      setError(err instanceof Error ? err.message : 'Failed to update job board status');
    } finally {
      setTogglingJobBoard(prev => {
        const next = new Set(prev);
        next.delete(opening.id);
        return next;
      });
    }
  };

  const handleConvertConfirm = async (companyId: string) => {
    if (!convertingOpeningId) return;

    setIsConverting(true);
    try {
      const position = await positionsApi.createFromSavedOpening(convertingOpeningId, companyId);
      setShowConvertModal(false);
      setConvertingOpeningId(null);
      navigate(`/app/positions/${position.id}`);
    } catch (err) {
      console.error('Failed to convert opening:', err);
      setError(err instanceof Error ? err.message : 'Failed to convert opening to position');
    } finally {
      setIsConverting(false);
    }
  };

  const totalNewJobs = trackedCompanies.reduce((sum, c) => sum + c.new_job_count, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-sm tracking-[0.2em] uppercase text-matcha-500 mb-1">Openings</h1>
          <p className="text-[10px] tracking-wide text-zinc-600">
            Track companies and discover jobs from niche sources
          </p>
        </div>

        {/* Tab Toggle */}
        <div className="flex gap-1">
          <button
            onClick={() => setViewMode('tracked')}
            className={`px-3 py-1.5 text-[10px] tracking-[0.1em] uppercase transition-all ${
              viewMode === 'tracked'
                ? 'text-matcha-400 bg-matcha-500/10 border border-matcha-500/30'
                : 'text-zinc-500 border border-zinc-800 hover:border-zinc-700'
            }`}
          >
            Tracked {totalNewJobs > 0 && <span className="ml-1 text-matcha-400">({totalNewJobs})</span>}
          </button>
          <button
            onClick={() => setViewMode('discover')}
            className={`px-3 py-1.5 text-[10px] tracking-[0.1em] uppercase transition-all ${
              viewMode === 'discover'
                ? 'text-matcha-400 bg-matcha-500/10 border border-matcha-500/30'
                : 'text-zinc-500 border border-zinc-800 hover:border-zinc-700'
            }`}
          >
            Discover
          </button>
          <button
            onClick={() => setViewMode('saved')}
            className={`px-3 py-1.5 text-[10px] tracking-[0.1em] uppercase transition-all ${
              viewMode === 'saved'
                ? 'text-matcha-400 bg-matcha-500/10 border border-matcha-500/30'
                : 'text-zinc-500 border border-zinc-800 hover:border-zinc-700'
            }`}
          >
            Saved ({savedUrls.size})
          </button>
        </div>
      </div>

      {error && (
        <div className={`text-[10px] tracking-wide ${error.includes('new jobs') ? 'text-matcha-400' : 'text-red-400'}`}>
          {error}
        </div>
      )}

      {/* ========== TRACKED TAB ========== */}
      {viewMode === 'tracked' && (
        <div className="space-y-4">
          {/* Add Company Form */}
          <Card>
            <CardContent className="p-4">
              <h3 className="text-[10px] tracking-[0.15em] uppercase text-zinc-500 mb-3">
                Add Company to Track
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input
                  type="text"
                  value={newCompanyName}
                  onChange={(e) => setNewCompanyName(e.target.value)}
                  placeholder="Company name"
                  className="bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-3 py-2 placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50"
                />
                <input
                  type="url"
                  value={newCompanyUrl}
                  onChange={(e) => setNewCompanyUrl(e.target.value)}
                  placeholder="Career page URL (e.g., https://company.com/careers)"
                  className="bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-3 py-2 placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50"
                />
                <Button onClick={handleAddCompany} disabled={addingCompany}>
                  {addingCompany ? 'Adding...' : 'Add Company'}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Tracked Companies List */}
          <div className="flex items-center justify-between">
            <span className="text-[10px] tracking-wide text-zinc-500">
              {trackedCompanies.length} companies tracked
            </span>
            <Button
              onClick={handleRefreshAll}
              disabled={refreshing || trackedCompanies.length === 0}
              variant="secondary"
            >
              {refreshing ? 'Refreshing...' : 'Refresh All'}
            </Button>
          </div>

          {loadingCompanies ? (
            <Card>
              <CardContent className="p-8 text-center">
                <span className="text-zinc-500 text-xs">Loading...</span>
              </CardContent>
            </Card>
          ) : trackedCompanies.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center">
                <div className="text-zinc-600 mb-4">
                  <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                  </svg>
                </div>
                <h3 className="text-xs text-zinc-400 tracking-wide mb-2">No Companies Tracked</h3>
                <p className="text-[10px] text-zinc-600">
                  Add company career page URLs above to start tracking job openings.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Company List */}
              <div className="space-y-2">
                {trackedCompanies.map((company) => (
                  <Card
                    key={company.id}
                    className={`cursor-pointer transition-colors ${
                      selectedCompany?.id === company.id ? 'border-matcha-500/50' : ''
                    }`}
                    onClick={() => handleSelectCompany(company)}
                  >
                    <CardContent className="p-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-zinc-200">{company.name}</span>
                            {company.new_job_count > 0 && (
                              <span className="px-1.5 py-0.5 text-[9px] bg-matcha-500/20 text-matcha-400 rounded">
                                {company.new_job_count} new
                              </span>
                            )}
                          </div>
                          <div className="text-[9px] text-zinc-600 mt-1">
                            {company.job_count} jobs
                            {company.last_scraped_at && (
                              <> · Last checked {new Date(company.last_scraped_at).toLocaleDateString()}</>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteCompany(company.id);
                          }}
                          className="p-1 text-zinc-600 hover:text-red-400 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Company Jobs */}
              <Card>
                <CardContent className="p-4">
                  {selectedCompany ? (
                    <>
                      <div className="flex items-center justify-between mb-3 pb-3 border-b border-zinc-800/50">
                        <h3 className="text-xs text-zinc-200">{selectedCompany.name}</h3>
                        <a
                          href={selectedCompany.career_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[9px] text-matcha-500 hover:text-matcha-400"
                        >
                          View Career Page →
                        </a>
                      </div>
                      {companyJobs.length === 0 ? (
                        <p className="text-[10px] text-zinc-600">No jobs found. Click "Refresh All" to scrape.</p>
                      ) : (
                        <div className="space-y-2 max-h-96 overflow-y-auto">
                          {companyJobs.map((job) => (
                            <div
                              key={job.id}
                              className={`py-2 border-b border-zinc-800/30 last:border-0 ${
                                job.is_new ? 'bg-matcha-500/5' : ''
                              }`}
                            >
                              <a
                                href={job.apply_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-zinc-300 hover:text-matcha-400"
                              >
                                {job.title}
                              </a>
                              {job.location && (
                                <div className="text-[9px] text-zinc-600 mt-0.5">{job.location}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="text-[10px] text-zinc-600 text-center py-8">
                      Select a company to view its jobs
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}

      {/* ========== DISCOVER TAB ========== */}
      {viewMode === 'discover' && (
        <div className="space-y-4">
          {/* Source Selection */}
          <Card>
            <CardContent className="p-4">
              <h3 className="text-[10px] tracking-[0.15em] uppercase text-zinc-500 mb-3">
                Select Job Sources
              </h3>
              <div className="flex flex-wrap gap-2 mb-4">
                {sources.map((source) => (
                  <button
                    key={source.id}
                    onClick={() => toggleSource(source.id)}
                    className={`px-3 py-1.5 text-[10px] border transition-colors ${
                      selectedSources.has(source.id)
                        ? 'border-matcha-500/50 bg-matcha-500/10 text-matcha-400'
                        : 'border-zinc-800 text-zinc-500 hover:border-zinc-700'
                    }`}
                  >
                    {source.name}
                  </button>
                ))}
              </div>

              {/* Search Form */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <input
                  type="text"
                  value={discoverQuery}
                  onChange={(e) => setDiscoverQuery(e.target.value)}
                  placeholder="Job title or keywords"
                  className="bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-3 py-2 placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50"
                />
                <input
                  type="text"
                  value={discoverLocation}
                  onChange={(e) => setDiscoverLocation(e.target.value)}
                  placeholder="Location (optional)"
                  className="bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-3 py-2 placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50"
                />
                <Button onClick={handleDiscoverSearch} disabled={searching}>
                  {searching ? 'Searching...' : 'Search'}
                </Button>
              </div>

              {sources.length > 0 && (
                <div className="mt-3 text-[9px] text-zinc-600">
                  {sources
                    .filter((s) => selectedSources.has(s.id))
                    .map((s) => s.description)
                    .join(' · ')}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Results */}
          {discoverJobs.length > 0 && (
            <>
              <div className="text-[10px] tracking-wide text-zinc-500">
                Found <span className="text-matcha-400">{discoverJobs.length}</span> jobs
              </div>
              <div className="space-y-2">
                {discoverJobs.map((job, idx) => {
                  const isSaved = savedUrls.has(job.apply_url);
                  return (
                    <Card key={`${job.apply_url}-${idx}`}>
                      <CardContent className="p-3">
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <a
                              href={job.apply_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-zinc-300 hover:text-matcha-400 block truncate"
                            >
                              {job.title}
                            </a>
                            <div className="flex items-center gap-2 mt-1 text-[9px] text-zinc-600">
                              <span>{job.company_name}</span>
                              {job.location && (
                                <>
                                  <span>·</span>
                                  <span>{job.location}</span>
                                </>
                              )}
                              {job.salary && (
                                <>
                                  <span>·</span>
                                  <span className="text-matcha-500">{job.salary}</span>
                                </>
                              )}
                              <span className="text-zinc-700">via {job.source_name}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            <button
                              onClick={() => handleSaveJob(job)}
                              disabled={isSaved}
                              className={`p-1.5 transition-colors ${
                                isSaved ? 'text-matcha-500' : 'text-zinc-600 hover:text-matcha-400'
                              }`}
                            >
                              <svg
                                className="w-4 h-4"
                                fill={isSaved ? 'currentColor' : 'none'}
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={1.5}
                                  d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
                                />
                              </svg>
                            </button>
                            <a
                              href={job.apply_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1 text-[9px] tracking-[0.1em] uppercase text-matcha-500 border border-matcha-500/30 hover:bg-matcha-500/10 transition-colors"
                            >
                              Apply
                            </a>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </>
          )}

          {/* Empty State */}
          {discoverJobs.length === 0 && !searching && (
            <Card>
              <CardContent className="p-8 text-center">
                <div className="text-zinc-600 mb-4">
                  <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <h3 className="text-xs text-zinc-400 tracking-wide mb-2">Discover Jobs</h3>
                <p className="text-[10px] text-zinc-600 max-w-md mx-auto">
                  Search niche job boards like Poached (hospitality) and Wellfound (startups) to find jobs that Google Jobs might miss.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ========== SAVED TAB ========== */}
      {viewMode === 'saved' && (
        <>
          {loadingSaved ? (
            <Card>
              <CardContent className="p-8 text-center">
                <span className="text-zinc-500 text-xs">Loading...</span>
              </CardContent>
            </Card>
          ) : savedOpenings.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center">
                <div className="text-zinc-600 mb-4">
                  <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                  </svg>
                </div>
                <h3 className="text-xs text-zinc-400 tracking-wide mb-2">No Saved Jobs</h3>
                <p className="text-[10px] text-zinc-600">
                  Save jobs from Discover or Tracked companies to review later.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {savedOpenings.map((opening) => {
                const isPublished = (opening as any).show_on_job_board || false;
                const isTogglingBoard = togglingJobBoard.has(opening.id);

                return (
                  <Card key={opening.id}>
                    <CardContent className="p-3">
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <a
                              href={opening.apply_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-zinc-300 hover:text-matcha-400 block truncate"
                            >
                              {opening.title}
                            </a>
                            {isPublished && (
                              <span className="px-1.5 py-0.5 text-[8px] tracking-wide uppercase bg-matcha-500/20 text-matcha-400 rounded">
                                Published
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 mt-1 text-[9px] text-zinc-600">
                            <span>{opening.company_name}</span>
                            {opening.location && (
                              <>
                                <span>·</span>
                                <span>{opening.location}</span>
                              </>
                            )}
                            {opening.industry && (
                              <>
                                <span>·</span>
                                <span>{opening.industry}</span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-4">
                          {/* Publish to Job Board button */}
                          <button
                            onClick={() => handleToggleJobBoard(opening)}
                            disabled={isTogglingBoard}
                            className={`p-1.5 transition-colors ${
                              isPublished
                                ? 'text-matcha-400 hover:text-matcha-300'
                                : 'text-zinc-600 hover:text-matcha-400'
                            } ${isTogglingBoard ? 'opacity-50 cursor-not-allowed' : ''}`}
                            title={isPublished ? 'Remove from Job Board' : 'Publish to Job Board'}
                          >
                            {isTogglingBoard ? (
                              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                              </svg>
                            ) : (
                              <svg className="w-4 h-4" fill={isPublished ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                            )}
                          </button>
                          {/* Convert to Position button */}
                          <button
                            onClick={() => handleConvertToPosition(opening.id)}
                            className="p-1.5 text-violet-400 hover:text-violet-300 transition-colors"
                            title="Convert to Position"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => handleUnsave(opening)}
                            className="p-1.5 text-amber-500 hover:text-red-400 transition-colors"
                            title="Remove from Saved"
                          >
                            <svg className="w-4 h-4" fill="currentColor" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                            </svg>
                          </button>
                          <a
                            href={opening.apply_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-3 py-1 text-[9px] tracking-[0.1em] uppercase text-matcha-500 border border-matcha-500/30 hover:bg-matcha-500/10 transition-colors"
                          >
                            Apply
                          </a>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Convert to Position Modal */}
      <CompanySelectModal
        isOpen={showConvertModal}
        onClose={() => {
          setShowConvertModal(false);
          setConvertingOpeningId(null);
        }}
        onSelect={handleConvertConfirm}
        title="Convert to Position"
        isLoading={isConverting}
      />
    </div>
  );
}

export default Openings;
