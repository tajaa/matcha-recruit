import { useState, useEffect, useMemo } from 'react';
import { openings, type ScrapedJob, type OpeningsSearchResponse, type SavedOpening } from '../api/client';
import { Button, Card, CardContent } from '../components';

type ViewMode = 'search' | 'saved';

export function Openings() {
  const [viewMode, setViewMode] = useState<ViewMode>('search');
  const [industries, setIndustries] = useState<string[]>([]);
  const [selectedIndustry, setSelectedIndustry] = useState('');
  const [query, setQuery] = useState('');
  const [maxSources, setMaxSources] = useState(10);
  const [searchResult, setSearchResult] = useState<OpeningsSearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Saved state
  const [savedUrls, setSavedUrls] = useState<Set<string>>(new Set());
  const [savedOpenings, setSavedOpenings] = useState<SavedOpening[]>([]);
  const [savingUrls, setSavingUrls] = useState<Set<string>>(new Set());
  const [loadingSaved, setLoadingSaved] = useState(false);

  // Client-side filters
  const [filterKeyword, setFilterKeyword] = useState('');
  const [filterCompany, setFilterCompany] = useState('');

  // Load industries and saved URLs on mount
  useEffect(() => {
    loadIndustries();
    loadSavedUrls();
  }, []);

  // Load saved openings when switching to saved view
  useEffect(() => {
    if (viewMode === 'saved') {
      loadSavedOpenings();
    }
  }, [viewMode]);

  const loadIndustries = async () => {
    try {
      const result = await openings.getIndustries();
      setIndustries(result.industries);
      if (result.industries.length > 0) {
        setSelectedIndustry(result.industries[0]);
      }
    } catch (err) {
      console.error('Failed to load industries:', err);
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

  const handleSearch = async () => {
    if (!selectedIndustry) {
      setError('Please select an industry');
      return;
    }

    setIsSearching(true);
    setError(null);
    setSearchResult(null);

    try {
      const result = await openings.search({
        industry: selectedIndustry,
        query: query || undefined,
        max_sources: maxSources,
      });
      setSearchResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setIsSearching(false);
    }
  };

  const handleSave = async (job: ScrapedJob) => {
    if (savingUrls.has(job.apply_url)) return;

    setSavingUrls((prev) => new Set(prev).add(job.apply_url));
    try {
      await openings.save({
        title: job.title,
        company_name: job.company_name,
        location: job.location || undefined,
        department: job.department || undefined,
        apply_url: job.apply_url,
        source_url: job.source_url,
        industry: selectedIndustry,
      });
      setSavedUrls((prev) => new Set(prev).add(job.apply_url));
    } catch (err) {
      console.error('Failed to save opening:', err);
    } finally {
      setSavingUrls((prev) => {
        const next = new Set(prev);
        next.delete(job.apply_url);
        return next;
      });
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
      console.error('Failed to unsave opening:', err);
    }
  };

  // Filter and group jobs
  const filteredJobs = useMemo(() => {
    if (!searchResult?.jobs) return [];

    return searchResult.jobs.filter((job) => {
      if (filterKeyword) {
        const keyword = filterKeyword.toLowerCase();
        const matchesKeyword =
          job.title.toLowerCase().includes(keyword) ||
          job.company_name.toLowerCase().includes(keyword) ||
          job.location?.toLowerCase().includes(keyword) ||
          job.department?.toLowerCase().includes(keyword);
        if (!matchesKeyword) return false;
      }
      if (filterCompany && !job.company_name.toLowerCase().includes(filterCompany.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [searchResult, filterKeyword, filterCompany]);

  // Helper to extract domain from URL for display
  const extractDomain = (url: string): string => {
    try {
      const hostname = new URL(url).hostname.replace('www.', '');
      return hostname;
    } catch {
      return '';
    }
  };

  // Helper to check if a company name looks generic/bad
  const isGenericName = (name: string): boolean => {
    const lower = name.toLowerCase().trim();
    const genericNames = [
      'careers', 'jobs', 'linkedin', 'indeed', 'glassdoor', 'hiring',
      'openings', 'open positions', 'job search', 'work with us',
      'join us', 'join our team', 'career opportunities'
    ];
    return genericNames.includes(lower) || lower.length < 2;
  };

  // Get a better display name for a company
  const getDisplayName = (job: ScrapedJob): string => {
    if (!isGenericName(job.company_name)) {
      return job.company_name;
    }
    // Fallback to domain name
    const domain = extractDomain(job.source_url);
    if (domain) {
      // Clean up domain for display
      return domain.split('.')[0].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }
    return job.company_name;
  };

  // Group by company (using improved display names)
  const jobsByCompany = useMemo(() => {
    const groups: Record<string, { jobs: ScrapedJob[]; sourceUrl: string }> = {};
    for (const job of filteredJobs) {
      const displayName = getDisplayName(job);
      if (!groups[displayName]) {
        groups[displayName] = { jobs: [], sourceUrl: job.source_url };
      }
      groups[displayName].jobs.push(job);
    }
    return groups;
  }, [filteredJobs]);

  const companyNames = Object.keys(jobsByCompany).sort();

  // Group saved by company
  const savedByCompany = useMemo(() => {
    const groups: Record<string, SavedOpening[]> = {};
    for (const opening of savedOpenings) {
      if (!groups[opening.company_name]) {
        groups[opening.company_name] = [];
      }
      groups[opening.company_name].push(opening);
    }
    return groups;
  }, [savedOpenings]);

  const savedCompanyNames = Object.keys(savedByCompany).sort();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-sm tracking-[0.2em] uppercase text-matcha-500 mb-1">
            Openings
          </h1>
          <p className="text-[10px] tracking-wide text-zinc-600">
            Discover job openings from company career pages by industry
          </p>
        </div>

        {/* View Toggle */}
        <div className="flex gap-1">
          <button
            onClick={() => setViewMode('search')}
            className={`px-3 py-1.5 text-[10px] tracking-[0.1em] uppercase transition-all ${
              viewMode === 'search'
                ? 'text-matcha-400 bg-matcha-500/10 border border-matcha-500/30'
                : 'text-zinc-500 border border-zinc-800 hover:border-zinc-700'
            }`}
          >
            Search
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

      {viewMode === 'search' ? (
        <>
          {/* Search Form */}
          <Card>
            <CardContent className="p-4">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Industry Select */}
                <div>
                  <label className="block text-[9px] tracking-[0.15em] uppercase text-zinc-500 mb-1.5">
                    Industry
                  </label>
                  <select
                    value={selectedIndustry}
                    onChange={(e) => setSelectedIndustry(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-3 py-2 focus:outline-none focus:border-matcha-500/50 transition-colors"
                  >
                    {industries.map((industry) => (
                      <option key={industry} value={industry}>
                        {industry}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Optional Keyword */}
                <div>
                  <label className="block text-[9px] tracking-[0.15em] uppercase text-zinc-500 mb-1.5">
                    Keyword (optional)
                  </label>
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="e.g. engineer, marketing"
                    className="w-full bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-3 py-2 placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 transition-colors"
                  />
                </div>

                {/* Max Sources */}
                <div>
                  <label className="block text-[9px] tracking-[0.15em] uppercase text-zinc-500 mb-1.5">
                    Sources to Scrape
                  </label>
                  <select
                    value={maxSources}
                    onChange={(e) => setMaxSources(Number(e.target.value))}
                    className="w-full bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs px-3 py-2 focus:outline-none focus:border-matcha-500/50 transition-colors"
                  >
                    <option value={5}>5 sources</option>
                    <option value={10}>10 sources</option>
                    <option value={15}>15 sources</option>
                    <option value={20}>20 sources</option>
                  </select>
                </div>

                {/* Search Button */}
                <div className="flex items-end">
                  <Button
                    onClick={handleSearch}
                    disabled={isSearching || !selectedIndustry}
                    className="w-full"
                  >
                    {isSearching ? (
                      <span className="flex items-center gap-2">
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                            fill="none"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                          />
                        </svg>
                        Scraping...
                      </span>
                    ) : (
                      'Search Openings'
                    )}
                  </Button>
                </div>
              </div>

              {isSearching && (
                <div className="mt-4 text-[10px] text-zinc-500 tracking-wide">
                  Searching career pages and extracting job listings. This may take 10-30 seconds...
                </div>
              )}

              {error && (
                <div className="mt-4 text-[10px] text-red-400 tracking-wide">
                  {error}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Results */}
          {searchResult && (
            <>
              {/* Stats & Filters */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="text-[10px] tracking-wide text-zinc-500">
                  Found <span className="text-matcha-400">{filteredJobs.length}</span> jobs from{' '}
                  <span className="text-zinc-300">{searchResult.sources_scraped}</span> sources
                  {searchResult.sources_failed > 0 && (
                    <span className="text-zinc-600"> ({searchResult.sources_failed} failed)</span>
                  )}
                </div>

                <div className="flex gap-3">
                  <input
                    type="text"
                    value={filterKeyword}
                    onChange={(e) => setFilterKeyword(e.target.value)}
                    placeholder="Filter by keyword..."
                    className="bg-zinc-900 border border-zinc-800 text-zinc-300 text-[10px] px-3 py-1.5 placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 w-40"
                  />
                  <input
                    type="text"
                    value={filterCompany}
                    onChange={(e) => setFilterCompany(e.target.value)}
                    placeholder="Filter by company..."
                    className="bg-zinc-900 border border-zinc-800 text-zinc-300 text-[10px] px-3 py-1.5 placeholder-zinc-600 focus:outline-none focus:border-matcha-500/50 w-40"
                  />
                </div>
              </div>

              {/* Job Listings by Company */}
              {filteredJobs.length === 0 ? (
                <Card>
                  <CardContent className="p-8 text-center">
                    <p className="text-zinc-500 text-xs">No jobs found matching your filters</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {companyNames.map((companyName) => {
                    const companyData = jobsByCompany[companyName];
                    const sourceDomain = extractDomain(companyData.sourceUrl);

                    return (
                    <Card key={companyName}>
                      <CardContent className="p-4">
                        {/* Company Header */}
                        <div className="flex items-center justify-between mb-3 pb-3 border-b border-zinc-800/50">
                          <div>
                            <h3 className="text-sm text-zinc-100 font-medium tracking-wide">{companyName}</h3>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[9px] text-zinc-500">
                                {companyData.jobs.length} position{companyData.jobs.length !== 1 ? 's' : ''}
                              </span>
                              {sourceDomain && (
                                <>
                                  <span className="text-zinc-700">•</span>
                                  <span className="text-[9px] text-zinc-600">{sourceDomain}</span>
                                </>
                              )}
                            </div>
                          </div>
                          <a
                            href={companyData.sourceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[9px] text-matcha-500 hover:text-matcha-400 tracking-wide"
                          >
                            View Career Page →
                          </a>
                        </div>

                        {/* Jobs */}
                        <div className="space-y-2">
                          {companyData.jobs.map((job, idx) => {
                            const isSaved = savedUrls.has(job.apply_url);
                            const isSaving = savingUrls.has(job.apply_url);

                            return (
                              <div
                                key={`${job.apply_url}-${idx}`}
                                className="flex items-center justify-between py-2 border-b border-zinc-800/30 last:border-0"
                              >
                                <div className="flex-1 min-w-0">
                                  <a
                                    href={job.apply_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs text-zinc-300 hover:text-matcha-400 transition-colors block truncate"
                                  >
                                    {job.title}
                                  </a>
                                  <div className="flex gap-3 mt-1">
                                    {job.location && (
                                      <span className="text-[9px] text-zinc-600">{job.location}</span>
                                    )}
                                    {job.department && (
                                      <span className="text-[9px] text-zinc-600">{job.department}</span>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 ml-4">
                                  <button
                                    onClick={() => handleSave(job)}
                                    disabled={isSaved || isSaving}
                                    className={`p-1.5 transition-colors ${
                                      isSaved
                                        ? 'text-matcha-500'
                                        : 'text-zinc-600 hover:text-matcha-400'
                                    }`}
                                    title={isSaved ? 'Saved' : 'Save for later'}
                                  >
                                    {isSaving ? (
                                      <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                                        <circle
                                          className="opacity-25"
                                          cx="12"
                                          cy="12"
                                          r="10"
                                          stroke="currentColor"
                                          strokeWidth="4"
                                          fill="none"
                                        />
                                        <path
                                          className="opacity-75"
                                          fill="currentColor"
                                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                                        />
                                      </svg>
                                    ) : (
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
                                    )}
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
                            );
                          })}
                        </div>
                      </CardContent>
                    </Card>
                    );
                  })}
                </div>
              )}
            </>
          )}

          {/* Empty State */}
          {!searchResult && !isSearching && (
            <Card>
              <CardContent className="p-8 text-center">
                <div className="text-zinc-600 mb-4">
                  <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1}
                      d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"
                    />
                  </svg>
                </div>
                <h3 className="text-xs text-zinc-400 tracking-wide mb-2">
                  Discover Job Openings by Industry
                </h3>
                <p className="text-[10px] text-zinc-600 max-w-md mx-auto">
                  Select an industry above and we'll search company career pages to find current job
                  openings. This complements Google Jobs by finding positions directly from company
                  websites.
                </p>
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        /* Saved View */
        <>
          {loadingSaved ? (
            <Card>
              <CardContent className="p-8 text-center">
                <div className="flex items-center justify-center gap-2 text-zinc-500">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  <span className="text-xs">Loading saved openings...</span>
                </div>
              </CardContent>
            </Card>
          ) : savedOpenings.length === 0 ? (
            <Card>
              <CardContent className="p-8 text-center">
                <div className="text-zinc-600 mb-4">
                  <svg className="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1}
                      d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
                    />
                  </svg>
                </div>
                <h3 className="text-xs text-zinc-400 tracking-wide mb-2">No Saved Openings</h3>
                <p className="text-[10px] text-zinc-600">
                  Search for openings and click the bookmark icon to save them for later.
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {savedCompanyNames.map((companyName) => (
                <Card key={companyName}>
                  <CardContent className="p-4">
                    {/* Company Header */}
                    <div className="flex items-center justify-between mb-3 pb-3 border-b border-zinc-800/50">
                      <div>
                        <h3 className="text-xs text-zinc-200 tracking-wide">{companyName}</h3>
                        <p className="text-[9px] text-zinc-600 mt-0.5">
                          {savedByCompany[companyName].length} saved
                        </p>
                      </div>
                    </div>

                    {/* Saved Openings */}
                    <div className="space-y-2">
                      {savedByCompany[companyName].map((opening) => (
                        <div
                          key={opening.id}
                          className="flex items-center justify-between py-2 border-b border-zinc-800/30 last:border-0"
                        >
                          <div className="flex-1 min-w-0">
                            <a
                              href={opening.apply_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-zinc-300 hover:text-matcha-400 transition-colors block truncate"
                            >
                              {opening.title}
                            </a>
                            <div className="flex gap-3 mt-1">
                              {opening.location && (
                                <span className="text-[9px] text-zinc-600">{opening.location}</span>
                              )}
                              {opening.industry && (
                                <span className="text-[9px] text-zinc-500">{opening.industry}</span>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            <button
                              onClick={() => handleUnsave(opening)}
                              className="p-1.5 text-matcha-500 hover:text-red-400 transition-colors"
                              title="Remove from saved"
                            >
                              <svg
                                className="w-4 h-4"
                                fill="currentColor"
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
                              href={opening.apply_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1 text-[9px] tracking-[0.1em] uppercase text-matcha-500 border border-matcha-500/30 hover:bg-matcha-500/10 transition-colors"
                            >
                              Apply
                            </a>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
