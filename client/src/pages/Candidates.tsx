import { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Card, CardContent, Modal } from '../components';
import { candidates as candidatesApi, type CandidateFilters } from '../api/client';
import type { Candidate, CandidateDetail } from '../types';

export function Candidates() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateDetail | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Filter state
  const [filters, setFilters] = useState<CandidateFilters>({});
  const [searchInput, setSearchInput] = useState('');
  const [skillsInput, setSkillsInput] = useState('');
  const [minExp, setMinExp] = useState('');
  const [maxExp, setMaxExp] = useState('');
  const [education, setEducation] = useState('');

  const fetchCandidates = useCallback(async (currentFilters: CandidateFilters) => {
    try {
      setLoading(true);
      const data = await candidatesApi.list(currentFilters);
      setCandidates(data);
    } catch (err) {
      console.error('Failed to fetch candidates:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCandidates(filters);
  }, [filters, fetchCandidates]);

  const applyFilters = () => {
    const newFilters: CandidateFilters = {};
    if (searchInput.trim()) newFilters.search = searchInput.trim();
    if (skillsInput.trim()) newFilters.skills = skillsInput.trim();
    if (minExp) newFilters.min_experience = parseInt(minExp);
    if (maxExp) newFilters.max_experience = parseInt(maxExp);
    if (education) newFilters.education = education;
    setFilters(newFilters);
  };

  const clearFilters = () => {
    setSearchInput('');
    setSkillsInput('');
    setMinExp('');
    setMaxExp('');
    setEducation('');
    setFilters({});
  };

  const hasActiveFilters = Object.keys(filters).length > 0;

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      await candidatesApi.upload(file);
      fetchCandidates(filters);
    } catch (err) {
      console.error('Failed to upload:', err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleViewDetail = async (id: string) => {
    try {
      const detail = await candidatesApi.get(id);
      setSelectedCandidate(detail);
      setShowDetail(true);
    } catch (err) {
      console.error('Failed to fetch candidate:', err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this candidate?')) return;
    try {
      await candidatesApi.delete(id);
      fetchCandidates(filters);
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-white tracking-tight">Candidates</h1>
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc"
            onChange={handleUpload}
            className="hidden"
          />
          <Button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? 'Uploading...' : 'Upload Resume'}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            {/* Search */}
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Search</label>
              <input
                type="text"
                placeholder="Name or email..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>

            {/* Skills */}
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Skills</label>
              <input
                type="text"
                placeholder="python, react, aws..."
                value={skillsInput}
                onChange={(e) => setSkillsInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
              />
            </div>

            {/* Experience Range */}
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Experience (years)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  placeholder="Min"
                  value={minExp}
                  onChange={(e) => setMinExp(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
                />
                <input
                  type="number"
                  placeholder="Max"
                  value={maxExp}
                  onChange={(e) => setMaxExp(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
                  className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-white"
                />
              </div>
            </div>

            {/* Education */}
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Education</label>
              <select
                value={education}
                onChange={(e) => setEducation(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-white"
              >
                <option value="">Any</option>
                <option value="phd">PhD / Doctorate</option>
                <option value="master">Master's</option>
                <option value="bachelor">Bachelor's</option>
                <option value="associate">Associate's</option>
              </select>
            </div>

            {/* Actions */}
            <div className="flex items-end gap-2">
              <Button onClick={applyFilters} className="flex-1">
                Filter
              </Button>
              {hasActiveFilters && (
                <Button variant="secondary" onClick={clearFilters}>
                  Clear
                </Button>
              )}
            </div>
          </div>

          {hasActiveFilters && (
            <div className="mt-3 text-sm text-zinc-500">
              Showing {candidates.length} result{candidates.length !== 1 ? 's' : ''}
            </div>
          )}
        </CardContent>
      </Card>

      {loading ? (
        <div className="text-center py-12 text-zinc-500">Loading...</div>
      ) : candidates.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <svg
              className="mx-auto h-12 w-12 text-zinc-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            {hasActiveFilters ? (
              <>
                <p className="mt-4 text-zinc-500">No candidates match your filters</p>
                <Button
                  variant="secondary"
                  className="mt-4"
                  onClick={clearFilters}
                >
                  Clear Filters
                </Button>
              </>
            ) : (
              <>
                <p className="mt-4 text-zinc-500">No candidates yet</p>
                <p className="text-sm text-zinc-600 mt-1">Upload PDF or DOCX resumes to get started</p>
                <Button
                  className="mt-4"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Upload Resume
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
          {/* Table Header */}
          <div className="grid grid-cols-[1fr_1.5fr_100px_1fr_50px] gap-4 px-4 py-3 bg-zinc-800/50 border-b border-zinc-700 text-xs font-medium text-zinc-400 uppercase tracking-wider">
            <div>Name</div>
            <div>Email</div>
            <div>Experience</div>
            <div>Skills</div>
            <div></div>
          </div>

          {/* Table Body */}
          <div className="divide-y divide-zinc-800">
            {candidates.map((candidate) => (
              <div
                key={candidate.id}
                onClick={() => handleViewDetail(candidate.id)}
                className="grid grid-cols-[1fr_1.5fr_100px_1fr_50px] gap-4 px-4 py-3 items-center hover:bg-zinc-800/30 transition-colors cursor-pointer"
              >
                <div className="font-medium text-zinc-100 truncate">
                  {candidate.name || 'Unknown'}
                </div>
                <div className="text-zinc-400 text-sm truncate">
                  {candidate.email || '-'}
                </div>
                <div className="text-zinc-400 text-sm">
                  {candidate.experience_years ? `${candidate.experience_years} yrs` : '-'}
                </div>
                <div className="flex flex-wrap gap-1 overflow-hidden">
                  {candidate.skills?.slice(0, 3).map((skill) => (
                    <span
                      key={skill}
                      className="px-2 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700 rounded text-xs whitespace-nowrap"
                    >
                      {skill}
                    </span>
                  ))}
                  {candidate.skills && candidate.skills.length > 3 && (
                    <span className="text-zinc-600 text-xs whitespace-nowrap">
                      +{candidate.skills.length - 3}
                    </span>
                  )}
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(candidate.id);
                    }}
                    className="text-zinc-600 hover:text-red-400 transition-colors p-1"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Candidate Detail Modal */}
      <Modal
        isOpen={showDetail}
        onClose={() => setShowDetail(false)}
        title={selectedCandidate?.name || 'Candidate Details'}
      >
        {selectedCandidate && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-6 text-sm">
              {selectedCandidate.email && (
                <div>
                  <span className="text-zinc-500 block mb-1">Email</span>
                  <p className="font-medium text-zinc-200">{selectedCandidate.email}</p>
                </div>
              )}
              {selectedCandidate.phone && (
                <div>
                  <span className="text-zinc-500 block mb-1">Phone</span>
                  <p className="font-medium text-zinc-200">{selectedCandidate.phone}</p>
                </div>
              )}
              {selectedCandidate.experience_years && (
                <div>
                  <span className="text-zinc-500 block mb-1">Experience</span>
                  <p className="font-medium text-zinc-200">{selectedCandidate.experience_years} years</p>
                </div>
              )}
            </div>

            {selectedCandidate.skills && selectedCandidate.skills.length > 0 && (
              <div>
                <span className="text-sm text-zinc-500 block mb-2">Skills</span>
                <div className="flex flex-wrap gap-2">
                  {selectedCandidate.skills.map((skill) => (
                    <span
                      key={skill}
                      className="px-2.5 py-1 bg-zinc-800 text-white border border-zinc-700 rounded-md text-xs font-medium"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {selectedCandidate.education && selectedCandidate.education.length > 0 && (
              <div>
                <span className="text-sm text-zinc-500 block mb-2">Education</span>
                <div className="space-y-3">
                  {selectedCandidate.education.map((edu, idx) => (
                    <div key={idx} className="text-sm bg-zinc-800/50 p-3 rounded-lg border border-zinc-800">
                      <p className="font-medium text-zinc-200">
                        {edu.degree} in {edu.field}
                      </p>
                      <p className="text-zinc-500 mt-1">
                        {edu.institution} {edu.year && `(${edu.year})`}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {typeof selectedCandidate.parsed_data?.summary === 'string' && (
              <div>
                <span className="text-sm text-zinc-500 block mb-2">Summary</span>
                <p className="text-sm text-zinc-300 leading-relaxed bg-zinc-800/30 p-3 rounded-lg border border-zinc-800/50">
                  {selectedCandidate.parsed_data.summary}
                </p>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}

export default Candidates;
