import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, FileUpload } from '../components';
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
import {
  ChevronLeft, Upload, Trash2, Search,
  AlertTriangle, CheckCircle, Clock, X, RefreshCw
} from 'lucide-react';

const STATUS_COLORS: Record<ERCaseStatus, string> = {
  open: 'text-zinc-900',
  in_review: 'text-amber-600',
  pending_determination: 'text-orange-600',
  closed: 'text-zinc-400',
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
  transcript: 'text-blue-600',
  policy: 'text-purple-600',
  email: 'text-amber-600',
  other: 'text-zinc-500',
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
  const [statusUpdating, setStatusUpdating] = useState(false);

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

  const handleReprocessDoc = async (docId: string) => {
    if (!id) return;
    try {
      await erCopilot.reprocessDocument(id, docId);
      // Refresh documents to show updated status
      fetchDocuments();
      // Poll for completion
      const pollInterval = setInterval(async () => {
        const docs = await erCopilot.listDocuments(id);
        const doc = docs.find(d => d.id === docId);
        if (doc && (doc.processing_status === 'completed' || doc.processing_status === 'failed')) {
          clearInterval(pollInterval);
          setDocuments(docs);
        }
      }, 2000);
      // Clear interval after 60 seconds max
      setTimeout(() => clearInterval(pollInterval), 60000);
    } catch (err) {
      console.error('Failed to reprocess document:', err);
    }
  };

  const [reprocessingAll, setReprocessingAll] = useState(false);

  const handleReprocessAllDocs = async () => {
    if (!id) return;
    setReprocessingAll(true);
    try {
      const result = await erCopilot.reprocessAllDocuments(id);
      console.log('Reprocess all result:', result);
      // Refresh documents to show updated status
      fetchDocuments();
    } catch (err) {
      console.error('Failed to reprocess all documents:', err);
    } finally {
      setReprocessingAll(false);
    }
  };

  const hasUnprocessedDocs = documents.some(d => d.processing_status === 'pending' || d.processing_status === 'failed');

  const pollForAnalysis = useCallback(async (type: AnalysisTab, maxAttempts = 30) => {
    // Poll every 2 seconds for up to 60 seconds
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      try {
        if (type === 'timeline') {
          const data = await erCopilot.getTimeline(id!);
          setTimeline(data.analysis.events || []);
          setTimelineSummary(data.analysis.timeline_summary || '');
          setTimelineGaps(data.analysis.gaps_identified || []);
          return true;
        } else if (type === 'discrepancies') {
          const data = await erCopilot.getDiscrepancies(id!);
          setDiscrepancies(data.analysis.discrepancies || []);
          setDiscrepancySummary(data.analysis.summary || '');
          return true;
        } else if (type === 'policy') {
          const data = await erCopilot.getPolicyCheck(id!);
          setViolations(data.analysis.violations || []);
          setViolationSummary(data.analysis.summary || '');
          return true;
        }
      } catch {
        // Not ready yet, continue polling
      }
    }
    return false;
  }, [id]);

  const handleGenerateTimeline = async () => {
    if (!id) return;
    setAnalysisLoading('timeline');
    try {
      await erCopilot.generateTimeline(id);
      const success = await pollForAnalysis('timeline');
      if (!success) {
        console.error('Timeline analysis timed out');
      }
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
      const success = await pollForAnalysis('discrepancies');
      if (!success) {
        console.error('Discrepancy analysis timed out');
      }
    } catch (err) {
      console.error('Failed to generate discrepancies:', err);
    } finally {
      setAnalysisLoading(null);
    }
  };

  const handleRunPolicyCheck = async () => {
    if (!id) return;
    const policyDoc = uploadedDocs.find(d => d.document_type === 'policy');
    if (!policyDoc) {
      alert('Please upload a policy document first.');
      return;
    }
    setAnalysisLoading('policy');
    try {
      await erCopilot.runPolicyCheck(id, policyDoc.id);
      const success = await pollForAnalysis('policy');
      if (!success) {
        console.error('Policy check timed out');
      }
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
    if (!id || !erCase) return;

    setStatusUpdating(true);
    try {
      await erCopilot.updateCase(id, { status: newStatus });
      await fetchCase();
    } catch (err) {
      console.error('Failed to update status:', err);
      await fetchCase();
    } finally {
      setStatusUpdating(false);
    }
  };

  if (loading) {
    return <div className="text-center py-12 text-zinc-500 text-xs uppercase tracking-wider">Loading...</div>;
  }

  if (!erCase) {
    return <div className="text-center py-12 text-zinc-500 text-xs uppercase tracking-wider">Case not found</div>;
  }

  const uploadedDocs = documents.filter(d => d.processing_status !== 'failed');

  return (
    <div className="max-w-5xl mx-auto space-y-12">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate('/app/er-copilot')}
            className="text-xs text-zinc-500 hover:text-zinc-900 mb-4 flex items-center gap-1 uppercase tracking-wider"
          >
            <ChevronLeft size={12} />
            Back to Cases
          </button>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-[10px] text-zinc-400 font-mono tracking-wide">{erCase.case_number}</span>
            <span className={`text-[10px] uppercase tracking-wide font-medium ${STATUS_COLORS[erCase.status]}`}>
              {erCase.status.replace('_', ' ')}
            </span>
          </div>
          <h1 className="text-2xl font-light text-zinc-900 dark:text-zinc-100 tracking-tight">{erCase.title}</h1>
        </div>
        <div className="w-40">
          <select
            value={erCase.status}
            onChange={(e) => handleStatusChange(e.target.value as ERCaseStatus)}
            disabled={statusUpdating}
            className={`w-full px-2 py-1.5 bg-transparent border-b border-zinc-200 text-xs text-zinc-600 focus:outline-none focus:border-zinc-400 cursor-pointer ${
              statusUpdating ? 'opacity-50' : ''
            }`}
          >
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-12">
        {/* Left: Documents */}
        <div className="lg:col-span-1 space-y-6">
          <div className="flex justify-between items-center border-b border-zinc-200 pb-2">
            <h2 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider">Evidence</h2>
            <div className="flex items-center gap-3">
              {hasUnprocessedDocs && (
                <button
                  onClick={handleReprocessAllDocs}
                  disabled={reprocessingAll}
                  className="text-[10px] text-amber-600 hover:text-amber-500 flex items-center gap-1 uppercase tracking-wide font-medium disabled:opacity-50"
                  title="Reprocess all pending/failed documents"
                >
                  <RefreshCw size={10} className={reprocessingAll ? 'animate-spin' : ''} />
                  {reprocessingAll ? 'Processing...' : 'Reprocess All'}
                </button>
              )}
              <button
                onClick={() => setShowUploadModal(true)}
                className="text-[10px] text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 flex items-center gap-1 uppercase tracking-wide font-medium"
              >
                <Upload size={10} />
                Upload
              </button>
            </div>
          </div>

          <div className="min-h-[200px]">
            {documents.length === 0 ? (
              <div className="text-zinc-400 text-xs py-4">
                No documents uploaded.
              </div>
            ) : (
              <div className="space-y-1">
                {documents.map(doc => (
                  <div key={doc.id} className="py-2 flex items-start justify-between group">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-[10px] uppercase tracking-wide font-medium ${DOC_TYPE_COLORS[doc.document_type]}`}>
                          {doc.document_type}
                        </span>
                        {doc.processing_status === 'pending' && (
                          <span className="text-[10px] text-zinc-400">Pending</span>
                        )}
                        {doc.processing_status === 'processing' && (
                          <span className="text-[10px] text-amber-500">Processing...</span>
                        )}
                        {doc.processing_status === 'completed' && (
                          <span className="text-[10px] text-emerald-500">✓</span>
                        )}
                        {doc.processing_status === 'failed' && (
                          <span className="text-[10px] text-red-500">Failed</span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-900 dark:text-zinc-100 truncate hover:text-zinc-700 dark:hover:text-zinc-300 cursor-pointer" title={doc.filename}>{doc.filename}</p>
                      {doc.processing_error && (
                        <p className="text-[10px] text-red-400 truncate" title={doc.processing_error}>{doc.processing_error}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                      {(doc.processing_status === 'pending' || doc.processing_status === 'failed') && (
                        <button
                          onClick={() => handleReprocessDoc(doc.id)}
                          className="text-zinc-300 hover:text-blue-500 transition-colors p-1"
                          title="Reprocess document"
                        >
                          <RefreshCw size={12} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteDoc(doc.id)}
                        className="text-zinc-300 hover:text-red-500 transition-colors p-1"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Analysis */}
        <div className="lg:col-span-2 space-y-6">
          {/* Tabs */}
          <div className="flex gap-6 border-b border-zinc-200 pb-px">
            {[
              { id: 'timeline', label: 'Timeline', icon: Clock },
              { id: 'discrepancies', label: 'Discrepancies', icon: AlertTriangle },
              { id: 'policy', label: 'Policy Check', icon: CheckCircle },
              { id: 'search', label: 'Search', icon: Search },
            ].map(tab => {
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as AnalysisTab)}
                  className={`pb-2 text-[10px] font-medium uppercase tracking-wider transition-colors flex items-center gap-2 border-b-2 ${
                    activeTab === tab.id
                      ? 'border-zinc-900 text-zinc-900'
                      : 'border-transparent text-zinc-400 hover:text-zinc-600'
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          <div className="min-h-[400px]">
            {/* Timeline Tab */}
            {activeTab === 'timeline' && (
              <div className="space-y-8">
                <div className="flex justify-end">
                  <button
                    onClick={handleGenerateTimeline}
                    disabled={analysisLoading === 'timeline' || uploadedDocs.length === 0}
                    className="text-[10px] uppercase tracking-wider font-medium text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
                  >
                    {analysisLoading === 'timeline' ? 'Generating...' : 'Regenerate Analysis'}
                  </button>
                </div>

                {timelineSummary && (
                  <div className="text-sm text-zinc-600 dark:text-zinc-300 leading-relaxed font-serif">
                    {timelineSummary}
                  </div>
                )}

                {timeline.length === 0 ? (
                  <div className="text-center py-12 text-zinc-400 text-xs">
                    {analysisLoading === 'timeline' ? (
                      <div className="flex flex-col items-center gap-3">
                        <RefreshCw size={20} className="animate-spin text-zinc-500" />
                        <span>Analyzing documents and reconstructing timeline...</span>
                        <span className="text-[10px] text-zinc-500">This may take up to a minute</span>
                      </div>
                    ) : (
                      'No timeline data generated.'
                    )}
                  </div>
                ) : (
                  <div className="relative pl-2 space-y-8 border-l border-zinc-200 ml-2">
                    {timeline.map((event, i) => (
                      <div key={i} className="relative pl-6">
                        <div className="absolute left-[-3px] top-1.5 w-1.5 h-1.5 rounded-full bg-zinc-300" />
                        <div className="flex items-center gap-3 mb-1">
                          <span className="text-xs font-medium text-zinc-900 dark:text-zinc-100">
                            {event.date} {event.time && <span className="text-zinc-400 font-normal">at {event.time}</span>}
                          </span>
                          <span className={`text-[9px] uppercase tracking-wide font-medium ${
                            event.confidence === 'high' ? 'text-emerald-600' :
                            event.confidence === 'medium' ? 'text-amber-600' :
                            'text-red-600'
                          }`}>
                            {event.confidence}
                          </span>
                        </div>
                        <p className="text-zinc-800 dark:text-zinc-200 text-sm mb-2">{event.description}</p>
                        
                        <div className="flex flex-wrap gap-2 mb-2">
                          {event.participants.map(p => (
                            <span key={p} className="text-[10px] text-zinc-500 uppercase tracking-wide">
                              {p}
                            </span>
                          ))}
                        </div>

                        {event.evidence_quote && (
                          <div className="text-xs text-zinc-500 italic pl-2 border-l border-zinc-200">
                            "{event.evidence_quote}"
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {timelineGaps.length > 0 && (
                  <div className="pt-6 border-t border-zinc-100">
                    <h4 className="text-[10px] font-medium text-zinc-500 uppercase tracking-wider mb-3">Identified Gaps</h4>
                    <ul className="space-y-2">
                      {timelineGaps.map((gap, i) => (
                        <li key={i} className="text-xs text-zinc-600 flex items-start gap-2">
                          <span className="text-amber-500 mt-0.5">•</span>
                          {gap}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Discrepancies Tab */}
            {activeTab === 'discrepancies' && (
              <div className="space-y-8">
                <div className="flex justify-end">
                  <button
                    onClick={handleGenerateDiscrepancies}
                    disabled={analysisLoading === 'discrepancies' || uploadedDocs.filter(d => d.document_type !== 'policy').length < 2}
                    className="text-[10px] uppercase tracking-wider font-medium text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
                  >
                    {analysisLoading === 'discrepancies' ? 'Analyzing...' : 'Analyze Documents'}
                  </button>
                </div>

                {discrepancySummary && (
                  <div className="text-sm text-zinc-600 dark:text-zinc-300 leading-relaxed font-serif">
                    {discrepancySummary}
                  </div>
                )}

                {discrepancies.length === 0 ? (
                  <div className="text-center py-12 text-zinc-400 text-xs">
                    {analysisLoading === 'discrepancies' ? (
                      <div className="flex flex-col items-center gap-3">
                        <RefreshCw size={20} className="animate-spin text-zinc-500" />
                        <span>Comparing statements and detecting discrepancies...</span>
                        <span className="text-[10px] text-zinc-500">This may take up to a minute</span>
                      </div>
                    ) : (
                      'No discrepancies detected or analysis not run.'
                    )}
                  </div>
                ) : (
                  <div className="space-y-8">
                    {discrepancies.map((disc, i) => (
                      <div key={i} className="border-b border-zinc-100 pb-8 last:border-0 last:pb-0">
                        <div className="flex items-center gap-3 mb-2">
                          <span className={`text-[10px] uppercase tracking-wide font-medium ${
                            disc.severity === 'high' ? 'text-red-600' :
                            disc.severity === 'medium' ? 'text-amber-600' :
                            'text-zinc-500'
                          }`}>
                            {disc.severity} Severity
                          </span>
                          <span className="text-[10px] text-zinc-400 uppercase tracking-wide">•</span>
                          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{disc.type}</span>
                        </div>
                        
                        <p className="text-zinc-900 dark:text-zinc-100 text-sm font-medium mb-4">{disc.description}</p>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
                          <div>
                            <p className="text-[10px] text-zinc-500 mb-1 uppercase tracking-wide">
                              {disc.statement_1.speaker}
                            </p>
                            <p className="text-xs text-zinc-600 italic border-l border-zinc-200 pl-2">"{disc.statement_1.quote}"</p>
                          </div>
                          <div>
                            <p className="text-[10px] text-zinc-500 mb-1 uppercase tracking-wide">
                              {disc.statement_2.speaker}
                            </p>
                            <p className="text-xs text-zinc-600 italic border-l border-zinc-200 pl-2">"{disc.statement_2.quote}"</p>
                          </div>
                        </div>
                        
                        <div className="text-xs text-zinc-500 bg-zinc-50 p-3 rounded-sm">
                          {disc.analysis}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Policy Check Tab */}
            {activeTab === 'policy' && (
              <div className="space-y-8">
                <div className="flex justify-end">
                  <button
                    onClick={handleRunPolicyCheck}
                    disabled={analysisLoading === 'policy' || !uploadedDocs.find(d => d.document_type === 'policy')}
                    className="text-[10px] uppercase tracking-wider font-medium text-zinc-900 dark:text-zinc-100 hover:text-zinc-600 dark:hover:text-zinc-300 disabled:opacity-50"
                  >
                    {analysisLoading === 'policy' ? 'Checking...' : 'Run Policy Check'}
                  </button>
                </div>

                {violationSummary && (
                  <div className="text-sm text-zinc-600 dark:text-zinc-300 leading-relaxed font-serif">
                    {violationSummary}
                  </div>
                )}

                {violations.length === 0 ? (
                  <div className="text-center py-12 text-zinc-400 text-xs">
                    {analysisLoading === 'policy' ? (
                      <div className="flex flex-col items-center gap-3">
                        <RefreshCw size={20} className="animate-spin text-zinc-500" />
                        <span>Checking evidence against policy documents...</span>
                        <span className="text-[10px] text-zinc-500">This may take up to a minute</span>
                      </div>
                    ) : (
                      'No violations detected or check not run.'
                    )}
                  </div>
                ) : (
                  <div className="space-y-8">
                    {violations.map((v, i) => (
                      <div key={i} className="border-b border-zinc-100 dark:border-zinc-800 pb-8 last:border-0 last:pb-0">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`text-[10px] uppercase tracking-wide font-medium ${
                            v.severity === 'major' ? 'text-red-600' : 'text-amber-600'
                          }`}>
                            {v.severity} Violation
                          </span>
                        </div>

                        <h4 className="text-zinc-900 dark:text-zinc-100 text-sm font-medium mb-2">{v.policy_section}</h4>
                        <div className="mb-4">
                          <p className="text-xs text-zinc-500 dark:text-zinc-400 italic">"{v.policy_text}"</p>
                        </div>

                        <div className="space-y-3 pl-3 border-l-2 border-zinc-100 dark:border-zinc-700">
                          {v.evidence.map((e, j) => (
                            <div key={j}>
                              <p className="text-xs text-zinc-700 dark:text-zinc-300 mb-1">"{e.quote}"</p>
                              <p className="text-[10px] text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">→ {e.how_it_violates}</p>
                            </div>
                          ))}
                        </div>
                        
                        <div className="mt-4 text-xs text-zinc-500">
                          {v.analysis}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Search Tab */}
            {activeTab === 'search' && (
              <div className="space-y-6">
                <div className="flex gap-3">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-2.5 text-zinc-400" size={16} />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                      placeholder="Search evidence using natural language..."
                      className="w-full pl-10 pr-4 py-2 bg-white border border-zinc-200 rounded text-sm text-zinc-900 focus:outline-none focus:border-zinc-400 focus:ring-0"
                    />
                  </div>
                  <Button 
                    onClick={handleSearch} 
                    disabled={searching || !searchQuery.trim()}
                    className="bg-zinc-900 text-white hover:bg-zinc-800"
                  >
                    {searching ? 'Searching...' : 'Search'}
                  </Button>
                </div>

                {searchResults.length > 0 ? (
                  <div className="space-y-4">
                    {searchResults.map((result, i) => (
                      <div key={i} className="bg-white border border-zinc-200 rounded p-4 shadow-sm hover:border-zinc-300 transition-colors">
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wide rounded border ${DOC_TYPE_COLORS[result.document_type]}`}>
                            {result.document_type}
                          </span>
                          <span className="text-xs text-zinc-500 font-medium">{result.source_file}</span>
                          <span className="text-[10px] text-zinc-400 ml-auto font-mono">
                            {(result.similarity * 100).toFixed(0)}% Match
                          </span>
                        </div>
                        
                        {result.speaker && (
                          <p className="text-xs text-zinc-500 mb-1 font-medium uppercase tracking-wide">{result.speaker}</p>
                        )}
                        
                        <div className="text-sm text-zinc-800 leading-relaxed bg-zinc-50 p-3 rounded border border-zinc-100">
                          {result.content}
                        </div>
                        
                        {result.line_range && (
                          <div className="mt-2 flex justify-end">
                            <span className="text-[10px] text-zinc-400">Lines {result.line_range}</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12 text-zinc-500 text-sm">
                    {uploadedDocs.length === 0
                      ? 'Upload documents first.'
                      : 'Enter a query to search through case evidence using semantic similarity.'}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/20 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-white shadow-2xl rounded-sm flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-zinc-100">
              <h3 className="text-sm font-light text-zinc-900 uppercase tracking-wider">Upload Document</h3>
              <button 
                onClick={() => setShowUploadModal(false)}
                className="text-zinc-400 hover:text-zinc-600 transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">Document Type</label>
                <select
                  value={uploadDocType}
                  onChange={(e) => setUploadDocType(e.target.value as ERDocumentType)}
                  className="w-full px-3 py-2 bg-white border border-zinc-200 rounded-lg text-sm text-zinc-900 focus:outline-none focus:border-zinc-400"
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
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ERCaseDetail;