import { useState, useEffect, useRef } from 'react';
import { Button, Card, CardContent, Modal } from '../components';
import { candidates as candidatesApi } from '../api/client';
import type { Candidate, CandidateDetail } from '../types';

export function Candidates() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateDetail | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchCandidates = async () => {
    try {
      const data = await candidatesApi.list();
      setCandidates(data);
    } catch (err) {
      console.error('Failed to fetch candidates:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      await candidatesApi.upload(file);
      fetchCandidates();
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
      fetchCandidates();
    } catch (err) {
      console.error('Failed to delete:', err);
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-zinc-500">Loading...</div>;
  }

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

      {candidates.length === 0 ? (
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
            <p className="mt-4 text-zinc-500">No candidates yet</p>
            <p className="text-sm text-zinc-600 mt-1">Upload PDF or DOCX resumes to get started</p>
            <Button
              className="mt-4"
              onClick={() => fileInputRef.current?.click()}
            >
              Upload Resume
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {candidates.map((candidate) => (
            <Card key={candidate.id} className="hover:border-matcha-500/50 transition-colors group">
              <CardContent>
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-lg font-semibold text-zinc-100 group-hover:text-matcha-400 transition-colors">
                      {candidate.name || 'Unknown'}
                    </h3>
                    {candidate.email && (
                      <p className="text-sm text-zinc-500">{candidate.email}</p>
                    )}
                  </div>
                  <button
                    onClick={() => handleDelete(candidate.id)}
                    className="text-zinc-600 hover:text-red-400 transition-colors"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>

                <div className="mt-4 space-y-3">
                  {candidate.experience_years && (
                    <p className="text-sm text-zinc-400 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-zinc-700"></span>
                      {candidate.experience_years} years experience
                    </p>
                  )}
                  {candidate.skills && candidate.skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {candidate.skills.slice(0, 5).map((skill) => (
                        <span
                          key={skill}
                          className="px-2 py-0.5 bg-zinc-800 text-zinc-400 border border-zinc-700 rounded text-xs"
                        >
                          {skill}
                        </span>
                      ))}
                      {candidate.skills.length > 5 && (
                        <span className="px-2 py-0.5 text-zinc-600 text-xs">
                          +{candidate.skills.length - 5} more
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full mt-6"
                  onClick={() => handleViewDetail(candidate.id)}
                >
                  View Details
                </Button>
              </CardContent>
            </Card>
          ))}
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
                      className="px-2.5 py-1 bg-matcha-500/10 text-matcha-400 border border-matcha-500/20 rounded-md text-xs font-medium"
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
