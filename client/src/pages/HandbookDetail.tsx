import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Download,
  Pencil,
  CheckCircle,
  Archive,
  Send,
  Save,
  AlertTriangle,
  Check,
  Star,
  X,
  RefreshCw,
} from 'lucide-react';
import { handbooks } from '../api/client';
import type {
  HandbookChangeRequest,
  HandbookDetail as HandbookDetailData,
  HandbookFreshnessCheck,
  HandbookSection,
} from '../types';
import HandbookDistributeModal from '../components/HandbookDistributeModal';

const getSectionTabId = (section: HandbookSection, index: number) =>
  section.id || `${section.section_key}-${index}`;

const SECTION_TYPE_ORDER: HandbookSection['section_type'][] = ['core', 'state', 'custom', 'uploaded'];

const SECTION_TYPE_LABELS: Record<HandbookSection['section_type'], string> = {
  core: 'Core Policies',
  state: 'State Addenda',
  custom: 'Company Custom',
  uploaded: 'Uploaded Content',
};

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
  const [freshnessLoading, setFreshnessLoading] = useState(false);
  const [showDistributeModal, setShowDistributeModal] = useState(false);
  const [freshnessCheck, setFreshnessCheck] = useState<HandbookFreshnessCheck | null>(null);
  const [activeSectionTabId, setActiveSectionTabId] = useState<string | null>(null);
  const [sectionSearch, setSectionSearch] = useState('');
  const [highlightedSectionTabIds, setHighlightedSectionTabIds] = useState<string[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<Record<string, boolean>>({});

  const highlightStorageKey = useMemo(
    () => (id ? `handbook:highlighted-sections:${id}` : null),
    [id]
  );

  const loadData = useCallback(async () => {
    if (!id) return;
    try {
      setLoading(true);
      setLoadError(null);
      const [detail, changeRows, ack, latestFreshness] = await Promise.all([
        handbooks.get(id),
        handbooks.listChanges(id).catch(() => []),
        handbooks.acknowledgements(id).catch(() => null),
        handbooks.getLatestFreshnessCheck(id).catch(() => null),
      ]);
      setHandbook(detail);
      setSections(detail.sections || []);
      setChanges(changeRows || []);
      setAckSummary(ack);
      setFreshnessCheck(latestFreshness);
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

  useEffect(() => {
    if (!sections.length) {
      setActiveSectionTabId(null);
      return;
    }
    setActiveSectionTabId((prev) => {
      if (prev && sections.some((section, index) => getSectionTabId(section, index) === prev)) {
        return prev;
      }
      return getSectionTabId(sections[0], 0);
    });
  }, [sections]);

  useEffect(() => {
    if (!highlightStorageKey) {
      setHighlightedSectionTabIds([]);
      return;
    }
    try {
      const raw = localStorage.getItem(highlightStorageKey);
      if (!raw) {
        setHighlightedSectionTabIds([]);
        return;
      }
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setHighlightedSectionTabIds(
          parsed.filter((value): value is string => typeof value === 'string')
        );
        return;
      }
      setHighlightedSectionTabIds([]);
    } catch {
      setHighlightedSectionTabIds([]);
    }
  }, [highlightStorageKey]);

  useEffect(() => {
    if (!highlightStorageKey) return;
    try {
      localStorage.setItem(highlightStorageKey, JSON.stringify(highlightedSectionTabIds));
    } catch {
      // Ignore localStorage write errors (private mode/quota)
    }
  }, [highlightStorageKey, highlightedSectionTabIds]);

  const activeSectionIndex = useMemo(() => {
    if (!activeSectionTabId) return 0;
    const index = sections.findIndex(
      (section, idx) => getSectionTabId(section, idx) === activeSectionTabId
    );
    return index >= 0 ? index : 0;
  }, [activeSectionTabId, sections]);

  const activeSection = sections[activeSectionIndex] || null;

  const sectionByTabId = useMemo(() => {
    const byId = new Map<string, { section: HandbookSection; index: number }>();
    sections.forEach((section, index) => {
      byId.set(getSectionTabId(section, index), { section, index });
    });
    return byId;
  }, [sections]);

  useEffect(() => {
    if (!highlightedSectionTabIds.length) return;
    setHighlightedSectionTabIds((prev) => {
      const next = prev.filter((tabId) => sectionByTabId.has(tabId));
      return next.length === prev.length ? prev : next;
    });
  }, [highlightedSectionTabIds.length, sectionByTabId]);

  const highlightedSet = useMemo(
    () => new Set(highlightedSectionTabIds),
    [highlightedSectionTabIds]
  );

  const dirtySectionIds = useMemo(() => {
    const originalContent = new Map(
      (handbook?.sections || []).map((section, index) => [getSectionTabId(section, index), section.content])
    );
    const dirty = new Set<string>();
    sections.forEach((section, index) => {
      const id = getSectionTabId(section, index);
      const before = originalContent.get(id) ?? '';
      if ((section.content || '') !== before) {
        dirty.add(id);
      }
    });
    return dirty;
  }, [handbook?.sections, sections]);

  const sectionKeyToIndex = useMemo(() => {
    const indexByKey = new Map<string, number>();
    sections.forEach((section, index) => {
      if (!section.section_key) return;
      if (!indexByKey.has(section.section_key)) {
        indexByKey.set(section.section_key, index);
      }
    });
    return indexByKey;
  }, [sections]);

  const filteredSectionEntries = useMemo(() => {
    const search = sectionSearch.trim().toLowerCase();
    const entries = sections.map((section, index) => {
      const tabId = getSectionTabId(section, index);
      return {
        section,
        index,
        tabId,
        isDirty: dirtySectionIds.has(tabId),
        isHighlighted: highlightedSet.has(tabId),
      };
    });
    if (!search) return entries;
    return entries.filter(({ section }) => {
      const haystack = `${section.title} ${section.section_key} ${section.section_type}`.toLowerCase();
      return haystack.includes(search);
    });
  }, [dirtySectionIds, highlightedSet, sectionSearch, sections]);

  const groupedSectionEntries = useMemo(() => {
    const grouped = new Map<HandbookSection['section_type'], typeof filteredSectionEntries>();
    for (const entry of filteredSectionEntries) {
      const key = entry.section.section_type;
      const bucket = grouped.get(key);
      if (bucket) {
        bucket.push(entry);
      } else {
        grouped.set(key, [entry]);
      }
    }

    return SECTION_TYPE_ORDER
      .map((sectionType) => ({
        sectionType,
        label: SECTION_TYPE_LABELS[sectionType],
        entries: grouped.get(sectionType) || [],
      }))
      .filter((group) => group.entries.length > 0);
  }, [filteredSectionEntries]);

  const jumpToSection = (sectionKey: string | null) => {
    if (!sectionKey) return;
    const index = sectionKeyToIndex.get(sectionKey);
    if (index === undefined) return;
    const tabId = getSectionTabId(sections[index], index);
    setActiveSectionTabId(tabId);

    if (sectionSearch.trim()) {
      const target = sections[index];
      const haystack = `${target.title} ${target.section_key} ${target.section_type}`.toLowerCase();
      if (!haystack.includes(sectionSearch.trim().toLowerCase())) {
        setSectionSearch('');
      }
    }
  };

  const toggleSectionHighlight = (tabId: string) => {
    setHighlightedSectionTabIds((prev) => (
      prev.includes(tabId)
        ? prev.filter((value) => value !== tabId)
        : [...prev, tabId]
    ));
  };

  const activeSectionIsHighlighted = activeSection
    ? highlightedSet.has(getSectionTabId(activeSection, activeSectionIndex))
    : false;

  const notebookEdgeTabs = useMemo(
    () => sections.map((section, index) => {
      const tabId = getSectionTabId(section, index);
      return {
        tabId,
        index,
        title: section.title,
        isActive: tabId === activeSectionTabId,
        isDirty: dirtySectionIds.has(tabId),
        isHighlighted: highlightedSet.has(tabId),
      };
    }),
    [activeSectionTabId, dirtySectionIds, highlightedSet, sections]
  );

  const highlightedSectionEntries = useMemo(
    () => highlightedSectionTabIds
      .map((tabId) => {
        const entry = sectionByTabId.get(tabId);
        if (!entry) return null;
        return { tabId, section: entry.section, index: entry.index };
      })
      .filter((value): value is { tabId: string; section: HandbookSection; index: number } => Boolean(value)),
    [highlightedSectionTabIds, sectionByTabId]
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

  const handleDistribute = () => {
    if (!id || distributionLoading) return;
    setShowDistributeModal(true);
  };

  const handleRunFreshnessCheck = async () => {
    if (!id || freshnessLoading) return;
    try {
      setFreshnessLoading(true);
      const result = await handbooks.runFreshnessCheck(id);
      setFreshnessCheck(result);
      await loadData();
      if (result.new_change_requests_count > 0) {
        alert(
          `Freshness check found ${result.impacted_sections} impacted section(s) and created ${result.new_change_requests_count} pending change request(s).`
        );
      } else if (result.is_outdated) {
        alert(
          `Freshness check found requirement changes, but no new change requests were created (likely already pending).`
        );
      } else {
        alert('Handbook appears up to date with current requirement data.');
      }
    } catch (error) {
      console.error('Failed to run handbook freshness check:', error);
      alert(error instanceof Error ? error.message : 'Failed to run freshness check');
    } finally {
      setFreshnessLoading(false);
    }
  };

  const handleConfirmDistribution = async (employeeIds?: string[]) => {
    if (!id || distributionLoading) return;
    try {
      setDistributionLoading(true);
      const result = await handbooks.distribute(id, employeeIds);
      alert(`Distributed to ${result.assigned_count} employees (${result.skipped_existing_count} already assigned).`);
      setShowDistributeModal(false);
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

  const toggleSidebarPanel = (key: string) =>
    setSidebarCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="space-y-8">
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
          {handbook.status !== 'archived' && (
            <button
              onClick={handleRunFreshnessCheck}
              disabled={freshnessLoading}
              className="flex items-center gap-1.5 text-[10px] text-zinc-300 hover:text-white uppercase tracking-wider font-medium px-3 py-2 transition-colors border border-zinc-700 hover:border-zinc-500 disabled:opacity-50"
            >
              <RefreshCw size={12} className={freshnessLoading ? 'animate-spin' : ''} />
              {freshnessLoading ? 'Checking...' : 'Check Updates'}
            </button>
          )}
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

      {/* Info panels — compact row above the editor */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Highlighted Sections */}
        <div className="border border-white/10 bg-zinc-950">
          <button
            type="button"
            onClick={() => toggleSidebarPanel('highlights')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-zinc-900 transition-colors"
          >
            <span className="text-[9px] uppercase tracking-widest text-zinc-400 flex items-center gap-1.5">
              <Star size={9} className={highlightedSectionEntries.length ? 'text-amber-300 fill-current' : ''} />
              Highlights
              {highlightedSectionEntries.length > 0 && (
                <span className="bg-amber-500/20 text-amber-300 px-1 rounded text-[9px]">{highlightedSectionEntries.length}</span>
              )}
            </span>
            <ChevronDown size={10} className={`text-zinc-500 transition-transform ${sidebarCollapsed['highlights'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['highlights'] && (
            <div className="px-2 pb-2 space-y-1 border-t border-white/10">
              {highlightedSectionEntries.length === 0 ? (
                <p className="text-[10px] text-zinc-600 px-1 py-2">None yet. Highlight sections from the editor.</p>
              ) : (
                <>
                  {highlightedSectionEntries.map((entry) => (
                    <button
                      key={entry.tabId}
                      type="button"
                      onClick={() => setActiveSectionTabId(entry.tabId)}
                      className="w-full text-left px-2 py-1.5 border border-amber-400/30 bg-amber-500/10 hover:border-amber-300 transition-colors"
                    >
                      <span className="text-[10px] font-mono text-amber-100 truncate block">{entry.index + 1}. {entry.section.title}</span>
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setHighlightedSectionTabIds([])}
                    className="w-full px-2 py-1 border border-white/10 text-zinc-500 hover:text-white text-[9px] uppercase tracking-wider transition-colors"
                  >
                    Clear
                  </button>
                </>
              )}
            </div>
          )}
        </div>

        {/* Freshness Check */}
        <div className="border border-white/10 bg-zinc-950">
          <button
            type="button"
            onClick={() => toggleSidebarPanel('freshness')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-zinc-900 transition-colors"
          >
            <span className="text-[9px] uppercase tracking-widest text-zinc-400 flex items-center gap-1.5">
              <RefreshCw size={9} className={freshnessCheck?.is_outdated ? 'text-amber-300' : ''} />
              Freshness
            </span>
            <ChevronDown size={10} className={`text-zinc-500 transition-transform ${sidebarCollapsed['freshness'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['freshness'] && (
            <div className="px-3 pb-3 space-y-1.5 border-t border-white/10 pt-2">
              {!freshnessCheck ? (
                <p className="text-[10px] text-zinc-600">No checks run yet.</p>
              ) : (
                <>
                  <div className={`text-[10px] font-medium ${
                    freshnessCheck.status === 'running' ? 'text-sky-300'
                    : freshnessCheck.status === 'failed' ? 'text-red-400'
                    : freshnessCheck.is_outdated ? 'text-amber-300'
                    : 'text-emerald-300'
                  }`}>
                    {freshnessCheck.status === 'running' ? 'In progress'
                      : freshnessCheck.status === 'failed' ? 'Failed'
                      : freshnessCheck.is_outdated ? 'Updates detected'
                      : 'Up to date'}
                  </div>
                  <div className="text-[10px] text-zinc-500">{new Date(freshnessCheck.checked_at).toLocaleDateString()}</div>
                  <div className="text-[10px] text-zinc-400">{freshnessCheck.impacted_sections} impacted</div>
                  <div className="text-[10px] text-zinc-400">{freshnessCheck.new_change_requests_count} new requests</div>
                </>
              )}
            </div>
          )}
        </div>

        {/* Employer Profile */}
        <div className="border border-white/10 bg-zinc-950">
          <button
            type="button"
            onClick={() => toggleSidebarPanel('profile')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-zinc-900 transition-colors"
          >
            <span className="text-[9px] uppercase tracking-widest text-zinc-400">Employer</span>
            <ChevronDown size={10} className={`text-zinc-500 transition-transform ${sidebarCollapsed['profile'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['profile'] && (
            <div className="px-3 pb-3 space-y-1 border-t border-white/10 pt-2">
              <div className="text-[11px] text-zinc-200 font-medium">{handbook.profile.legal_name}</div>
              <div className="text-[10px] text-zinc-500">DBA: {handbook.profile.dba || 'N/A'}</div>
              <div className="text-[10px] text-zinc-500">CEO: {handbook.profile.ceo_or_president}</div>
              <div className="text-[10px] text-zinc-500">Headcount: {handbook.profile.headcount ?? 'N/A'}</div>
            </div>
          )}
        </div>

        {/* Acknowledgements */}
        <div className="border border-white/10 bg-zinc-950">
          <button
            type="button"
            onClick={() => toggleSidebarPanel('acks')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-zinc-900 transition-colors"
          >
            <span className="text-[9px] uppercase tracking-widest text-zinc-400">Acknowledgements</span>
            <ChevronDown size={10} className={`text-zinc-500 transition-transform ${sidebarCollapsed['acks'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['acks'] && (
            <div className="px-3 pb-3 space-y-1 border-t border-white/10 pt-2">
              <div className="text-[10px] text-zinc-400">Assigned: {ackSummary?.assigned_count ?? 0}</div>
              <div className="text-[10px] text-emerald-400">Signed: {ackSummary?.signed_count ?? 0}</div>
              <div className="text-[10px] text-amber-400">Pending: {ackSummary?.pending_count ?? 0}</div>
              <div className="text-[10px] text-zinc-500">Expired: {ackSummary?.expired_count ?? 0}</div>
            </div>
          )}
        </div>
      </div>

      <div className="space-y-8">
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
            {!sections.length ? (
              <p className="text-sm text-zinc-500">No sections found for this handbook version.</p>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)] gap-4">
                <div className="border border-white/10 bg-zinc-900/40 max-h-[560px] overflow-y-auto">
                  <div className="p-2 space-y-2">
                    <div className="space-y-2">
                      <input
                        type="text"
                        value={sectionSearch}
                        onChange={(e) => setSectionSearch(e.target.value)}
                        placeholder="Search sections..."
                        className="w-full px-2.5 py-2 bg-zinc-950 border border-white/15 text-[11px] text-zinc-200 focus:outline-none focus:border-white/40"
                      />
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500">
                        Showing {filteredSectionEntries.length} of {sections.length}
                      </p>
                    </div>

                    {groupedSectionEntries.length === 0 ? (
                      <div className="px-2 py-4 text-[11px] text-zinc-500 border border-white/10 bg-zinc-950/70">
                        No matching sections.
                      </div>
                    ) : (
                      groupedSectionEntries.map((group) => (
                        <div key={group.sectionType} className="space-y-1.5">
                          <p className="px-1 text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                            {group.label}
                          </p>
                          {group.entries.map(({ section, index, tabId, isDirty, isHighlighted }) => {
                            const selected = tabId === activeSectionTabId;
                            return (
                              <button
                                key={tabId}
                                type="button"
                                onClick={() => setActiveSectionTabId(tabId)}
                                className={`w-full text-left px-2.5 py-2 border transition-colors ${
                                  selected
                                    ? 'bg-white text-black border-white'
                                    : 'bg-zinc-950/80 text-zinc-300 border-white/10 hover:border-white/30'
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-[10px] uppercase tracking-wider font-mono truncate">
                                    {index + 1}. {section.title}
                                  </span>
                                  <div className="flex items-center gap-1">
                                    {isHighlighted && (
                                      <Star size={10} className={selected ? 'text-black/70 fill-current' : 'text-amber-300 fill-current'} />
                                    )}
                                    {isDirty && (
                                      <span className={`text-[9px] uppercase tracking-wider ${selected ? 'text-black/70' : 'text-amber-400'}`}>
                                        edited
                                      </span>
                                    )}
                                  </div>
                                </div>
                                <div className={`text-[10px] uppercase tracking-wider mt-1 ${selected ? 'text-black/70' : 'text-zinc-500'}`}>
                                  {section.section_type}
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="space-y-3">
                  {activeSection ? (
                    <div className="flex gap-2">
                      <div className="flex-1 space-y-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="text-sm text-white">{activeSection.title}</h3>
                            <p className="text-[10px] text-zinc-500 uppercase tracking-wider mt-1">
                              Section {activeSectionIndex + 1} of {sections.length} • {activeSection.section_type}
                            </p>
                            <p className="text-[10px] text-zinc-600 font-mono mt-1">{activeSection.section_key}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => toggleSectionHighlight(getSectionTabId(activeSection, activeSectionIndex))}
                              className={`px-2 py-1 border text-[10px] uppercase tracking-wider inline-flex items-center gap-1 ${
                                activeSectionIsHighlighted
                                  ? 'border-amber-400/50 bg-amber-500/10 text-amber-300'
                                  : 'border-white/20 text-zinc-300 hover:text-white'
                              }`}
                            >
                              <Star size={10} className={activeSectionIsHighlighted ? 'fill-current' : ''} />
                              {activeSectionIsHighlighted ? 'Highlighted' : 'Highlight'}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                const prevIndex = Math.max(0, activeSectionIndex - 1);
                                setActiveSectionTabId(getSectionTabId(sections[prevIndex], prevIndex));
                              }}
                              disabled={activeSectionIndex === 0}
                              className="px-2 py-1 border border-white/20 text-zinc-300 hover:text-white text-[10px] uppercase tracking-wider disabled:opacity-40"
                            >
                              <span className="inline-flex items-center gap-1">
                                <ChevronLeft size={11} />
                                Prev
                              </span>
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                const nextIndex = Math.min(sections.length - 1, activeSectionIndex + 1);
                                setActiveSectionTabId(getSectionTabId(sections[nextIndex], nextIndex));
                              }}
                              disabled={activeSectionIndex >= sections.length - 1}
                              className="px-2 py-1 border border-white/20 text-zinc-300 hover:text-white text-[10px] uppercase tracking-wider disabled:opacity-40"
                            >
                              <span className="inline-flex items-center gap-1">
                                Next
                                <ChevronRight size={11} />
                              </span>
                            </button>
                          </div>
                        </div>
                        <textarea
                          value={activeSection.content}
                          onChange={(e) => handleSectionChange(activeSectionIndex, e.target.value)}
                          className="w-full min-h-[420px] px-3 py-3 bg-zinc-900 border border-white/10 text-sm text-zinc-100 font-serif leading-[1.5] focus:outline-none focus:border-white/30 resize-y"
                        />
                      </div>
                      <div className="flex-shrink-0 w-8">
                        <div className="flex flex-col gap-0.5">
                          {notebookEdgeTabs.map((tab) => (
                            <div key={tab.tabId} className="relative group">
                              <button
                                type="button"
                                onClick={() => setActiveSectionTabId(tab.tabId)}
                                className={`h-[80px] w-8 border flex items-center justify-center transition-colors ${
                                  tab.isActive
                                    ? 'bg-white text-black border-white'
                                    : tab.isHighlighted
                                    ? 'bg-amber-500/15 text-amber-100 border-amber-400/50 hover:bg-amber-500/25'
                                    : 'bg-zinc-800 text-zinc-200 border-zinc-600 hover:bg-zinc-700 hover:text-white'
                                }`}
                                style={{ writingMode: 'vertical-rl' }}
                              >
                                <span className="text-[8px] uppercase tracking-widest truncate">
                                  {tab.index + 1}. {tab.title}
                                </span>
                                {tab.isDirty && <span className={tab.isActive ? 'text-black/60' : 'text-amber-400'}> •</span>}
                              </button>
                              {/* Hover label floats to the left */}
                              <div className="absolute right-full top-1/2 -translate-y-1/2 pr-1.5 hidden group-hover:block z-50 pointer-events-none">
                                <div className={`px-2.5 py-1.5 text-[10px] uppercase tracking-widest whitespace-nowrap border ${
                                  tab.isActive
                                    ? 'bg-white text-black border-white'
                                    : tab.isHighlighted
                                    ? 'bg-zinc-900 text-amber-200 border-amber-400/50'
                                    : 'bg-zinc-900 text-zinc-100 border-zinc-600'
                                }`}>
                                  {tab.index + 1}. {tab.title}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            )}
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
                      <div className="text-xs text-zinc-300 whitespace-pre-wrap font-serif leading-[1.5]">{change.proposed_content}</div>
                        </div>
                        <div className="flex justify-end">
                          <button
                            type="button"
                            onClick={() => jumpToSection(change.section_key)}
                            disabled={!change.section_key || !sectionKeyToIndex.has(change.section_key)}
                            className="px-2.5 py-1 border border-zinc-600 hover:border-zinc-500 text-zinc-300 hover:text-white text-[10px] uppercase tracking-wider disabled:opacity-40"
                          >
                            Jump to section
                          </button>
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

      <HandbookDistributeModal
        open={showDistributeModal}
        handbookId={id ?? null}
        handbookTitle={handbook.title}
        submitting={distributionLoading}
        onClose={() => {
          if (!distributionLoading) setShowDistributeModal(false);
        }}
        onSubmit={handleConfirmDistribution}
      />
    </div>
  );
}

export default HandbookDetailPage;
