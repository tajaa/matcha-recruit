import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ChevronLeft,
  Download,
  Pencil,
  CheckCircle,
  Archive,
  Send,
  Save,
  AlertTriangle,
  Check,
  X,
} from 'lucide-react';
import { handbooks } from '../api/client';
import type {
  HandbookChangeRequest,
  HandbookDetail as HandbookDetailData,
  HandbookSection,
} from '../types';

function HandbookDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [handbook, setHandbook] = useState<HandbookDetailData | null>(null);
  const [sections, setSections] = useState<HandbookSection[]>([]);
  const [changes, setChanges] = useState<HandbookChangeRequest[]>([]);
  const [ackSummary, setAckSummary] = useState<{
    assigned_count: number;
    signed_count: number;
    pending_count: number;
    expired_count: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [distributionLoading, setDistributionLoading] = useState(false);

  const loadData = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      setLoadError(null);
      const [detail, changeRows, ack] = await Promise.all([
        handbooks.get(id),
        handbooks.listChanges(id).catch(() => []),
        handbooks.acknowledgements(id).catch(() => null),
      ]);
      setHandbook(detail);
      setSections(detail.sections || []);
      setChanges(changeRows || []);
      setAckSummary(ack);
    } catch (error) {
      console.error('Failed to load handbook detail:', error);
      setLoadError(error instanceof Error ? error.message : 'Failed to load handbook');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const pendingChanges = useMemo(
    () => changes.filter((change) => change.status === 'pending'),
    [changes],
  );

  const handleSectionChange = (index: number, content: string) => {
    setSections((prev) => prev.map((section, i) => (i === index ? { ...section, content } : section)));
  };

  const handleSaveSections = async () => {
    if (!id) return;
    try {
      setSaving(true);
      await handbooks.update(id, { sections });
      await loadData();
    } catch (error) {
      console.error('Failed to save handbook sections:', error);
      alert(error instanceof Error ? error.message : 'Failed to save handbook');
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    if (!id) return;
    if (!confirm('Publish this handbook? Any active handbook will be archived.')) return;
    try {
      await handbooks.publish(id);
      await loadData();
    } catch (error) {
      console.error('Failed to publish handbook:', error);
      alert(error instanceof Error ? error.message : 'Failed to publish handbook');
    }
  };

  const handleArchive = async () => {
    if (!id) return;
    if (!confirm('Archive this handbook?')) return;
    try {
      await handbooks.archive(id);
      await loadData();
    } catch (error) {
      console.error('Failed to archive handbook:', error);
      alert(error instanceof Error ? error.message : 'Failed to archive handbook');
    }
  };

  const handleDownload = async () => {
    if (!id || !handbook) return;
    try {
      await handbooks.downloadPdf(id, handbook.title);
    } catch (error) {
      console.error('Failed to download handbook PDF:', error);
      alert(error instanceof Error ? error.message : 'Failed to download handbook');
    }
  };

  const handleDistribute = async () => {
    if (!id) return;
    if (!confirm('Send this handbook to all active employees for e-signature?')) return;
    try {
      setDistributionLoading(true);
      const result = await handbooks.distribute(id);
      alert(`Distributed to ${result.assigned_count} employees (${result.skipped_existing_count} already assigned).`);
      await loadData();
    } catch (error) {
      console.error('Failed to distribute handbook:', error);
      alert(error instanceof Error ? error.message : 'Failed to distribute handbook');
    } finally {
      setDistributionLoading(false);
    }
  };

  const handleResolveChange = async (changeId: string, action: 'accept' | 'reject') => {
    if (!id) return;
    try {
      if (action === 'accept') {
        await handbooks.acceptChange(id, changeId);
      } else {
        await handbooks.rejectChange(id, changeId);
      }
      await loadData();
    } catch (error) {
      console.error(`Failed to ${action} handbook change:`, error);
      alert(error instanceof Error ? error.message : `Failed to ${action} change`);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-xs text-zinc-500 uppercase tracking-wider">Loading handbook...</div>
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="max-w-4xl mx-auto space-y-4 py-8">
        <div className="border border-red-500/30 bg-red-500/10 p-4 text-red-300 text-sm">
          {loadError}
        </div>
        <button
          onClick={() => navigate('/app/matcha/handbook')}
          className="text-xs text-zinc-400 hover:text-white uppercase tracking-wider"
        >
          Back to Handbooks
        </button>
      </div>
    );
  }
  if (!handbook) {
    return (
      <div className="max-w-4xl mx-auto space-y-4 py-8">
        <div className="border border-white/10 bg-zinc-900/40 p-4 text-zinc-300 text-sm">
          Handbook not found.
        </div>
        <button
          onClick={() => navigate('/app/matcha/handbook')}
          className="text-xs text-zinc-400 hover:text-white uppercase tracking-wider"
        >
          Back to Handbooks
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-10">
      <div className="flex items-start justify-between">
        <div className="space-y-3">
          <button
            onClick={() => navigate('/app/matcha/handbook')}
            className="text-[10px] text-zinc-500 hover:text-zinc-300 transition-colors uppercase tracking-wider flex items-center gap-1"
          >
            <ChevronLeft size={12} /> Back to Handbooks
          </button>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] text-zinc-500 font-mono tracking-wide uppercase">HANDBOOK</span>
              <span className="text-[10px] uppercase tracking-wide font-medium text-zinc-400 bg-zinc-900 px-1.5 py-0.5 rounded border border-zinc-700">
                v{handbook.active_version}
              </span>
              <span className={`text-[10px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded border ${
                handbook.status === 'active'
                  ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
                  : handbook.status === 'draft'
                  ? 'text-zinc-400 border-zinc-700 bg-zinc-900'
                  : 'text-zinc-500 border-zinc-800 bg-zinc-950'
              }`}>
                {handbook.status}
              </span>
            </div>
            <h1 className="text-3xl font-light tracking-tight text-white">{handbook.title}</h1>
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-mono mt-1">
              {handbook.mode === 'multi_state' ? 'Multi-State' : 'Single-State'} • {(handbook.scopes || []).map((scope) => scope.state).join(', ')}
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => navigate(`/app/matcha/handbook/${handbook.id}/edit`)}
            className="flex items-center gap-1.5 text-[10px] text-zinc-300 hover:text-white uppercase tracking-wider font-medium px-3 py-2 transition-colors border border-zinc-700 hover:border-zinc-500"
          >
            <Pencil size={12} />
            Edit Setup
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 text-[10px] text-zinc-300 hover:text-white uppercase tracking-wider font-medium px-3 py-2 transition-colors border border-zinc-700 hover:border-zinc-500"
          >
            <Download size={12} />
            PDF
          </button>
          {handbook.status !== 'active' && (
            <button
              onClick={handlePublish}
              className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] uppercase tracking-wider font-medium px-4 py-2 transition-colors"
            >
              <CheckCircle size={12} />
              Publish
            </button>
          )}
          {handbook.status !== 'archived' && (
            <button
              onClick={handleArchive}
              className="flex items-center gap-1.5 text-[10px] text-zinc-300 hover:text-white uppercase tracking-wider font-medium px-3 py-2 transition-colors border border-zinc-700 hover:border-zinc-500"
            >
              <Archive size={12} />
              Archive
            </button>
          )}
          {handbook.status === 'active' && (
            <button
              onClick={handleDistribute}
              disabled={distributionLoading}
              className="flex items-center gap-1.5 bg-sky-600 hover:bg-sky-700 text-white text-[10px] uppercase tracking-wider font-medium px-4 py-2 transition-colors disabled:opacity-50"
            >
              <Send size={12} />
              {distributionLoading ? 'Sending...' : 'Send E-Sign'}
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-8">
          <div className="border border-white/10 bg-zinc-950 p-5">
            <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-4">
              <h2 className="text-[10px] uppercase tracking-widest text-zinc-400">Handbook Sections</h2>
              <button
                onClick={handleSaveSections}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-wider bg-white text-black hover:bg-zinc-200 disabled:opacity-50"
              >
                <Save size={12} />
                {saving ? 'Saving...' : 'Save Sections'}
              </button>
            </div>
            <div className="space-y-4">
              {sections.map((section, index) => (
                <div key={section.id || `${section.section_key}-${index}`} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm text-white">{section.title}</h3>
                    <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{section.section_type}</span>
                  </div>
                  <textarea
                    value={section.content}
                    onChange={(e) => handleSectionChange(index, e.target.value)}
                    className="w-full min-h-[130px] px-3 py-3 bg-zinc-900 border border-white/10 text-sm text-zinc-100 focus:outline-none focus:border-white/30 resize-y"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="border border-white/10 bg-zinc-950 p-5">
            <div className="flex items-center gap-2 border-b border-white/10 pb-3 mb-4">
              <AlertTriangle size={14} className="text-amber-400" />
              <h2 className="text-[10px] uppercase tracking-widest text-zinc-400">Pending Legal Changes</h2>
            </div>
            {pendingChanges.length === 0 ? (
              <p className="text-sm text-zinc-500">No pending handbook language changes.</p>
            ) : (
              <div className="space-y-4">
                {pendingChanges.map((change) => (
                  <div key={change.id} className="border border-amber-500/20 bg-amber-500/5 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-zinc-300 uppercase tracking-wider">
                        Section: {change.section_key || 'general'}
                      </p>
                      <p className="text-[10px] text-zinc-500">{new Date(change.created_at).toLocaleDateString()}</p>
                    </div>
                    {change.rationale && <p className="text-xs text-zinc-400">{change.rationale}</p>}
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Proposed Content</p>
                      <div className="text-xs text-zinc-300 whitespace-pre-wrap">{change.proposed_content}</div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleResolveChange(change.id, 'accept')}
                        className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] uppercase tracking-wider"
                      >
                        <Check size={12} />
                        Accept
                      </button>
                      <button
                        onClick={() => handleResolveChange(change.id, 'reject')}
                        className="flex items-center gap-1 px-3 py-1.5 border border-zinc-600 hover:border-zinc-500 text-zinc-200 text-[10px] uppercase tracking-wider"
                      >
                        <X size={12} />
                        Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="border border-white/10 bg-zinc-950 p-5 space-y-3">
            <h2 className="text-[10px] uppercase tracking-widest text-zinc-400 border-b border-white/10 pb-2">Employer Profile</h2>
            <div className="text-sm text-zinc-200">{handbook.profile.legal_name}</div>
            <div className="text-xs text-zinc-500">DBA: {handbook.profile.dba || 'N/A'}</div>
            <div className="text-xs text-zinc-500">CEO/President: {handbook.profile.ceo_or_president}</div>
            <div className="text-xs text-zinc-500">Headcount: {handbook.profile.headcount ?? 'N/A'}</div>
          </div>

          <div className="border border-white/10 bg-zinc-950 p-5 space-y-3">
            <h2 className="text-[10px] uppercase tracking-widest text-zinc-400 border-b border-white/10 pb-2">Acknowledgements</h2>
            <div className="text-xs text-zinc-400">Assigned: {ackSummary?.assigned_count ?? 0}</div>
            <div className="text-xs text-emerald-400">Signed: {ackSummary?.signed_count ?? 0}</div>
            <div className="text-xs text-amber-400">Pending: {ackSummary?.pending_count ?? 0}</div>
            <div className="text-xs text-zinc-500">Expired: {ackSummary?.expired_count ?? 0}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default HandbookDetailPage;
