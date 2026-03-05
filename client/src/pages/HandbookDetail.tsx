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
import { useIsLightMode } from '../hooks/useIsLightMode';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  textMain: 'text-zinc-900',
  textSecondary: 'text-zinc-700',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-xl',
  panelBg: 'bg-stone-200 rounded-2xl',
  panelBorder: 'border-stone-300',
  panelHover: 'hover:bg-stone-100',
  panelHeader: 'text-stone-500',
  panelChevron: 'text-stone-400',
  panelText: 'text-zinc-700',
  panelTextMuted: 'text-stone-500',
  editorBg: 'bg-stone-100 rounded-2xl',
  editorBorder: 'border-stone-200',
  sidebarBg: 'bg-stone-200/60',
  sidebarBorder: 'border-stone-200',
  sidebarInput: 'bg-white border border-stone-300 text-zinc-900 focus:outline-none focus:border-stone-400',
  sidebarSelected: 'bg-zinc-900 text-zinc-50 border-zinc-900',
  sidebarUnselected: 'bg-white text-zinc-700 border-stone-200 hover:border-stone-400',
  sidebarSelectedSub: 'text-zinc-300',
  sidebarUnselectedSub: 'text-stone-500',
  editorTitle: 'text-zinc-900',
  editorSub: 'text-stone-500',
  editorKey: 'text-stone-400',
  textarea: 'bg-white border border-stone-300 text-zinc-900 font-serif leading-[1.5] focus:outline-none focus:border-stone-400 resize-y rounded-xl',
  tabActive: 'bg-zinc-900 text-zinc-50 border-zinc-900',
  tabHighlighted: 'bg-amber-100 text-amber-800 border-amber-300 hover:bg-amber-200',
  tabDefault: 'bg-stone-200 text-zinc-700 border-stone-300 hover:bg-stone-100 hover:text-zinc-900',
  tabHoverLabel: 'bg-stone-100 text-zinc-900 border-stone-300',
  tabHoverHighlighted: 'bg-amber-50 text-amber-800 border-amber-300',
  navBtn: 'border border-stone-300 text-stone-600 hover:text-zinc-900',
  highlightBtn: 'border-amber-400/50 bg-amber-100 text-amber-700',
  highlightBtnOff: 'border-stone-300 text-stone-600 hover:text-zinc-900',
  highlightEntry: 'border border-amber-300 bg-amber-50 hover:border-amber-400',
  highlightEntryText: 'text-amber-800',
  clearHighlights: 'border border-stone-300 text-stone-500 hover:text-zinc-900',
  changeCard: 'border border-amber-300 bg-amber-50 rounded-xl',
  changeSection: 'text-zinc-700',
  changeDate: 'text-stone-500',
  changeRationale: 'text-stone-600',
  changeProposedLabel: 'text-stone-500',
  changeProposedText: 'text-zinc-700',
  jumpBtn: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-lg',
  acceptBtn: 'bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg',
  rejectBtn: 'border border-stone-300 hover:border-stone-400 text-zinc-700 rounded-lg',
  statusBadge: {
    active: 'text-emerald-700 border-emerald-300 bg-emerald-50',
    draft: 'text-stone-500 border-stone-300 bg-stone-200',
    archived: 'text-stone-400 border-stone-300 bg-stone-100',
  } as Record<string, string>,
  versionBadge: 'text-stone-500 bg-stone-200 border-stone-300',
  publishBtn: 'bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl',
  archiveBtn: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900 rounded-xl',
  distributeBtn: 'bg-sky-600 hover:bg-sky-700 text-white rounded-xl',
  saveBtn: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  markReviewedBtn: 'text-stone-500 hover:text-emerald-600',
  errorBg: 'border border-red-300 bg-red-50 text-red-700 rounded-xl',
  errorBack: 'text-stone-500 hover:text-zinc-900',
  notFoundBg: 'border border-stone-200 bg-stone-100 text-stone-600 rounded-xl',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  textMain: 'text-zinc-100',
  textSecondary: 'text-zinc-300',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100 rounded-xl',
  panelBg: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  panelBorder: 'border-white/10',
  panelHover: 'hover:bg-zinc-900',
  panelHeader: 'text-zinc-400',
  panelChevron: 'text-zinc-500',
  panelText: 'text-zinc-200',
  panelTextMuted: 'text-zinc-500',
  editorBg: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  editorBorder: 'border-white/10',
  sidebarBg: 'bg-zinc-900/40',
  sidebarBorder: 'border-white/10',
  sidebarInput: 'bg-zinc-950 border border-white/15 text-zinc-200 focus:outline-none focus:border-white/40',
  sidebarSelected: 'bg-white text-black border-white',
  sidebarUnselected: 'bg-zinc-950/80 text-zinc-300 border-white/10 hover:border-white/30',
  sidebarSelectedSub: 'text-black/70',
  sidebarUnselectedSub: 'text-zinc-500',
  editorTitle: 'text-white',
  editorSub: 'text-zinc-500',
  editorKey: 'text-zinc-600',
  textarea: 'bg-zinc-900 border border-white/10 text-zinc-100 font-serif leading-[1.5] focus:outline-none focus:border-white/30 resize-y rounded-xl',
  tabActive: 'bg-white text-black border-white',
  tabHighlighted: 'bg-amber-500/15 text-amber-100 border-amber-400/50 hover:bg-amber-500/25',
  tabDefault: 'bg-zinc-800 text-zinc-200 border-zinc-600 hover:bg-zinc-700 hover:text-white',
  tabHoverLabel: 'bg-zinc-900 text-zinc-100 border-zinc-600',
  tabHoverHighlighted: 'bg-zinc-900 text-amber-200 border-amber-400/50',
  navBtn: 'border border-white/20 text-zinc-300 hover:text-white',
  highlightBtn: 'border-amber-400/50 bg-amber-500/10 text-amber-300',
  highlightBtnOff: 'border-white/20 text-zinc-300 hover:text-white',
  highlightEntry: 'border border-amber-400/30 bg-amber-500/10 hover:border-amber-300',
  highlightEntryText: 'text-amber-100',
  clearHighlights: 'border border-white/10 text-zinc-500 hover:text-white',
  changeCard: 'border border-amber-500/20 bg-amber-500/5 rounded-xl',
  changeSection: 'text-zinc-300',
  changeDate: 'text-zinc-500',
  changeRationale: 'text-zinc-400',
  changeProposedLabel: 'text-zinc-500',
  changeProposedText: 'text-zinc-300',
  jumpBtn: 'border border-zinc-600 hover:border-zinc-500 text-zinc-300 hover:text-white rounded-lg',
  acceptBtn: 'bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg',
  rejectBtn: 'border border-zinc-600 hover:border-zinc-500 text-zinc-200 rounded-lg',
  statusBadge: {
    active: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10',
    draft: 'text-zinc-400 border-zinc-700 bg-zinc-900',
    archived: 'text-zinc-500 border-zinc-800 bg-zinc-950',
  } as Record<string, string>,
  versionBadge: 'text-zinc-400 bg-zinc-900 border-zinc-700',
  publishBtn: 'bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl',
  archiveBtn: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100 rounded-xl',
  distributeBtn: 'bg-sky-600 hover:bg-sky-700 text-white rounded-xl',
  saveBtn: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  markReviewedBtn: 'text-zinc-500 hover:text-emerald-400',
  errorBg: 'border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl',
  errorBack: 'text-zinc-400 hover:text-white',
  notFoundBg: 'border border-white/10 bg-zinc-900/40 text-zinc-300 rounded-xl',
} as const;

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
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

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

  const handleMarkReviewed = async (sectionId: string) => {
    if (!id) return;
    try {
      await handbooks.markSectionReviewed(id, sectionId);
      await loadData();
    } catch (error) {
      console.error('Failed to mark section as reviewed:', error);
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
      <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="flex items-center justify-center min-h-[50vh]">
          <div className={`text-xs ${t.textFaint} uppercase tracking-wider animate-pulse`}>Loading handbook...</div>
        </div>
      </div>
    );
  }
  if (loadError) {
    return (
      <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="max-w-5xl mx-auto space-y-4 py-8">
          <div className={`${t.errorBg} p-4 text-sm`}>
            {loadError}
          </div>
          <button
            onClick={() => navigate('/app/matcha/handbook')}
            className={`text-xs ${t.errorBack} uppercase tracking-wider font-bold`}
          >
            Back to Handbooks
          </button>
        </div>
      </div>
    );
  }
  if (!handbook) {
    return (
      <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
        <div className="max-w-5xl mx-auto space-y-4 py-8">
          <div className={`${t.notFoundBg} p-4 text-sm`}>
            Handbook not found.
          </div>
          <button
            onClick={() => navigate('/app/matcha/handbook')}
            className={`text-xs ${t.errorBack} uppercase tracking-wider font-bold`}
          >
            Back to Handbooks
          </button>
        </div>
      </div>
    );
  }

  const toggleSidebarPanel = (key: string) =>
    setSidebarCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className={`-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`}>
    <div className="max-w-5xl mx-auto space-y-8">
      <div className="flex items-start justify-between mb-12 pb-8">
        <div className="space-y-3">
          <button
            onClick={() => navigate('/app/matcha/handbook')}
            className={`text-[10px] ${t.btnGhost} transition-colors uppercase tracking-wider flex items-center gap-1 font-bold`}
          >
            <ChevronLeft size={12} /> Back to Handbooks
          </button>
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-[10px] ${t.textMuted} font-mono tracking-wide uppercase`}>Handbook</span>
              <span className={`text-[10px] uppercase tracking-wide font-medium ${t.versionBadge} px-1.5 py-0.5 rounded-lg border`}>
                v{handbook.active_version}
              </span>
              <span className={`text-[10px] uppercase tracking-wide font-medium px-1.5 py-0.5 rounded-lg border ${
                t.statusBadge[handbook.status] || t.statusBadge['draft']
              }`}>
                {handbook.status}
              </span>
            </div>
            <h1 className={`text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>{handbook.title}</h1>
            <p className={`text-xs ${t.textMuted} uppercase tracking-wider font-mono mt-2`}>
              {handbook.mode === 'multi_state' ? 'Multi-State' : 'Single-State'} • {(handbook.scopes || []).map((scope) => scope.state).join(', ')}
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => navigate(`/app/matcha/handbook/${handbook.id}/edit`)}
            className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-3 py-2 transition-colors ${t.btnSecondary}`}
          >
            <Pencil size={12} />
            Edit Setup
          </button>
          <button
            onClick={handleDownload}
            className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-3 py-2 transition-colors ${t.btnSecondary}`}
          >
            <Download size={12} />
            PDF
          </button>
          {handbook.status !== 'archived' && (
            <button
              onClick={handleRunFreshnessCheck}
              disabled={freshnessLoading}
              className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-3 py-2 transition-colors disabled:opacity-50 ${t.btnSecondary}`}
            >
              <RefreshCw size={12} className={freshnessLoading ? 'animate-spin' : ''} />
              {freshnessLoading ? 'Checking...' : 'Check Updates'}
            </button>
          )}
          {handbook.status !== 'active' && (
            <button
              onClick={handlePublish}
              className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-4 py-2 transition-colors ${t.publishBtn}`}
            >
              <CheckCircle size={12} />
              Publish
            </button>
          )}
          {handbook.status !== 'archived' && (
            <button
              onClick={handleArchive}
              className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-3 py-2 transition-colors ${t.archiveBtn}`}
            >
              <Archive size={12} />
              Archive
            </button>
          )}
          {handbook.status === 'active' && (
            <button
              onClick={handleDistribute}
              disabled={distributionLoading}
              className={`flex items-center gap-1.5 text-[10px] uppercase tracking-wider font-bold px-4 py-2 transition-colors disabled:opacity-50 ${t.distributeBtn}`}
            >
              <Send size={12} />
              {distributionLoading ? 'Sending...' : 'Send E-Sign'}
            </button>
          )}
        </div>
      </div>

      {/* Info panels */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Highlighted Sections */}
        <div className={t.panelBg}>
          <button
            type="button"
            onClick={() => toggleSidebarPanel('highlights')}
            className={`w-full flex items-center justify-between px-3 py-2.5 ${t.panelHover} transition-colors rounded-2xl`}
          >
            <span className={`text-[9px] uppercase tracking-widest ${t.panelHeader} flex items-center gap-1.5`}>
              <Star size={9} className={highlightedSectionEntries.length ? 'text-amber-300 fill-current' : ''} />
              Highlights
              {highlightedSectionEntries.length > 0 && (
                <span className="bg-amber-500/20 text-amber-300 px-1 rounded text-[9px]">{highlightedSectionEntries.length}</span>
              )}
            </span>
            <ChevronDown size={10} className={`${t.panelChevron} transition-transform ${sidebarCollapsed['highlights'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['highlights'] && (
            <div className={`px-2 pb-2 space-y-1 border-t ${t.panelBorder}`}>
              {highlightedSectionEntries.length === 0 ? (
                <p className={`text-[10px] ${t.textFaint} px-1 py-2`}>None yet. Highlight sections from the editor.</p>
              ) : (
                <>
                  {highlightedSectionEntries.map((entry) => (
                    <button
                      key={entry.tabId}
                      type="button"
                      onClick={() => setActiveSectionTabId(entry.tabId)}
                      className={`w-full text-left px-2 py-1.5 ${t.highlightEntry} rounded-lg transition-colors`}
                    >
                      <span className={`text-[10px] font-mono ${t.highlightEntryText} truncate block`}>{entry.index + 1}. {entry.section.title}</span>
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setHighlightedSectionTabIds([])}
                    className={`w-full px-2 py-1 ${t.clearHighlights} text-[9px] uppercase tracking-wider transition-colors rounded-lg`}
                  >
                    Clear
                  </button>
                </>
              )}
            </div>
          )}
        </div>

        {/* Freshness Check */}
        <div className={t.panelBg}>
          <button
            type="button"
            onClick={() => toggleSidebarPanel('freshness')}
            className={`w-full flex items-center justify-between px-3 py-2.5 ${t.panelHover} transition-colors rounded-2xl`}
          >
            <span className={`text-[9px] uppercase tracking-widest ${t.panelHeader} flex items-center gap-1.5`}>
              <RefreshCw size={9} className={freshnessCheck?.is_outdated ? 'text-amber-300' : ''} />
              Freshness
            </span>
            <ChevronDown size={10} className={`${t.panelChevron} transition-transform ${sidebarCollapsed['freshness'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['freshness'] && (
            <div className={`px-3 pb-3 space-y-1.5 border-t ${t.panelBorder} pt-2`}>
              {!freshnessCheck ? (
                <p className={`text-[10px] ${t.textFaint}`}>No checks run yet.</p>
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
                  <div className={`text-[10px] ${t.panelTextMuted}`}>{new Date(freshnessCheck.checked_at).toLocaleDateString()}</div>
                  <div className={`text-[10px] ${t.textFaint}`}>{freshnessCheck.impacted_sections} impacted</div>
                  <div className={`text-[10px] ${t.textFaint}`}>{freshnessCheck.new_change_requests_count} new requests</div>
                  {freshnessCheck.findings
                    .filter(f => f.finding_type === 'review_recommended')
                    .map((f, i) => (
                      <div key={i} className="flex items-center gap-1.5 mt-1">
                        <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                        <span className="text-[10px] text-amber-300 truncate">{f.summary}</span>
                      </div>
                    ))
                  }
                </>
              )}
            </div>
          )}
        </div>

        {/* Employer Profile */}
        <div className={t.panelBg}>
          <button
            type="button"
            onClick={() => toggleSidebarPanel('profile')}
            className={`w-full flex items-center justify-between px-3 py-2.5 ${t.panelHover} transition-colors rounded-2xl`}
          >
            <span className={`text-[9px] uppercase tracking-widest ${t.panelHeader}`}>Employer</span>
            <ChevronDown size={10} className={`${t.panelChevron} transition-transform ${sidebarCollapsed['profile'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['profile'] && (
            <div className={`px-3 pb-3 space-y-1 border-t ${t.panelBorder} pt-2`}>
              <div className={`text-[11px] ${t.panelText} font-medium`}>{handbook.profile.legal_name}</div>
              <div className={`text-[10px] ${t.panelTextMuted}`}>DBA: {handbook.profile.dba || 'N/A'}</div>
              <div className={`text-[10px] ${t.panelTextMuted}`}>CEO: {handbook.profile.ceo_or_president}</div>
              <div className={`text-[10px] ${t.panelTextMuted}`}>Headcount: {handbook.profile.headcount ?? 'N/A'}</div>
            </div>
          )}
        </div>

        {/* Acknowledgements */}
        <div className={t.panelBg}>
          <button
            type="button"
            onClick={() => toggleSidebarPanel('acks')}
            className={`w-full flex items-center justify-between px-3 py-2.5 ${t.panelHover} transition-colors rounded-2xl`}
          >
            <span className={`text-[9px] uppercase tracking-widest ${t.panelHeader}`}>Acknowledgements</span>
            <ChevronDown size={10} className={`${t.panelChevron} transition-transform ${sidebarCollapsed['acks'] ? '-rotate-90' : ''}`} />
          </button>
          {!sidebarCollapsed['acks'] && (
            <div className={`px-3 pb-3 space-y-1 border-t ${t.panelBorder} pt-2`}>
              <div className={`text-[10px] ${t.textFaint}`}>Assigned: {ackSummary?.assigned_count ?? 0}</div>
              <div className="text-[10px] text-emerald-400">Signed: {ackSummary?.signed_count ?? 0}</div>
              <div className="text-[10px] text-amber-400">Pending: {ackSummary?.pending_count ?? 0}</div>
              <div className={`text-[10px] ${t.panelTextMuted}`}>Expired: {ackSummary?.expired_count ?? 0}</div>
            </div>
          )}
        </div>
      </div>

      <div className="space-y-8">
          <div className={`${t.editorBg} p-5`}>
            <div className={`flex items-center justify-between border-b ${t.editorBorder} pb-3 mb-4`}>
              <h2 className={t.label}>Handbook Sections</h2>
              <button
                onClick={handleSaveSections}
                disabled={saving}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-[10px] uppercase tracking-wider font-bold disabled:opacity-50 ${t.saveBtn}`}
              >
                <Save size={12} />
                {saving ? 'Saving...' : 'Save Sections'}
              </button>
            </div>
            {!sections.length ? (
              <p className={`text-sm ${t.textMuted}`}>No sections found for this handbook version.</p>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)] gap-4">
                <div className={`border ${t.sidebarBorder} ${t.sidebarBg} max-h-[560px] overflow-y-auto rounded-xl`}>
                  <div className="p-2 space-y-2">
                    <div className="space-y-2">
                      <input
                        type="text"
                        value={sectionSearch}
                        onChange={(e) => setSectionSearch(e.target.value)}
                        placeholder="Search sections..."
                        className={`w-full px-2.5 py-2 ${t.sidebarInput} text-[11px] rounded-lg`}
                      />
                      <p className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                        Showing {filteredSectionEntries.length} of {sections.length}
                      </p>
                    </div>

                    {groupedSectionEntries.length === 0 ? (
                      <div className={`px-2 py-4 text-[11px] ${t.textMuted} border ${t.sidebarBorder} rounded-lg`}>
                        No matching sections.
                      </div>
                    ) : (
                      groupedSectionEntries.map((group) => (
                        <div key={group.sectionType} className="space-y-1.5">
                          <p className={`px-1 text-[9px] uppercase tracking-[0.18em] ${t.textMuted}`}>
                            {group.label}
                          </p>
                          {group.entries.map(({ section, index, tabId, isDirty, isHighlighted }) => {
                            const selected = tabId === activeSectionTabId;
                            return (
                              <button
                                key={tabId}
                                type="button"
                                onClick={() => setActiveSectionTabId(tabId)}
                                className={`w-full text-left px-2.5 py-2 border transition-colors rounded-lg ${
                                  selected ? t.sidebarSelected : t.sidebarUnselected
                                }`}
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-[10px] uppercase tracking-wider font-mono truncate">
                                    {index + 1}. {section.title}
                                  </span>
                                  <div className="flex items-center gap-1">
                                    {isHighlighted && (
                                      <Star size={10} className={selected ? `${t.sidebarSelectedSub} fill-current` : 'text-amber-300 fill-current'} />
                                    )}
                                    {isDirty && (
                                      <span className={`text-[9px] uppercase tracking-wider ${selected ? t.sidebarSelectedSub : 'text-amber-400'}`}>
                                        edited
                                      </span>
                                    )}
                                  </div>
                                </div>
                                <div className={`text-[10px] uppercase tracking-wider mt-1 ${selected ? t.sidebarSelectedSub : t.sidebarUnselectedSub}`}>
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
                            <h3 className={`text-sm ${t.editorTitle}`}>{activeSection.title}</h3>
                            <p className={`text-[10px] ${t.editorSub} uppercase tracking-wider mt-1`}>
                              Section {activeSectionIndex + 1} of {sections.length} • {activeSection.section_type}
                            </p>
                            <p className={`text-[10px] ${t.editorKey} font-mono mt-1`}>{activeSection.section_key}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            {(activeSection.section_type === 'custom' || activeSection.section_type === 'uploaded') && activeSection.id && (
                              <button
                                onClick={() => handleMarkReviewed(activeSection.id!)}
                                className={`text-[9px] ${t.markReviewedBtn} transition-colors uppercase tracking-wider`}
                              >
                                Mark Reviewed
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => toggleSectionHighlight(getSectionTabId(activeSection, activeSectionIndex))}
                              className={`px-2 py-1 border text-[10px] uppercase tracking-wider inline-flex items-center gap-1 rounded-lg ${
                                activeSectionIsHighlighted ? t.highlightBtn : t.highlightBtnOff
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
                              className={`px-2 py-1 ${t.navBtn} text-[10px] uppercase tracking-wider disabled:opacity-40 rounded-lg`}
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
                              className={`px-2 py-1 ${t.navBtn} text-[10px] uppercase tracking-wider disabled:opacity-40 rounded-lg`}
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
                          className={`w-full min-h-[420px] px-3 py-3 ${t.textarea} text-sm`}
                        />
                      </div>
                      <div className="flex-shrink-0 w-8">
                        <div className="flex flex-col gap-0.5">
                          {notebookEdgeTabs.map((tab) => (
                            <div key={tab.tabId} className="relative group">
                              <button
                                type="button"
                                onClick={() => setActiveSectionTabId(tab.tabId)}
                                className={`h-[80px] w-8 border flex items-center justify-center transition-colors rounded-sm ${
                                  tab.isActive ? t.tabActive
                                    : tab.isHighlighted ? t.tabHighlighted
                                    : t.tabDefault
                                }`}
                                style={{ writingMode: 'vertical-rl' }}
                              >
                                <span className="text-[8px] uppercase tracking-widest truncate">
                                  {tab.index + 1}. {tab.title}
                                </span>
                                {tab.isDirty && <span className={tab.isActive ? (isLight ? 'text-zinc-300' : 'text-black/60') : 'text-amber-400'}> •</span>}
                              </button>
                              <div className="absolute right-full top-1/2 -translate-y-1/2 pr-1.5 hidden group-hover:block z-50 pointer-events-none">
                                <div className={`px-2.5 py-1.5 text-[10px] uppercase tracking-widest whitespace-nowrap border rounded-lg ${
                                  tab.isActive ? t.tabActive
                                    : tab.isHighlighted ? t.tabHoverHighlighted
                                    : t.tabHoverLabel
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

          <div className={`${t.editorBg} p-5`}>
            <div className={`flex items-center gap-2 border-b ${t.editorBorder} pb-3 mb-4`}>
              <AlertTriangle size={14} className="text-amber-400" />
              <h2 className={t.label}>Pending Legal Changes</h2>
            </div>
            {pendingChanges.length === 0 ? (
              <p className={`text-sm ${t.textMuted}`}>No pending handbook language changes.</p>
            ) : (
              <div className="space-y-4">
                    {pendingChanges.map((change) => (
                      <div key={change.id} className={`${t.changeCard} p-4 space-y-3`}>
                    <div className="flex items-center justify-between">
                      <p className={`text-xs ${t.changeSection} uppercase tracking-wider`}>
                        Section: {change.section_key || 'general'}
                      </p>
                      <p className={`text-[10px] ${t.changeDate}`}>{new Date(change.created_at).toLocaleDateString()}</p>
                    </div>
                    {change.rationale && <p className={`text-xs ${t.changeRationale}`}>{change.rationale}</p>}
                    <div>
                      <p className={`text-[10px] uppercase tracking-wider ${t.changeProposedLabel} mb-1`}>Proposed Content</p>
                      <div className={`text-xs ${t.changeProposedText} whitespace-pre-wrap font-serif leading-[1.5]`}>{change.proposed_content}</div>
                        </div>
                        <div className="flex justify-end">
                          <button
                            type="button"
                            onClick={() => jumpToSection(change.section_key)}
                            disabled={!change.section_key || !sectionKeyToIndex.has(change.section_key)}
                            className={`px-2.5 py-1 ${t.jumpBtn} text-[10px] uppercase tracking-wider disabled:opacity-40`}
                          >
                            Jump to section
                          </button>
                        </div>
                        <div className="flex gap-2">
                      <button
                        onClick={() => handleResolveChange(change.id, 'accept')}
                        className={`flex items-center gap-1 px-3 py-1.5 ${t.acceptBtn} text-[10px] uppercase tracking-wider`}
                      >
                        <Check size={12} />
                        Accept
                      </button>
                      <button
                        onClick={() => handleResolveChange(change.id, 'reject')}
                        className={`flex items-center gap-1 px-3 py-1.5 ${t.rejectBtn} text-[10px] uppercase tracking-wider`}
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
    </div>
  );
}

export default HandbookDetailPage;
