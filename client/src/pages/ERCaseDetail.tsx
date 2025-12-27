import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Card, CardContent, FileUpload, Modal } from '../components';
import { erCopilot } from '../api/client';
import type {
  ERCase,
  ERCaseStatus,
  ERDocument,
  ERDocumentType,
  TimelineEvent,
  Discrepancy,
  PolicyViolation,
  EvidenceSearchResult,
} from '../types';

const STATUS_COLORS: Record<ERCaseStatus, string> = {
  open: 'bg-matcha-500/20 text-matcha-400',
  in_review: 'bg-yellow-500/20 text-yellow-400',
  pending_determination: 'bg-orange-500/20 text-orange-400',
  closed: 'bg-zinc-700 text-zinc-300',
};

const STATUS_OPTIONS: { value: ERCaseStatus; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'in_review', label: 'In Review' },
  { value: 'pending_determination', label: 'Pending Determination' },
  { value: 'closed', label: 'Closed' },
];

const DOC_TYPE_OPTIONS: { value: ERDocumentType; label: string }[] = [
  { value: 'transcript', label: 'Interview Transcript' },
  { value: 'policy', label: 'Policy Document' },
  { value: 'email', label: 'Email/Communication' },
  { value: 'other', label: 'Other Evidence' },
];

const DOC_TYPE_COLORS: Record<ERDocumentType, string> = {
  transcript: 'bg-blue-500/20 text-blue-400',
  policy: 'bg-purple-500/20 text-purple-400',
  email: 'bg-yellow-500/20 text-yellow-400',
  other: 'bg-zinc-600 text-zinc-300',
};

type AnalysisTab = 'timeline' | 'discrepancies' | 'policy' | 'search';

export function ERCaseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // State
  const [erCase, setCase] = useState<ERCase | null>(null);
  const [documents, setDocuments] = useState<ERDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<AnalysisTab>('timeline');

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadDocType, setUploadDocType] = useState<ERDocumentType>('transcript');
  const [uploading, setUploading] = useState(false);

  // Analysis state
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineSummary, setTimelineSummary] = useState<string>('');
  const [timelineGaps, setTimelineGaps] = useState<string[]>([]);
  const [discrepancies, setDiscrepancies] = useState<Discrepancy[]>([]);
  const [discrepancySummary, setDiscrepancySummary] = useState<string>('');
  const [violations, setViolations] = useState<PolicyViolation[]>([]);
  const [violationSummary, setViolationSummary] = useState<string>('');
  const [analysisLoading, setAnalysisLoading] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<EvidenceSearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  const fetchCase = useCallback(async () => {
    if (!id) return;
    try {
      const data = await erCopilot.getCase(id);
      setCase(data);
    } catch (err) {
      console.error('Failed to fetch case:', err);
    }
  }, [id]);

  const fetchDocuments = useCallback(async () => {
    if (!id) return;
    try {
      const docs = await erCopilot.listDocuments(id);
      setDocuments(docs);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    }
  }, [id]);

  const fetchAnalysis = useCallback(async (type: AnalysisTab) => {
    if (!id) return;
    try {
      if (type === 'timeline') {
        const data = await erCopilot.getTimeline(id);
        setTimeline(data.analysis.events || []);
        setTimelineSummary(data.analysis.timeline_summary || '');
        setTimelineGaps(data.analysis.gaps_identified || []);
      } else if (type === 'discrepancies') {
        const data = await erCopilot.getDiscrepancies(id);
        setDiscrepancies(data.analysis.discrepancies || []);
        setDiscrepancySummary(data.analysis.summary || '');
      } else if (type === 'policy') {
        const data = await erCopilot.getPolicyCheck(id);
        setViolations(data.analysis.violations || []);
        setViolationSummary(data.analysis.summary || '');
      }
    } catch {
      // Analysis not yet generated - that's okay
    }
  }, [id]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchCase(), fetchDocuments()]);
      setLoading(false);
    };
    load();
  }, [fetchCase, fetchDocuments]);

  useEffect(() => {
    fetchAnalysis(activeTab);
  }, [activeTab, fetchAnalysis]);

  const handleUpload = async (files: File[]) => {
    if (!id || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of files) {
        await erCopilot.uploadDocument(id, file, uploadDocType);
      }
      setShowUploadModal(false);
      fetchDocuments();
    } catch (err) {
      console.error('Failed to upload:', err);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDoc = async (docId: string) => {
    if (!id) return;
    if (!confirm('Delete this document?')) return;
    try {
      await erCopilot.deleteDocument(id, docId);
      fetchDocuments();
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  const handleGenerateTimeline = async () => {
    if (!id) return;
    setAnalysisLoading('timeline');
    try {
      await erCopilot.generateTimeline(id);
      // Poll for results
      setTimeout(() => fetchAnalysis('timeline'), 5000);
    } catch (err) {
      console.error('Failed to generate timeline:', err);
    } finally {
      setAnalysisLoading(null);
    }
  };

  const handleGenerateDiscrepancies = async () => {
    if (!id) return;
    setAnalysisLoading('discrepancies');
    try {
      await erCopilot.generateDiscrepancies(id);
      setTimeout(() => fetchAnalysis('discrepancies'), 5000);
    } catch (err) {
      console.error('Failed to generate discrepancies:', err);
    } finally {
      setAnalysisLoading(null);
    }
  };

  const handleRunPolicyCheck = async () => {
    if (!id) return;
    const policyDoc = documents.find(d => d.document_type === 'policy' && d.processing_status === 'completed');
    if (!policyDoc) {
      alert('Please upload a policy document first.');
      return;
    }
    setAnalysisLoading('policy');
    try {
      await erCopilot.runPolicyCheck(id, policyDoc.id);
      setTimeout(() => fetchAnalysis('policy'), 5000);
    } catch (err) {
      console.error('Failed to run policy check:', err);
    } finally {
      setAnalysisLoading(null);
    }
  };

  const handleSearch = async () => {
    if (!id || !searchQuery.trim()) return;
    setSearching(true);
    try {
      const data = await erCopilot.searchEvidence(id, searchQuery);
      setSearchResults(data.results);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setSearching(false);
    }
  };

  const handleStatusChange = async (newStatus: ERCaseStatus) => {
    if (!id) return;
    try {
      await erCopilot.updateCase(id, { status: newStatus });
      fetchCase();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const getDocFilename = (docId: string) => {
    const doc = documents.find(d => d.id === docId);
    return doc?.filename || docId;
  };

  if (loading) {
    return <div className="text-center py-12 text-zinc-500">Loading...</div>;
  }

  if (!erCase) {
    return <div className="text-center py-12 text-zinc-500">Case not found</div>;
  }

  const processedDocs = documents.filter(d => d.processing_status === 'completed');

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate('/app/er-copilot')}
          className="text-zinc-400 hover:text-white transition-colors"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <span className="text-sm text-zinc-500 font-mono">{erCase.case_number}</span>
            <span className={`px-2 py-0.5 text-xs rounded ${STATUS_COLORS[erCase.status]}`}>
              {erCase.status.replace('_', ' ')}
            </span>
          </div>
          <h1 className="text-2xl font-bold text-white mt-1">{erCase.title}</h1>
        </div>
        <select
          value={erCase.status}
          onChange={(e) => handleStatusChange(e.target.value as ERCaseStatus)}
          className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm"
        >
          {STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {/* Split Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Documents */}
        <div className="lg:col-span-1">
          <Card>
            <CardContent>
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold text-white">Documents</h2>
                <Button size="sm" onClick={() => setShowUploadModal(true)}>Upload</Button>
              </div>

              {documents.length === 0 ? (
                <p className="text-zinc-500 text-sm">No documents uploaded yet.</p>
              ) : (
                <div className="space-y-2">
                  {documents.map(doc => (
                    <div
                      key={doc.id}
                      className="p-3 bg-zinc-800/50 rounded-lg flex items-start justify-between"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`px-1.5 py-0.5 text-xs rounded ${DOC_TYPE_COLORS[doc.document_type]}`}>
                            {doc.document_type}
                          </span>
                          {doc.processing_status === 'processing' && (
                            <span className="text-xs text-yellow-400">Processing...</span>
                          )}
                          {doc.processing_status === 'failed' && (
                            <span className="text-xs text-red-400">Failed</span>
                          )}
                          {doc.pii_scrubbed && (
                            <span className="text-xs text-matcha-400">PII scrubbed</span>
                          )}
                        </div>
                        <p className="text-sm text-white truncate">{doc.filename}</p>
                        {doc.file_size && (
                          <p className="text-xs text-zinc-500">{(doc.file_size / 1024).toFixed(1)} KB</p>
                        )}
                      </div>
                      <button
                        onClick={() => handleDeleteDoc(doc.id)}
                        className="text-zinc-500 hover:text-red-400 transition-colors ml-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Analysis */}
        <div className="lg:col-span-2">
          <Card>
            <CardContent>
              {/* Analysis Tabs */}
              <div className="flex gap-1 mb-4 bg-zinc-800 p-1 rounded-lg">
                {[
                  { id: 'timeline', label: 'Timeline' },
                  { id: 'discrepancies', label: 'Discrepancies' },
                  { id: 'policy', label: 'Policy Check' },
                  { id: 'search', label: 'Search' },
                ].map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as AnalysisTab)}
                    className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                      activeTab === tab.id
                        ? 'bg-zinc-700 text-white'
                        : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Timeline Tab */}
              {activeTab === 'timeline' && (
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-medium text-white">Timeline Reconstruction</h3>
                    <Button
                      size="sm"
                      onClick={handleGenerateTimeline}
                      disabled={analysisLoading === 'timeline' || processedDocs.length === 0}
                    >
                      {analysisLoading === 'timeline' ? 'Generating...' : 'Generate'}
                    </Button>
                  </div>

                  {timelineSummary && (
                    <p className="text-sm text-zinc-400 mb-4 p-3 bg-zinc-800/50 rounded-lg">{timelineSummary}</p>
                  )}

                  {timeline.length === 0 ? (
                    <p className="text-zinc-500 text-sm">
                      {processedDocs.length === 0
                        ? 'Upload and process documents first.'
                        : 'Click "Generate" to reconstruct the timeline from your documents.'}
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {timeline.map((event, i) => (
                        <div key={i} className="relative pl-6 pb-4 border-l-2 border-zinc-700 last:pb-0">
                          <div className="absolute left-[-5px] top-0 w-2 h-2 rounded-full bg-matcha-500" />
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-sm font-medium text-matcha-400">
                              {event.date} {event.time && `at ${event.time}`}
                            </span>
                            <span className={`px-1.5 py-0.5 text-xs rounded ${
                              event.confidence === 'high' ? 'bg-matcha-500/20 text-matcha-400' :
                              event.confidence === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-red-500/20 text-red-400'
                            }`}>
                              {event.confidence}
                            </span>
                          </div>
                          <p className="text-white mb-1">{event.description}</p>
                          {event.participants.length > 0 && (
                            <p className="text-xs text-zinc-500 mb-1">
                              Participants: {event.participants.join(', ')}
                            </p>
                          )}
                          <p className="text-xs text-zinc-600 italic">
                            Source: {getDocFilename(event.source_document_id)} ({event.source_location})
                          </p>
                          {event.evidence_quote && (
                            <p className="text-xs text-zinc-500 mt-1 p-2 bg-zinc-800 rounded border-l-2 border-zinc-600">
                              "{event.evidence_quote}"
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {timelineGaps.length > 0 && (
                    <div className="mt-4 p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
                      <h4 className="text-sm font-medium text-yellow-400 mb-2">Gaps Identified</h4>
                      <ul className="text-sm text-zinc-400 space-y-1">
                        {timelineGaps.map((gap, i) => (
                          <li key={i}>• {gap}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Discrepancies Tab */}
              {activeTab === 'discrepancies' && (
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-medium text-white">Discrepancy Detection</h3>
                    <Button
                      size="sm"
                      onClick={handleGenerateDiscrepancies}
                      disabled={analysisLoading === 'discrepancies' || processedDocs.filter(d => d.document_type === 'transcript').length < 2}
                    >
                      {analysisLoading === 'discrepancies' ? 'Analyzing...' : 'Analyze'}
                    </Button>
                  </div>

                  {discrepancySummary && (
                    <p className="text-sm text-zinc-400 mb-4 p-3 bg-zinc-800/50 rounded-lg">{discrepancySummary}</p>
                  )}

                  {discrepancies.length === 0 ? (
                    <p className="text-zinc-500 text-sm">
                      {processedDocs.filter(d => d.document_type === 'transcript').length < 2
                        ? 'Upload at least 2 transcript documents to detect discrepancies.'
                        : 'Click "Analyze" to detect discrepancies between witness statements.'}
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {discrepancies.map((disc, i) => (
                        <div key={i} className="p-4 bg-zinc-800/50 rounded-lg border-l-4 border-l-red-500">
                          <div className="flex items-center gap-2 mb-2">
                            <span className={`px-2 py-0.5 text-xs rounded ${
                              disc.severity === 'high' ? 'bg-red-500/20 text-red-400' :
                              disc.severity === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-zinc-600 text-zinc-300'
                            }`}>
                              {disc.severity} severity
                            </span>
                            <span className="text-xs text-zinc-500">{disc.type}</span>
                          </div>
                          <p className="text-white mb-3">{disc.description}</p>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div className="p-2 bg-zinc-800 rounded">
                              <p className="text-xs text-zinc-500 mb-1">
                                {disc.statement_1.speaker} ({disc.statement_1.location})
                              </p>
                              <p className="text-sm text-zinc-300">"{disc.statement_1.quote}"</p>
                            </div>
                            <div className="p-2 bg-zinc-800 rounded">
                              <p className="text-xs text-zinc-500 mb-1">
                                {disc.statement_2.speaker} ({disc.statement_2.location})
                              </p>
                              <p className="text-sm text-zinc-300">"{disc.statement_2.quote}"</p>
                            </div>
                          </div>
                          <p className="text-xs text-zinc-500 mt-2 italic">{disc.analysis}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Policy Check Tab */}
              {activeTab === 'policy' && (
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-medium text-white">Policy Violation Check</h3>
                    <Button
                      size="sm"
                      onClick={handleRunPolicyCheck}
                      disabled={analysisLoading === 'policy' || !documents.find(d => d.document_type === 'policy' && d.processing_status === 'completed')}
                    >
                      {analysisLoading === 'policy' ? 'Checking...' : 'Run Check'}
                    </Button>
                  </div>

                  {violationSummary && (
                    <p className="text-sm text-zinc-400 mb-4 p-3 bg-zinc-800/50 rounded-lg">{violationSummary}</p>
                  )}

                  {violations.length === 0 ? (
                    <p className="text-zinc-500 text-sm">
                      {!documents.find(d => d.document_type === 'policy')
                        ? 'Upload a policy document (Code of Conduct, Employee Handbook, etc.) first.'
                        : 'Click "Run Check" to analyze evidence against the policy document.'}
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {violations.map((v, i) => (
                        <div key={i} className="p-4 bg-zinc-800/50 rounded-lg border-l-4 border-l-purple-500">
                          <div className="flex items-center gap-2 mb-2">
                            <span className={`px-2 py-0.5 text-xs rounded ${
                              v.severity === 'major' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'
                            }`}>
                              {v.severity}
                            </span>
                          </div>
                          <h4 className="text-white font-medium mb-1">{v.policy_section}</h4>
                          <p className="text-sm text-zinc-400 mb-2 italic">"{v.policy_text}"</p>
                          <div className="space-y-2">
                            {v.evidence.map((e, j) => (
                              <div key={j} className="p-2 bg-zinc-800 rounded text-sm">
                                <p className="text-zinc-300">"{e.quote}"</p>
                                <p className="text-xs text-zinc-500 mt-1">{e.how_it_violates}</p>
                              </div>
                            ))}
                          </div>
                          <p className="text-xs text-zinc-500 mt-2 italic">{v.analysis}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Search Tab */}
              {activeTab === 'search' && (
                <div>
                  <h3 className="text-lg font-medium text-white mb-4">Evidence Search</h3>
                  <div className="flex gap-2 mb-4">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                      placeholder="Search case evidence..."
                      className="flex-1 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-matcha-500"
                    />
                    <Button onClick={handleSearch} disabled={searching || !searchQuery.trim()}>
                      {searching ? 'Searching...' : 'Search'}
                    </Button>
                  </div>

                  {searchResults.length > 0 ? (
                    <div className="space-y-3">
                      {searchResults.map((result, i) => (
                        <div key={i} className="p-3 bg-zinc-800/50 rounded-lg">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`px-1.5 py-0.5 text-xs rounded ${DOC_TYPE_COLORS[result.document_type]}`}>
                              {result.document_type}
                            </span>
                            <span className="text-xs text-zinc-500">{result.source_file}</span>
                            <span className="text-xs text-matcha-400 ml-auto">
                              {(result.similarity * 100).toFixed(0)}% match
                            </span>
                          </div>
                          {result.speaker && (
                            <p className="text-xs text-zinc-500 mb-1">{result.speaker}:</p>
                          )}
                          <p className="text-sm text-zinc-300">{result.content}</p>
                          {result.line_range && (
                            <p className="text-xs text-zinc-600 mt-1">Lines {result.line_range}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-zinc-500 text-sm">
                      {processedDocs.length === 0
                        ? 'Upload and process documents first.'
                        : 'Enter a query to search through case evidence using semantic similarity.'}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Upload Modal */}
      <Modal isOpen={showUploadModal} onClose={() => setShowUploadModal(false)} title="Upload Document">
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Document Type</label>
            <select
              value={uploadDocType}
              onChange={(e) => setUploadDocType(e.target.value as ERDocumentType)}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white"
            >
              {DOC_TYPE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <FileUpload
            accept=".pdf,.docx,.doc,.txt,.csv,.json"
            onUpload={handleUpload}
            multiple={true}
            label={uploading ? 'Uploading...' : 'Drop files here or click to select'}
            description="Supports PDF, DOCX, TXT, CSV, JSON"
          />

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => setShowUploadModal(false)}>
              Cancel
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
