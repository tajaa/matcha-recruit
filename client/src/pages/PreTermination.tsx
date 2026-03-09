import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  FileWarning,
  Gavel,
  Plus,
  RefreshCw,
  Save,
  Scale,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from 'lucide-react';
import { preTermination } from '../api/client';
import type {
  ProgressiveDiscipline,
  DisciplineCreateRequest,
  DisciplineUpdateRequest,
  DisciplineType,
  DisciplineStatus,
  AgencyCharge,
  AgencyChargeCreateRequest,
  AgencyChargeUpdateRequest,
  ChargeType,
  ChargeStatus,
  PostTermClaim,
  PostTermClaimCreateRequest,
  PostTermClaimUpdateRequest,
  ClaimStatus,
} from '../types';
import { useIsLightMode } from '../hooks/useIsLightMode';
import { FeatureGuideTrigger } from '../features/feature-guides';

// ─── theme ────────────────────────────────────────────────────────────────────

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  rowHover: 'hover:bg-stone-50',
  label: 'text-[10px] text-stone-500 uppercase tracking-wider',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  select: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  btnDanger: 'border border-red-300 text-red-700 hover:bg-red-50',
  modalBg: 'bg-stone-100 rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-400 hover:text-stone-600',
  tabBorder: 'border-b border-stone-200',
  badgeGreen: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  badgeYellow: 'bg-amber-100 text-amber-800 border-amber-200',
  badgeRed: 'bg-red-100 text-red-800 border-red-200',
  badgeBlue: 'bg-blue-100 text-blue-800 border-blue-200',
  badgeGray: 'bg-stone-200 text-stone-600 border-stone-300',
  badgePurple: 'bg-violet-100 text-violet-800 border-violet-200',
};

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  divide: 'divide-white/10',
  rowHover: 'hover:bg-white/5',
  label: 'text-[10px] text-zinc-500 uppercase tracking-wider',
  input: 'bg-zinc-800 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:border-white/20',
  select: 'bg-zinc-800 border border-white/10 rounded-xl text-zinc-100 focus:border-white/20',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  btnDanger: 'border border-red-500/30 text-red-300 hover:bg-red-500/10',
  modalBg: 'bg-zinc-900 border border-white/10 rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  tabActive: 'border-zinc-100 text-zinc-100',
  tabInactive: 'border-transparent text-zinc-600 hover:text-zinc-400',
  tabBorder: 'border-b border-white/10',
  badgeGreen: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  badgeYellow: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  badgeRed: 'bg-red-500/10 text-red-400 border-red-500/20',
  badgeBlue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  badgeGray: 'bg-zinc-600/20 text-zinc-300 border-zinc-600/30',
  badgePurple: 'bg-violet-500/10 text-violet-400 border-violet-500/20',
};

// ─── constants ────────────────────────────────────────────────────────────────

type TabKey = 'discipline' | 'charges' | 'claims';

const TABS: { key: TabKey; label: string; icon: typeof ShieldAlert }[] = [
  { key: 'discipline', label: 'Progressive Discipline', icon: FileWarning },
  { key: 'charges', label: 'Agency Charges', icon: Gavel },
  { key: 'claims', label: 'Post-Termination Claims', icon: Scale },
];

const DISCIPLINE_TYPES: DisciplineType[] = ['verbal_warning', 'written_warning', 'pip', 'final_warning', 'suspension'];
const DISCIPLINE_STATUSES: DisciplineStatus[] = ['active', 'completed', 'expired', 'escalated'];
const CHARGE_TYPES: ChargeType[] = ['eeoc', 'nlrb', 'osha', 'state_agency', 'other'];
const CHARGE_STATUSES: ChargeStatus[] = ['filed', 'investigating', 'mediation', 'resolved', 'dismissed', 'litigated'];
const CLAIM_STATUSES: ClaimStatus[] = ['filed', 'investigating', 'mediation', 'settled', 'dismissed', 'litigated', 'judgment'];

// ─── helpers ──────────────────────────────────────────────────────────────────

function formatLabel(value: string): string {
  return value
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function statusBadge(status: string, t: typeof LT): string {
  switch (status) {
    case 'completed':
    case 'resolved':
    case 'settled':
    case 'dismissed':
      return t.badgeGreen;
    case 'active':
    case 'filed':
    case 'open':
      return t.badgeBlue;
    case 'investigating':
    case 'mediation':
    case 'pip':
      return t.badgeYellow;
    case 'escalated':
    case 'litigated':
    case 'judgment':
    case 'final_warning':
    case 'suspension':
      return t.badgeRed;
    case 'expired':
      return t.badgeGray;
    default:
      return t.badgePurple;
  }
}

function typeBadge(type: string, t: typeof LT): string {
  switch (type) {
    case 'verbal_warning':
      return t.badgeBlue;
    case 'written_warning':
      return t.badgeYellow;
    case 'pip':
      return t.badgePurple;
    case 'final_warning':
    case 'suspension':
      return t.badgeRed;
    case 'eeoc':
    case 'nlrb':
      return t.badgeRed;
    case 'osha':
      return t.badgeYellow;
    default:
      return t.badgeGray;
  }
}

function truncate(text: string | null, max = 60): string {
  if (!text) return '--';
  return text.length > max ? text.slice(0, max) + '...' : text;
}

function formatCurrency(amount: number | null): string {
  if (amount === null || amount === undefined) return '--';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

// ─── component ────────────────────────────────────────────────────────────────

export default function PreTermination() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [activeTab, setActiveTab] = useState<TabKey>('discipline');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // ── Discipline state ──────────────────────────────────────────────────────
  const [disciplineSearch, setDisciplineSearch] = useState('');
  const [disciplineRecords, setDisciplineRecords] = useState<ProgressiveDiscipline[]>([]);
  const [showDisciplineCreate, setShowDisciplineCreate] = useState(false);
  const [editingDiscipline, setEditingDiscipline] = useState<ProgressiveDiscipline | null>(null);
  const [disciplineForm, setDisciplineForm] = useState<DisciplineCreateRequest>({
    employee_id: '',
    discipline_type: 'verbal_warning',
    issued_date: todayISO(),
    description: '',
    expected_improvement: '',
    review_date: '',
  });
  const [disciplineEditForm, setDisciplineEditForm] = useState<DisciplineUpdateRequest>({});

  // ── Charges state ─────────────────────────────────────────────────────────
  const [charges, setCharges] = useState<AgencyCharge[]>([]);
  const [showChargeCreate, setShowChargeCreate] = useState(false);
  const [editingCharge, setEditingCharge] = useState<AgencyCharge | null>(null);
  const [chargeForm, setChargeForm] = useState<AgencyChargeCreateRequest>({
    employee_id: '',
    charge_type: 'eeoc',
    filing_date: todayISO(),
    charge_number: '',
    agency_name: '',
    description: '',
  });
  const [chargeEditForm, setChargeEditForm] = useState<AgencyChargeUpdateRequest>({});

  // ── Claims state ──────────────────────────────────────────────────────────
  const [claims, setClaims] = useState<PostTermClaim[]>([]);
  const [showClaimCreate, setShowClaimCreate] = useState(false);
  const [editingClaim, setEditingClaim] = useState<PostTermClaim | null>(null);
  const [claimForm, setClaimForm] = useState<PostTermClaimCreateRequest>({
    employee_id: '',
    claim_type: '',
    filed_date: todayISO(),
    description: '',
  });
  const [claimEditForm, setClaimEditForm] = useState<PostTermClaimUpdateRequest>({});

  // ── auto-clear success ────────────────────────────────────────────────────
  useEffect(() => {
    if (!successMessage) return;
    const timer = setTimeout(() => setSuccessMessage(null), 4000);
    return () => clearTimeout(timer);
  }, [successMessage]);

  // ── data loading ──────────────────────────────────────────────────────────

  const loadDiscipline = useCallback(async () => {
    const trimmed = disciplineSearch.trim();
    if (!trimmed) {
      setDisciplineRecords([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await preTermination.getEmployeeDiscipline(trimmed);
      setDisciplineRecords(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load discipline records');
      setDisciplineRecords([]);
    } finally {
      setLoading(false);
    }
  }, [disciplineSearch]);

  const [chargeSearch, setChargeSearch] = useState('');

  const loadCharges = useCallback(async () => {
    const trimmed = chargeSearch.trim();
    if (!trimmed) {
      setCharges([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await preTermination.getEmployeeCharges(trimmed);
      setCharges(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agency charges');
      setCharges([]);
    } finally {
      setLoading(false);
    }
  }, [chargeSearch]);

  const loadClaims = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await preTermination.getCompanyClaims();
      setClaims(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load post-termination claims');
      setClaims([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'claims') {
      void loadClaims();
    }
  }, [activeTab, loadClaims]);

  // ── discipline CRUD ───────────────────────────────────────────────────────

  const handleCreateDiscipline = async () => {
    if (!disciplineForm.employee_id.trim() || !disciplineForm.issued_date) return;
    setSaving(true);
    setError(null);
    try {
      await preTermination.createDiscipline({
        ...disciplineForm,
        description: disciplineForm.description?.trim() || undefined,
        expected_improvement: disciplineForm.expected_improvement?.trim() || undefined,
        review_date: disciplineForm.review_date?.trim() || undefined,
      });
      setShowDisciplineCreate(false);
      setDisciplineForm({ employee_id: '', discipline_type: 'verbal_warning', issued_date: todayISO(), description: '', expected_improvement: '', review_date: '' });
      setSuccessMessage('Discipline record created.');
      if (disciplineSearch.trim()) await loadDiscipline();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create discipline record');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateDiscipline = async () => {
    if (!editingDiscipline) return;
    setSaving(true);
    setError(null);
    try {
      const body: DisciplineUpdateRequest = {
        status: disciplineEditForm.status,
        outcome_notes: disciplineEditForm.outcome_notes?.trim() || undefined,
        review_date: disciplineEditForm.review_date?.trim() || undefined,
        description: disciplineEditForm.description?.trim() || undefined,
      };
      await preTermination.updateDiscipline(editingDiscipline.id, body);
      setEditingDiscipline(null);
      setSuccessMessage('Discipline record updated.');
      if (disciplineSearch.trim()) await loadDiscipline();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update discipline record');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteDiscipline = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this discipline record?')) return;
    setSaving(true);
    setError(null);
    try {
      await preTermination.deleteDiscipline(id);
      setSuccessMessage('Discipline record deleted.');
      if (disciplineSearch.trim()) await loadDiscipline();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete discipline record');
    } finally {
      setSaving(false);
    }
  };

  // ── charges CRUD ──────────────────────────────────────────────────────────

  const handleCreateCharge = async () => {
    if (!chargeForm.employee_id.trim() || !chargeForm.filing_date) return;
    setSaving(true);
    setError(null);
    try {
      await preTermination.createCharge({
        ...chargeForm,
        charge_number: chargeForm.charge_number?.trim() || undefined,
        agency_name: chargeForm.agency_name?.trim() || undefined,
        description: chargeForm.description?.trim() || undefined,
      });
      setShowChargeCreate(false);
      setChargeForm({ employee_id: '', charge_type: 'eeoc', filing_date: todayISO(), charge_number: '', agency_name: '', description: '' });
      setSuccessMessage('Agency charge created.');
      if (chargeSearch.trim()) await loadCharges();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create agency charge');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateCharge = async () => {
    if (!editingCharge) return;
    setSaving(true);
    setError(null);
    try {
      const body: AgencyChargeUpdateRequest = {
        status: chargeEditForm.status,
        resolution_amount: chargeEditForm.resolution_amount ?? undefined,
        resolution_date: chargeEditForm.resolution_date?.trim() || undefined,
        resolution_notes: chargeEditForm.resolution_notes?.trim() || undefined,
        description: chargeEditForm.description?.trim() || undefined,
      };
      await preTermination.updateCharge(editingCharge.id, body);
      setEditingCharge(null);
      setSuccessMessage('Agency charge updated.');
      if (chargeSearch.trim()) await loadCharges();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update agency charge');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteCharge = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this agency charge?')) return;
    setSaving(true);
    setError(null);
    try {
      await preTermination.deleteCharge(id);
      setSuccessMessage('Agency charge deleted.');
      if (chargeSearch.trim()) await loadCharges();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agency charge');
    } finally {
      setSaving(false);
    }
  };

  // ── claims CRUD ───────────────────────────────────────────────────────────

  const handleCreateClaim = async () => {
    if (!claimForm.employee_id.trim() || !claimForm.claim_type.trim() || !claimForm.filed_date) return;
    setSaving(true);
    setError(null);
    try {
      await preTermination.createClaim({
        ...claimForm,
        description: claimForm.description?.trim() || undefined,
      });
      setShowClaimCreate(false);
      setClaimForm({ employee_id: '', claim_type: '', filed_date: todayISO(), description: '' });
      setSuccessMessage('Post-termination claim created.');
      await loadClaims();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create claim');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateClaim = async () => {
    if (!editingClaim) return;
    setSaving(true);
    setError(null);
    try {
      const body: PostTermClaimUpdateRequest = {
        status: claimEditForm.status,
        resolution_amount: claimEditForm.resolution_amount ?? undefined,
        resolution_date: claimEditForm.resolution_date?.trim() || undefined,
        description: claimEditForm.description?.trim() || undefined,
      };
      await preTermination.updateClaim(editingClaim.id, body);
      setEditingClaim(null);
      setSuccessMessage('Claim updated.');
      await loadClaims();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update claim');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteClaim = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this claim?')) return;
    setSaving(true);
    setError(null);
    try {
      await preTermination.deleteClaim(id);
      setSuccessMessage('Claim deleted.');
      await loadClaims();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete claim');
    } finally {
      setSaving(false);
    }
  };

  // ── render helpers ────────────────────────────────────────────────────────

  const renderBadge = (value: string, style: string) => (
    <span className={`text-[9px] px-2 py-0.5 uppercase tracking-widest border rounded-full ${style}`}>
      {formatLabel(value)}
    </span>
  );

  // ── loading state ─────────────────────────────────────────────────────────

  const renderLoading = () => (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className={`text-xs uppercase tracking-wider animate-pulse ${t.textMuted}`}>Loading...</div>
    </div>
  );

  // ── empty state ───────────────────────────────────────────────────────────

  const renderEmpty = (message: string) => (
    <div className={`px-4 py-10 text-center text-sm ${t.textMuted}`}>{message}</div>
  );

  // ─── DISCIPLINE TAB ─────────────────────────────────────────────────────────

  const renderDisciplineTab = () => (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className={`block mb-1 ${t.label}`}>Employee ID</label>
          <div className="flex gap-2">
            <input
              value={disciplineSearch}
              onChange={(e) => setDisciplineSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && loadDiscipline()}
              placeholder="Enter employee ID to search..."
              className={`flex-1 px-3 py-2 text-sm ${t.input}`}
            />
            <button
              onClick={loadDiscipline}
              disabled={!disciplineSearch.trim() || loading}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50`}
            >
              <Search size={14} /> Search
            </button>
          </div>
        </div>
        <button
          data-tour="pretermination-new-btn"
          onClick={() => {
            setShowDisciplineCreate(true);
            setError(null);
          }}
          className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary}`}
        >
          <Plus size={14} /> New Record
        </button>
      </div>

      {loading ? renderLoading() : disciplineRecords.length === 0 ? (
        renderEmpty(disciplineSearch.trim() ? 'No discipline records found for this employee.' : 'Enter an employee ID to search for discipline records.')
      ) : (
        <div data-tour="pretermination-list" className={`${t.card} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`${t.tabBorder}`}>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Employee ID</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Type</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Issued Date</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Status</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Review Date</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Description</th>
                  <th className={`px-4 py-3 text-right ${t.label}`}>Actions</th>
                </tr>
              </thead>
              <tbody className={t.divide}>
                {disciplineRecords.map((rec) => (
                  <tr key={rec.id} className={`${t.rowHover} transition-colors`}>
                    <td className={`px-4 py-3 font-mono text-xs ${t.textMain}`}>{rec.employee_id.slice(0, 8)}...</td>
                    <td className="px-4 py-3">{renderBadge(rec.discipline_type, typeBadge(rec.discipline_type, t))}</td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>{rec.issued_date}</td>
                    <td className="px-4 py-3" data-tour="pretermination-status">{renderBadge(rec.status, statusBadge(rec.status, t))}</td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>{rec.review_date || '--'}</td>
                    <td className={`px-4 py-3 max-w-[200px] ${t.textMuted}`}>{truncate(rec.description)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => {
                            setEditingDiscipline(rec);
                            setDisciplineEditForm({
                              status: rec.status,
                              outcome_notes: rec.outcome_notes || '',
                              review_date: rec.review_date || '',
                              description: rec.description || '',
                            });
                          }}
                          className={`p-1.5 text-xs ${t.btnGhost}`}
                          title="Edit"
                        >
                          <Save size={14} />
                        </button>
                        <button
                          onClick={() => handleDeleteDiscipline(rec.id)}
                          disabled={saving}
                          className="p-1.5 text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  // ─── CHARGES TAB ────────────────────────────────────────────────────────────

  const renderChargesTab = () => (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className={`block mb-1 ${t.label}`}>Employee ID</label>
          <div className="flex gap-2">
            <input
              value={chargeSearch}
              onChange={(e) => setChargeSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && loadCharges()}
              placeholder="Enter employee ID to search..."
              className={`flex-1 px-3 py-2 text-sm ${t.input}`}
            />
            <button
              onClick={loadCharges}
              disabled={!chargeSearch.trim() || loading}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50`}
            >
              <Search size={14} /> Search
            </button>
          </div>
        </div>
        <button
          onClick={() => {
            setShowChargeCreate(true);
            setError(null);
          }}
          className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary}`}
        >
          <Plus size={14} /> New Charge
        </button>
      </div>

      {loading ? renderLoading() : charges.length === 0 ? (
        renderEmpty(chargeSearch.trim() ? 'No agency charges found for this employee.' : 'Enter an employee ID to search for agency charges.')
      ) : (
        <div className={`${t.card} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={t.tabBorder}>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Employee ID</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Charge Type</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Charge Number</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Filing Date</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Agency</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Status</th>
                  <th className={`px-4 py-3 text-right ${t.label}`}>Resolution Amt</th>
                  <th className={`px-4 py-3 text-right ${t.label}`}>Actions</th>
                </tr>
              </thead>
              <tbody className={t.divide}>
                {charges.map((charge) => (
                  <tr key={charge.id} className={`${t.rowHover} transition-colors`}>
                    <td className={`px-4 py-3 font-mono text-xs ${t.textMain}`}>{charge.employee_id.slice(0, 8)}...</td>
                    <td className="px-4 py-3">{renderBadge(charge.charge_type, typeBadge(charge.charge_type, t))}</td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>{charge.charge_number || '--'}</td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>{charge.filing_date}</td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>{charge.agency_name || '--'}</td>
                    <td className="px-4 py-3">{renderBadge(charge.status, statusBadge(charge.status, t))}</td>
                    <td className={`px-4 py-3 text-right font-mono ${t.textMain}`}>{formatCurrency(charge.resolution_amount)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => {
                            setEditingCharge(charge);
                            setChargeEditForm({
                              status: charge.status,
                              resolution_amount: charge.resolution_amount ?? undefined,
                              resolution_date: charge.resolution_date || '',
                              resolution_notes: charge.resolution_notes || '',
                              description: charge.description || '',
                            });
                          }}
                          className={`p-1.5 text-xs ${t.btnGhost}`}
                          title="Edit"
                        >
                          <Save size={14} />
                        </button>
                        <button
                          onClick={() => handleDeleteCharge(charge.id)}
                          disabled={saving}
                          className="p-1.5 text-xs text-red-400 hover:text-red-300 disabled:opacity-50"
                          title="Delete"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  // ─── CLAIMS TAB ─────────────────────────────────────────────────────────────

  const renderClaimsTab = () => (
    <div className="space-y-4">
      <div className="flex justify-end">
        <div className="flex items-center gap-2">
          <button
            onClick={loadClaims}
            disabled={loading}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnGhost}`}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button
            onClick={() => {
              setShowClaimCreate(true);
              setError(null);
            }}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary}`}
          >
            <Plus size={14} /> New Claim
          </button>
        </div>
      </div>

      {loading ? renderLoading() : claims.length === 0 ? (
        renderEmpty('No post-termination claims found.')
      ) : (
        <div className={`${t.card} overflow-hidden`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={t.tabBorder}>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Employee ID</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Claim Type</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Filed Date</th>
                  <th className={`px-4 py-3 text-left ${t.label}`}>Status</th>
                  <th className={`px-4 py-3 text-right ${t.label}`}>Resolution Amt</th>
                  <th className={`px-4 py-3 text-right ${t.label}`}>Actions</th>
                </tr>
              </thead>
              <tbody className={t.divide}>
                {claims.map((claim) => (
                  <tr key={claim.id} className={`${t.rowHover} transition-colors`}>
                    <td className={`px-4 py-3 font-mono text-xs ${t.textMain}`}>{claim.employee_id.slice(0, 8)}...</td>
                    <td className={`px-4 py-3 ${t.textMain}`}>{formatLabel(claim.claim_type)}</td>
                    <td className={`px-4 py-3 ${t.textMuted}`}>{claim.filed_date}</td>
                    <td className="px-4 py-3">{renderBadge(claim.status, statusBadge(claim.status, t))}</td>
                    <td className={`px-4 py-3 text-right font-mono ${t.textMain}`}>{formatCurrency(claim.resolution_amount)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => {
                          setEditingClaim(claim);
                          setClaimEditForm({
                            status: claim.status,
                            resolution_amount: claim.resolution_amount ?? undefined,
                            resolution_date: claim.resolution_date || '',
                            description: claim.description || '',
                          });
                        }}
                        className={`p-1.5 text-xs ${t.btnGhost}`}
                        title="Edit"
                      >
                        <Save size={14} />
                      </button>
                      <button
                        onClick={() => handleDeleteClaim(claim.id)}
                        className={`p-1.5 text-xs ${t.btnDanger}`}
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );

  // ─── MODALS ─────────────────────────────────────────────────────────────────

  const renderModal = (
    title: string,
    open: boolean,
    onClose: () => void,
    onSubmit: () => void,
    submitLabel: string,
    children: React.ReactNode,
  ) => {
    if (!open) return null;
    return (
      <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm p-4 flex items-center justify-center">
        <div className={`w-full max-w-lg ${t.modalBg}`}>
          <div className={`flex items-center justify-between p-5 ${t.modalHeader}`}>
            <h3 className={`text-lg font-semibold uppercase tracking-wider ${t.textMain}`}>{title}</h3>
            <button onClick={onClose} className={t.btnGhost}>
              <X size={18} />
            </button>
          </div>
          <div className="p-5 space-y-4">
            {children}
          </div>
          <div className={`p-5 ${t.modalFooter} flex justify-end gap-2`}>
            <button onClick={onClose} className={`px-3 py-2 text-xs uppercase tracking-wider ${t.btnGhost}`}>
              Cancel
            </button>
            <button
              onClick={onSubmit}
              disabled={saving}
              className={`px-3 py-2 text-xs uppercase tracking-wider ${t.btnPrimary} disabled:opacity-50`}
            >
              {saving ? 'Saving...' : submitLabel}
            </button>
          </div>
        </div>
      </div>
    );
  };

  // ─── MAIN RENDER ────────────────────────────────────────────────────────────

  return (
    <div className={`max-w-7xl mx-auto space-y-6 ${t.pageBg} min-h-screen p-6`}>
      {/* Header */}
      <div data-tour="pretermination-context" className={`flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 pb-6 ${t.tabBorder}`}>
        <div>
          <div className="flex items-center gap-3">
            <ShieldAlert size={28} className={t.textMain} />
            <h1 className={`text-4xl font-bold tracking-tighter uppercase ${t.textMain}`}>Pre-Termination</h1>
            <FeatureGuideTrigger guideId="pre-termination" />
          </div>
          <p className={`text-xs mt-2 font-mono tracking-wide uppercase ${t.textMuted}`}>
            Progressive discipline, agency charges, and post-termination claims
          </p>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="text-red-400" size={16} />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {successMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 flex items-center gap-3">
          <CheckCircle className="text-emerald-400" size={16} />
          <p className="text-sm text-emerald-300">{successMessage}</p>
        </div>
      )}

      {/* Tabs */}
      <div data-tour="pretermination-tabs" className={`flex gap-6 ${t.tabBorder}`}>
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => { setActiveTab(key); setError(null); }}
            className={`inline-flex items-center gap-2 pb-3 text-xs uppercase tracking-wider border-b-2 transition-colors ${
              activeTab === key ? t.tabActive : t.tabInactive
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'discipline' && renderDisciplineTab()}
      {activeTab === 'charges' && renderChargesTab()}
      {activeTab === 'claims' && renderClaimsTab()}

      {/* ── Create Discipline Modal ──────────────────────────────────────────── */}
      {renderModal(
        'Create Discipline Record',
        showDisciplineCreate,
        () => setShowDisciplineCreate(false),
        handleCreateDiscipline,
        'Create Record',
        <>
          <div>
            <label className={`block mb-1 ${t.label}`}>Employee ID</label>
            <input
              value={disciplineForm.employee_id}
              onChange={(e) => setDisciplineForm((p) => ({ ...p, employee_id: e.target.value }))}
              placeholder="Employee UUID"
              className={`w-full px-3 py-2 text-sm ${t.input}`}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block mb-1 ${t.label}`}>Discipline Type</label>
              <select
                value={disciplineForm.discipline_type}
                onChange={(e) => setDisciplineForm((p) => ({ ...p, discipline_type: e.target.value as DisciplineType }))}
                className={`w-full px-3 py-2 text-sm ${t.select}`}
              >
                {DISCIPLINE_TYPES.map((dt) => (
                  <option key={dt} value={dt}>{formatLabel(dt)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={`block mb-1 ${t.label}`}>Issued Date</label>
              <input
                type="date"
                value={disciplineForm.issued_date}
                onChange={(e) => setDisciplineForm((p) => ({ ...p, issued_date: e.target.value }))}
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Description</label>
            <textarea
              rows={3}
              value={disciplineForm.description || ''}
              onChange={(e) => setDisciplineForm((p) => ({ ...p, description: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Expected Improvement</label>
            <textarea
              rows={2}
              value={disciplineForm.expected_improvement || ''}
              onChange={(e) => setDisciplineForm((p) => ({ ...p, expected_improvement: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Review Date</label>
            <input
              type="date"
              value={disciplineForm.review_date || ''}
              onChange={(e) => setDisciplineForm((p) => ({ ...p, review_date: e.target.value }))}
              className={`w-full px-3 py-2 text-sm ${t.input}`}
            />
          </div>
        </>,
      )}

      {/* ── Edit Discipline Modal ────────────────────────────────────────────── */}
      {renderModal(
        'Edit Discipline Record',
        editingDiscipline !== null,
        () => setEditingDiscipline(null),
        handleUpdateDiscipline,
        'Update Record',
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block mb-1 ${t.label}`}>Status</label>
              <select
                value={disciplineEditForm.status || ''}
                onChange={(e) => setDisciplineEditForm((p) => ({ ...p, status: e.target.value as DisciplineStatus }))}
                className={`w-full px-3 py-2 text-sm ${t.select}`}
              >
                {DISCIPLINE_STATUSES.map((s) => (
                  <option key={s} value={s}>{formatLabel(s)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={`block mb-1 ${t.label}`}>Review Date</label>
              <input
                type="date"
                value={disciplineEditForm.review_date || ''}
                onChange={(e) => setDisciplineEditForm((p) => ({ ...p, review_date: e.target.value }))}
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Description</label>
            <textarea
              rows={3}
              value={disciplineEditForm.description || ''}
              onChange={(e) => setDisciplineEditForm((p) => ({ ...p, description: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Outcome Notes</label>
            <textarea
              rows={3}
              value={disciplineEditForm.outcome_notes || ''}
              onChange={(e) => setDisciplineEditForm((p) => ({ ...p, outcome_notes: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
        </>,
      )}

      {/* ── Create Charge Modal ──────────────────────────────────────────────── */}
      {renderModal(
        'Create Agency Charge',
        showChargeCreate,
        () => setShowChargeCreate(false),
        handleCreateCharge,
        'Create Charge',
        <>
          <div>
            <label className={`block mb-1 ${t.label}`}>Employee ID</label>
            <input
              value={chargeForm.employee_id}
              onChange={(e) => setChargeForm((p) => ({ ...p, employee_id: e.target.value }))}
              placeholder="Employee UUID"
              className={`w-full px-3 py-2 text-sm ${t.input}`}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block mb-1 ${t.label}`}>Charge Type</label>
              <select
                value={chargeForm.charge_type}
                onChange={(e) => setChargeForm((p) => ({ ...p, charge_type: e.target.value as ChargeType }))}
                className={`w-full px-3 py-2 text-sm ${t.select}`}
              >
                {CHARGE_TYPES.map((ct) => (
                  <option key={ct} value={ct}>{formatLabel(ct)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={`block mb-1 ${t.label}`}>Filing Date</label>
              <input
                type="date"
                value={chargeForm.filing_date}
                onChange={(e) => setChargeForm((p) => ({ ...p, filing_date: e.target.value }))}
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block mb-1 ${t.label}`}>Charge Number</label>
              <input
                value={chargeForm.charge_number || ''}
                onChange={(e) => setChargeForm((p) => ({ ...p, charge_number: e.target.value }))}
                placeholder="e.g. 123-2026-00456"
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
            <div>
              <label className={`block mb-1 ${t.label}`}>Agency Name</label>
              <input
                value={chargeForm.agency_name || ''}
                onChange={(e) => setChargeForm((p) => ({ ...p, agency_name: e.target.value }))}
                placeholder="e.g. EEOC - Dallas"
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Description</label>
            <textarea
              rows={3}
              value={chargeForm.description || ''}
              onChange={(e) => setChargeForm((p) => ({ ...p, description: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
        </>,
      )}

      {/* ── Edit Charge Modal ────────────────────────────────────────────────── */}
      {renderModal(
        'Edit Agency Charge',
        editingCharge !== null,
        () => setEditingCharge(null),
        handleUpdateCharge,
        'Update Charge',
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block mb-1 ${t.label}`}>Status</label>
              <select
                value={chargeEditForm.status || ''}
                onChange={(e) => setChargeEditForm((p) => ({ ...p, status: e.target.value as ChargeStatus }))}
                className={`w-full px-3 py-2 text-sm ${t.select}`}
              >
                {CHARGE_STATUSES.map((s) => (
                  <option key={s} value={s}>{formatLabel(s)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={`block mb-1 ${t.label}`}>Resolution Date</label>
              <input
                type="date"
                value={chargeEditForm.resolution_date || ''}
                onChange={(e) => setChargeEditForm((p) => ({ ...p, resolution_date: e.target.value }))}
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Resolution Amount ($)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={chargeEditForm.resolution_amount ?? ''}
              onChange={(e) => setChargeEditForm((p) => ({ ...p, resolution_amount: e.target.value ? parseFloat(e.target.value) : undefined }))}
              placeholder="0.00"
              className={`w-full px-3 py-2 text-sm ${t.input}`}
            />
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Resolution Notes</label>
            <textarea
              rows={3}
              value={chargeEditForm.resolution_notes || ''}
              onChange={(e) => setChargeEditForm((p) => ({ ...p, resolution_notes: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Description</label>
            <textarea
              rows={2}
              value={chargeEditForm.description || ''}
              onChange={(e) => setChargeEditForm((p) => ({ ...p, description: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
        </>,
      )}

      {/* ── Create Claim Modal ───────────────────────────────────────────────── */}
      {renderModal(
        'Create Post-Termination Claim',
        showClaimCreate,
        () => setShowClaimCreate(false),
        handleCreateClaim,
        'Create Claim',
        <>
          <div>
            <label className={`block mb-1 ${t.label}`}>Employee ID</label>
            <input
              value={claimForm.employee_id}
              onChange={(e) => setClaimForm((p) => ({ ...p, employee_id: e.target.value }))}
              placeholder="Employee UUID"
              className={`w-full px-3 py-2 text-sm ${t.input}`}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block mb-1 ${t.label}`}>Claim Type</label>
              <input
                value={claimForm.claim_type}
                onChange={(e) => setClaimForm((p) => ({ ...p, claim_type: e.target.value }))}
                placeholder="e.g. wrongful_termination"
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
            <div>
              <label className={`block mb-1 ${t.label}`}>Filed Date</label>
              <input
                type="date"
                value={claimForm.filed_date}
                onChange={(e) => setClaimForm((p) => ({ ...p, filed_date: e.target.value }))}
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Description</label>
            <textarea
              rows={3}
              value={claimForm.description || ''}
              onChange={(e) => setClaimForm((p) => ({ ...p, description: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
        </>,
      )}

      {/* ── Edit Claim Modal ─────────────────────────────────────────────────── */}
      {renderModal(
        'Edit Post-Termination Claim',
        editingClaim !== null,
        () => setEditingClaim(null),
        handleUpdateClaim,
        'Update Claim',
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={`block mb-1 ${t.label}`}>Status</label>
              <select
                value={claimEditForm.status || ''}
                onChange={(e) => setClaimEditForm((p) => ({ ...p, status: e.target.value as ClaimStatus }))}
                className={`w-full px-3 py-2 text-sm ${t.select}`}
              >
                {CLAIM_STATUSES.map((s) => (
                  <option key={s} value={s}>{formatLabel(s)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={`block mb-1 ${t.label}`}>Resolution Date</label>
              <input
                type="date"
                value={claimEditForm.resolution_date || ''}
                onChange={(e) => setClaimEditForm((p) => ({ ...p, resolution_date: e.target.value }))}
                className={`w-full px-3 py-2 text-sm ${t.input}`}
              />
            </div>
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Resolution Amount ($)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={claimEditForm.resolution_amount ?? ''}
              onChange={(e) => setClaimEditForm((p) => ({ ...p, resolution_amount: e.target.value ? parseFloat(e.target.value) : undefined }))}
              placeholder="0.00"
              className={`w-full px-3 py-2 text-sm ${t.input}`}
            />
          </div>
          <div>
            <label className={`block mb-1 ${t.label}`}>Description</label>
            <textarea
              rows={3}
              value={claimEditForm.description || ''}
              onChange={(e) => setClaimEditForm((p) => ({ ...p, description: e.target.value }))}
              className={`w-full px-3 py-2 text-sm resize-none ${t.input}`}
            />
          </div>
        </>,
      )}
    </div>
  );
}
