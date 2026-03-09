import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAccessToken, provisioning, employees as employeesApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Plus, X, Mail, AlertTriangle, CheckCircle, UserX, Clock, ChevronRight, ChevronDown, Search, MapPin } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { useIsLightMode } from '../hooks/useIsLightMode';
import type { GoogleWorkspaceConnectionStatus } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const LT = {
  pageBg: 'bg-stone-300',
  card: 'bg-stone-100 rounded-2xl',
  cardLight: 'bg-stone-100 rounded-2xl',
  cardDark: 'bg-zinc-900 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-800',
  cardDarkGhost: 'text-zinc-800',
  innerEl: 'bg-stone-200/60 rounded-xl border border-stone-200',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',
  border: 'border-stone-200',
  borderTab: 'border-stone-400/40',
  divide: 'divide-stone-200',
  tabActive: 'border-zinc-900 text-zinc-900',
  tabInactive: 'border-transparent text-stone-500 hover:text-stone-700 hover:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 text-stone-500 hover:text-zinc-900 hover:border-stone-400',
  btnSecondaryActive: 'border-stone-400 text-zinc-900 bg-stone-200',
  modalBg: 'bg-stone-100 border border-stone-200 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-stone-200',
  modalFooter: 'border-t border-stone-200',
  inputCls: 'bg-white border border-stone-300 text-zinc-900 text-sm rounded-xl focus:outline-none focus:border-stone-400 placeholder:text-stone-400 transition-colors',
  batchInputCls: 'bg-white border border-stone-300 text-zinc-900 rounded-lg',
  rowHover: 'hover:bg-stone-50',
  emptyBorder: 'border border-dashed border-stone-300 bg-stone-100 rounded-2xl',
  emptyIcon: 'bg-stone-200 border border-stone-300',
  alertWarn: 'border border-amber-300 bg-amber-50',
  alertWarnText: 'text-amber-700',
  alertError: 'bg-red-50 border border-red-300',
  alertErrorText: 'text-red-700',
  wizardActive: 'border-zinc-900 text-zinc-50 bg-zinc-900',
  wizardInactive: 'border-stone-300 text-stone-400',
  separator: 'bg-stone-300',
  progressBg: 'bg-stone-300',
  closeBtnCls: 'text-stone-400 hover:text-zinc-900 transition-colors',
  cancelBtn: 'text-stone-500 hover:text-zinc-900',
  chevron: 'text-stone-400 group-hover:text-stone-600',
  dropdownBg: 'bg-stone-100 border border-stone-200 shadow-xl',
  dropdownItem: 'text-stone-600 hover:bg-stone-50 hover:text-zinc-900',
  avatar: 'bg-zinc-900 text-zinc-50',
  genPreview: 'bg-stone-200/60 border border-stone-300 text-stone-600',
  tableHeader: 'bg-stone-200 text-stone-500',
  resultSuccess: 'border border-emerald-300 bg-emerald-50',
  resultFail: 'border border-red-300 bg-red-50',
  uploadZone: 'border-stone-400 bg-white hover:border-stone-500',
  uploadZoneDrag: 'border-emerald-500 bg-emerald-50',
  uploadZoneDone: 'border-emerald-400 bg-emerald-50',
  resultCard: 'bg-white border border-stone-200',
} as const;

const DK = {
  pageBg: 'bg-zinc-950',
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardLight: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardDark: 'bg-zinc-800 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-700',
  cardDarkGhost: 'text-zinc-700',
  innerEl: 'bg-zinc-900/40 rounded-xl border border-white/10',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',
  border: 'border-white/10',
  borderTab: 'border-white/10',
  divide: 'divide-white/10',
  tabActive: 'border-zinc-100 text-zinc-100',
  tabInactive: 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600',
  btnPrimary: 'bg-zinc-100 text-zinc-900 hover:bg-white',
  btnSecondary: 'border border-white/10 text-zinc-500 hover:text-zinc-100 hover:border-white/20',
  btnSecondaryActive: 'border-white/20 text-zinc-100 bg-zinc-800',
  modalBg: 'bg-zinc-900 border border-white/10 shadow-2xl rounded-2xl',
  modalHeader: 'border-b border-white/10',
  modalFooter: 'border-t border-white/10',
  inputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 text-sm rounded-xl focus:outline-none focus:border-white/20 placeholder:text-zinc-600 transition-colors',
  batchInputCls: 'bg-zinc-800 border border-white/10 text-zinc-100 rounded-lg',
  rowHover: 'hover:bg-white/5',
  emptyBorder: 'border border-dashed border-white/10 bg-zinc-900/30 rounded-2xl',
  emptyIcon: 'bg-zinc-800 border border-white/10',
  alertWarn: 'border border-amber-500/30 bg-amber-950/30',
  alertWarnText: 'text-amber-400',
  alertError: 'bg-red-950/30 border border-red-500/30',
  alertErrorText: 'text-red-400',
  wizardActive: 'border-zinc-100 text-zinc-900 bg-zinc-100',
  wizardInactive: 'border-zinc-700 text-zinc-600',
  separator: 'bg-zinc-700',
  progressBg: 'bg-zinc-700',
  closeBtnCls: 'text-zinc-500 hover:text-zinc-100 transition-colors',
  cancelBtn: 'text-zinc-500 hover:text-zinc-100',
  chevron: 'text-zinc-600 group-hover:text-zinc-400',
  dropdownBg: 'bg-zinc-900 border border-white/10 shadow-xl',
  dropdownItem: 'text-zinc-400 hover:bg-white/5 hover:text-zinc-100',
  avatar: 'bg-zinc-700 text-zinc-100',
  genPreview: 'bg-zinc-800/60 border border-white/10 text-zinc-400',
  tableHeader: 'bg-zinc-800 text-zinc-500',
  resultSuccess: 'border border-emerald-500/30 bg-emerald-950/40',
  resultFail: 'border border-red-500/30 bg-red-950/40',
  uploadZone: 'border-zinc-600 bg-zinc-800 hover:border-zinc-500',
  uploadZoneDrag: 'border-emerald-500/50 bg-emerald-950/20',
  uploadZoneDone: 'border-emerald-500/40 bg-emerald-950/20',
  resultCard: 'bg-zinc-800 border border-white/10',
} as const;

interface Employee {
  id: string;
  email: string;
  work_email?: string | null;
  personal_email?: string | null;
  first_name: string;
  last_name: string;
  work_state: string | null;
  employment_type: string | null;
  start_date: string | null;
  termination_date: string | null;
  manager_id: string | null;
  manager_name: string | null;
  user_id: string | null;
  invitation_status: string | null;
  pay_classification: string | null;
  pay_rate: number | null;
  work_city: string | null;
  work_zip: string | null;
  job_title: string | null;
  department: string | null;
  employment_status: string | null;
  status_changed_at: string | null;
  status_reason: string | null;
  created_at: string;
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';

  if (contentType.includes('application/json')) {
    const payload = await response.json().catch(() => null);
    if (payload && typeof payload === 'object') {
      const data = payload as { detail?: unknown; message?: unknown; error?: unknown };
      const candidate = data.detail ?? data.message ?? data.error;
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate;
      }
    }
  }

  const text = (await response.text().catch(() => '')).trim();
  if (!text || /^internal server error$/i.test(text)) {
    return fallback;
  }

  return text;
}

interface OnboardingProgress {
  employee_id: string;
  total: number;
  completed: number;
  pending: number;
  has_onboarding: boolean;
}


const EMPLOYEE_CYCLE_STEPS = [
  {
    id: 1,
    icon: 'onboard' as const,
    title: 'Onboard Personnel',
    description: 'Add new hires via the Onboarding Center using a single form, the Batch Wizard for up to 50 people, or a Bulk CSV upload.',
    action: 'Click "Add New Hire" to go to the Onboarding Center.',
  },
  {
    id: 2,
    icon: 'provision' as const,
    title: 'Auto-Provision',
    description: 'Synchronize with Google Workspace and Slack to automatically create business accounts for your new hires.',
    action: 'Configure Google Auto-Provisioning in Onboarding Settings.',
  },
  {
    id: 3,
    icon: 'invite' as const,
    title: 'Send Invitations',
    description: 'Issue portal invitations to employees so they can access their documents, PTO, and onboarding tasks.',
    action: 'Click "Send Invite" for employees in "Not Invited" status.',
  },
  {
    id: 4,
    icon: 'track' as const,
    title: 'Track Progress',
    description: 'Monitor real-time progress as employees complete their assigned onboarding tasks and document signatures.',
    action: 'View the "Onboarding" column in the directory below.',
  },
  {
    id: 5,
    icon: 'directory' as const,
    title: 'Manage Directory',
    description: 'Maintain your official system of record for active, pending, and terminated personnel.',
    action: 'Filter the directory by status to manage different employee groups.',
  },
];

type EmployeeEmptyState = {
  title: string;
  description: string;
  actionLabel: string | null;
  action: (() => void) | null;
  icon: 'add' | 'invited' | 'terminated';
};

function StatusActionBadge({ employee, handleSendInvite, invitingId }: { employee: Employee, handleSendInvite: (id: string) => void, invitingId: string | null }) {
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [selectedAction, setSelectedAction] = useState('invite');

  const base = 'inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] uppercase tracking-wider font-bold';

  if (employee.termination_date || employee.employment_status === 'terminated' || employee.employment_status === 'offboarded') {
    const neutral = 'bg-zinc-800 text-zinc-400 border border-zinc-700';
    return <span data-tour="emp-status-badge" className={`${base} ${neutral}`}><UserX size={10} /> Terminated</span>;
  }
  if (employee.user_id) {
    const status = employee.employment_status;
    if (status === 'on_leave') {
      const tone = 'bg-amber-950/40 text-amber-400 border border-amber-500/30';
      return <span data-tour="emp-status-badge" className={`${base} ${tone}`}><Clock size={10} /> On Leave</span>;
    }
    if (status === 'suspended') {
      const tone = 'bg-red-950/40 text-red-400 border border-red-500/30';
      return <span data-tour="emp-status-badge" className={`${base} ${tone}`}><AlertTriangle size={10} /> Suspended</span>;
    }
    if (status === 'on_notice') {
      const tone = 'bg-orange-950/40 text-orange-400 border border-orange-500/30';
      return <span data-tour="emp-status-badge" className={`${base} ${tone}`}><AlertTriangle size={10} /> On Notice</span>;
    }
    if (status === 'furloughed') {
      const tone = 'bg-amber-950/40 text-amber-400 border border-amber-500/30';
      return <span data-tour="emp-status-badge" className={`${base} ${tone}`}><Clock size={10} /> Furloughed</span>;
    }
    const active = 'bg-emerald-950/40 text-emerald-400 border border-emerald-500/30';
    return <span data-tour="emp-status-badge" className={`${base} ${active}`}><CheckCircle size={10} /> Active</span>;
  }

  const isPending = employee.invitation_status === 'pending';
  const badgeLabel = isPending ? 'Invited' : 'Not Invited';
  const bwClass = 'bg-zinc-100 text-zinc-900 border border-zinc-300';
  const notInvitedClass = 'bg-zinc-800 text-zinc-500 border border-zinc-700';

  if (mode === 'view') {
    return (
      <button
        data-tour="emp-status-badge"
        onClick={(e) => { e.stopPropagation(); setMode('edit'); setSelectedAction('invite'); }}
        className={`${base} ${isPending ? bwClass : notInvitedClass} hover:opacity-80 transition-opacity`}
      >
        {isPending ? <Clock size={10} /> : <Mail size={10} />}
        {badgeLabel}
        <ChevronDown size={10} className="ml-1 opacity-50" />
      </button>
    );
  }

  return (
    <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
      <select
        value={selectedAction}
        onChange={(e) => setSelectedAction(e.target.value)}
        className={`px-2 py-1 text-[10px] uppercase tracking-wider font-bold rounded-lg cursor-pointer focus:outline-none bg-zinc-800 text-zinc-100 border border-zinc-600`}
      >
        <option value="invite">{isPending ? 'Resend Invite' : 'Send Invite'}</option>
      </select>
      <button
        onClick={() => {
          if (selectedAction === 'invite') {
            handleSendInvite(employee.id);
          }
          setMode('view');
        }}
        disabled={invitingId === employee.id}
        className={`px-2 py-1 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-colors bg-zinc-100 text-zinc-900 hover:bg-white disabled:opacity-50`}
      >
        {invitingId === employee.id ? '...' : 'Submit'}
      </button>
      <button
        onClick={() => setMode('view')}
        className={`p-1 rounded-full text-zinc-400 hover:bg-zinc-700`}
      >
        <X size={12} />
      </button>
    </div>
  );
}

function EmployeeRow({ employee, navigate, onboardingProgress, handleSendInvite, invitingId, incidentCount }: {
  employee: Employee;
  navigate: (path: string) => void;
  onboardingProgress: Record<string, OnboardingProgress>;
  handleSendInvite: (id: string) => void;
  invitingId: string | null;
  incidentCount: number;
}) {
  return (
    <div
      onClick={() => navigate(`/app/matcha/employees/${employee.id}`)}
      className="group hover:bg-white/5 transition-colors py-3 px-4 md:px-6 flex flex-col xl:flex-row xl:items-center gap-4 cursor-pointer"
    >
      <div className="flex items-center min-w-[240px] flex-1">
        <div className="flex-shrink-0">
          <div className="h-9 w-9 rounded-xl bg-zinc-200 text-zinc-900 flex items-center justify-center font-bold text-[11px]">
            {employee.first_name[0]}{employee.last_name[0]}
          </div>
        </div>
        <div className="ml-3 min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-bold text-zinc-100 truncate">
              {employee.first_name || employee.last_name
                ? `${employee.first_name} ${employee.last_name}`.trim()
                : (employee.work_email || employee.email || 'Unknown')}
            </p>
          </div>
          {(employee.first_name || employee.last_name) && (
            <p className="text-[11px] text-zinc-500 truncate mt-0.5">
              {employee.job_title || (employee.work_email || employee.email)}
            </p>
          )}
          {!(employee.first_name || employee.last_name) && employee.job_title && (
            <p className="text-[11px] text-zinc-500 truncate mt-0.5">
              {employee.job_title}
            </p>
          )}
        </div>
        <div className="xl:hidden">
          <ChevronRight size={16} className="text-zinc-600" />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:flex sm:items-center justify-between xl:justify-end gap-x-4 gap-y-3 xl:gap-6 w-full xl:w-auto border-t border-white/5 pt-3 xl:border-0 xl:pt-0">
        <div className="xl:text-left xl:w-24">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Department</p>
          <p className="text-xs text-zinc-300 truncate">{employee.department || '—'}</p>
        </div>
        <div className="xl:text-left xl:w-28">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Location</p>
          <p className="text-[10px] text-zinc-300 font-mono leading-tight">{employee.work_city ? `${employee.work_city}, ${employee.work_state}` : (employee.work_state || '—')}</p>
        </div>
        <div className="xl:text-left xl:w-20">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Type</p>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider truncate">
            {employee.employment_type?.replace('_', ' ') || '—'}
          </p>
        </div>
        <div className="xl:text-center xl:w-10">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">IR</p>
          {incidentCount > 0 ? (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded bg-amber-950/40 text-amber-400 border border-amber-500/30">
              <AlertTriangle size={10} />
              {incidentCount}
            </span>
          ) : (
            <span className="text-[10px] text-zinc-600">—</span>
          )}
        </div>
        <div data-tour="emp-onboarding-col" className="xl:w-28 flex flex-col xl:items-start xl:justify-center">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Onboarding</p>
          {onboardingProgress[employee.id]?.has_onboarding ? (
            <div className="flex items-center gap-2">
              <div className="w-12 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all"
                  style={{
                    width: `${(onboardingProgress[employee.id].completed / onboardingProgress[employee.id].total) * 100}%`,
                  }}
                />
              </div>
              <span className="text-[10px] text-zinc-500 font-mono">
                {onboardingProgress[employee.id].completed}/{onboardingProgress[employee.id].total}
              </span>
            </div>
          ) : (
            <span className="text-[10px] text-zinc-600 uppercase tracking-wider">Not started</span>
          )}
        </div>
        <div className="col-span-2 sm:col-auto xl:w-48 flex xl:justify-end mt-2 sm:mt-0 xl:pr-4">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Status</p>
          <StatusActionBadge employee={employee} handleSendInvite={handleSendInvite} invitingId={invitingId} />
        </div>
        <div className="hidden xl:flex w-6 justify-end">
          <ChevronRight size={14} className="text-zinc-600 group-hover:text-zinc-300 transition-colors" />
        </div>
      </div>
    </div>
  );
}

export default function Employees() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('active');
  const [invitingId, setInvitingId] = useState<string | null>(null);
  const [onboardingProgress, setOnboardingProgress] = useState<Record<string, OnboardingProgress>>({});
  const { hasFeature } = useAuth();
  const [incidentCounts, setIncidentCounts] = useState<Record<string, number>>({});
  const [googleWorkspaceStatus, setGoogleWorkspaceStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleWorkspaceStatusLoading, setGoogleWorkspaceStatusLoading] = useState(false);

  // Search & filter state
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterDepartment, setFilterDepartment] = useState('');
  const [filterEmploymentType, setFilterEmploymentType] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [groupByLocation, setGroupByLocation] = useState(false);
  const [departments, setDepartments] = useState<string[]>([]);
  const [locations, setLocations] = useState<{ state: string; city: string | null }[]>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showFirstEmployeeBanner = employees.length === 0 && filter === '';

  const fetchEmployees = async () => {
    try {
      const token = getAccessToken();
      const params = new URLSearchParams();
      if (filter) params.set('status', filter);
      if (searchQuery) params.set('search', searchQuery);
      if (filterDepartment) params.set('department', filterDepartment);
      if (filterEmploymentType) params.set('employment_type', filterEmploymentType);
      if (filterLocation) {
        // filterLocation is "STATE" or "STATE|CITY"
        const [st, ct] = filterLocation.split('|');
        if (st) params.set('work_state', st);
        if (ct) params.set('work_city', ct);
      }
      const qs = params.toString();
      const url = `${API_BASE}/employees${qs ? `?${qs}` : ''}`;

      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'Failed to fetch employees'));
      }

      const data = await response.json();
      setEmployees(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const fetchOnboardingProgress = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/onboarding-progress`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error('Failed to fetch onboarding progress');

      const data = await response.json();
      setOnboardingProgress(data);
    } catch (err) {
      console.error('Failed to fetch onboarding progress:', err);
    }
  };

  const fetchGoogleWorkspaceStatus = async () => {
    setGoogleWorkspaceStatusLoading(true);
    try {
      const status = await provisioning.getGoogleWorkspaceStatus();
      setGoogleWorkspaceStatus(status);
    } catch (err) {
      console.error('Failed to fetch Google Workspace provisioning status:', err);
      setGoogleWorkspaceStatus(null);
    } finally {
      setGoogleWorkspaceStatusLoading(false);
    }
  };

  useEffect(() => {
    fetchEmployees();
    fetchOnboardingProgress();
    if (hasFeature('incidents')) {
      employeesApi.getIncidentCounts().then(setIncidentCounts).catch(() => setIncidentCounts({}));
    }
  }, [filter, searchQuery, filterDepartment, filterEmploymentType, filterLocation]);

  // Debounced search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setSearchQuery(searchInput);
    }, 300);
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [searchInput]);

  // Fetch departments + locations for filter dropdowns
  const fetchFilterOptions = async () => {
    try {
      const token = getAccessToken();
      const [deptRes, locRes] = await Promise.allSettled([
        fetch(`${API_BASE}/employees/departments`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_BASE}/employees/locations`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      if (deptRes.status === 'fulfilled' && deptRes.value.ok) {
        setDepartments(await deptRes.value.json());
      }
      if (locRes.status === 'fulfilled' && locRes.value.ok) {
        setLocations(await locRes.value.json());
      }
    } catch {
      // non-critical
    }
  };

  useEffect(() => {
    fetchGoogleWorkspaceStatus();
    fetchFilterOptions();
  }, []);

  const googleAutoProvisionBadge = () => {
    const defaultTone = isLight ? 'bg-stone-200 text-stone-600 border-stone-300' : 'bg-zinc-800 text-zinc-400 border-zinc-700';
    if (googleWorkspaceStatusLoading) {
      return { label: 'Loading', tone: defaultTone };
    }
    if (
      !googleWorkspaceStatus ||
      !googleWorkspaceStatus.connected ||
      googleWorkspaceStatus.status === 'disconnected'
    ) {
      return { label: 'Disconnected', tone: defaultTone };
    }
    if (
      googleWorkspaceStatus.status === 'error' ||
      googleWorkspaceStatus.status === 'needs_action'
    ) {
      return {
        label: 'Needs Attention',
        tone: 'bg-red-50 text-red-700 border-red-300',
      };
    }
    if (googleWorkspaceStatus.auto_provision_on_employee_create) {
      return {
        label: 'ON',
        tone: 'bg-emerald-50 text-emerald-700 border-emerald-300',
      };
    }
    return {
      label: 'OFF',
      tone: 'bg-amber-50 text-amber-700 border-amber-300',
    };
  };

  const handleSendInvite = async (employeeId: string) => {
    setInvitingId(employeeId);

    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/invite`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'Failed to send invitation'));
      }

      fetchEmployees();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setInvitingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className={`text-xs ${t.textMuted} uppercase tracking-wider animate-pulse`}>Loading directory...</div>
      </div>
    );
  }

  const googleBadge = googleAutoProvisionBadge();
  const emptyState: EmployeeEmptyState = (() => {
    if (filter === 'terminated') {
      return {
        title: 'No terminated employees yet',
        description: 'Employees will show up here after they have been marked as terminated in the system.',
        actionLabel: null,
        action: null,
        icon: 'terminated',
      };
    }

    if (filter === 'invited') {
      return {
        title: 'No pending invites',
        description: 'Employees will show up here after you send them a portal invitation.',
        actionLabel: null,
        action: null,
        icon: 'invited',
      };
    }

    if (filter === 'active') {
      return {
        title: 'No active employees yet',
        description: 'Use the onboarding wizard to add your first employee, then active employees will appear here.',
        actionLabel: 'Onboard New Employee',
        action: () => navigate('/app/matcha/onboarding?tab=employees'),
        icon: 'add',
      };
    }

    return {
      title: 'No employees found',
      description: 'Use the onboarding wizard to add your first employee, then they will appear here.',
      actionLabel: 'Onboard New Employee',
      action: () => navigate('/app/matcha/onboarding?tab=employees'),
      icon: 'add',
    };
  })();
  const EmptyStateIcon = emptyState.icon === 'terminated'
    ? UserX
    : emptyState.icon === 'invited'
      ? Mail
      : Plus;

  const wrapperClass = `-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`;

  return (
    <div className={wrapperClass}>
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className={`flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b ${t.borderTab} pb-8`}>
        <div>
          <div className="flex items-center gap-3 justify-center lg:justify-start">
            <h1 className={`text-3xl md:text-4xl font-bold tracking-tighter ${t.textMain} uppercase`}>Employees</h1>
            <FeatureGuideTrigger guideId="employees" />
          </div>
          <p className={`text-xs ${t.textMuted} mt-2 font-mono tracking-wide uppercase text-center lg:text-left`}>
            Manage your team
          </p>
          <div className="flex justify-center lg:justify-start">
            <button
              onClick={() => navigate('/app/matcha/onboarding?tab=workspace')}
              className={`mt-4 inline-flex items-center gap-2 ${t.btnSecondary} px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded-xl transition-colors`}
              title="Open Google Workspace provisioning settings"
            >
              <span className={t.textMuted}>Google Auto-Provision</span>
              <span className={`rounded-lg border px-2 py-0.5 ${googleBadge.tone}`}>{googleBadge.label}</span>
            </button>
          </div>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            data-tour="emp-add-hire-btn"
            onClick={() => navigate('/app/matcha/onboarding?tab=employees')}
            className={`flex items-center justify-center gap-2 px-4 sm:px-6 py-2.5 ${t.btnPrimary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
          >
            <Plus size={14} />
            Add New Hire
          </button>
        </div>
      </div>

      <div data-tour="emp-context">
        <LifecycleWizard
          steps={EMPLOYEE_CYCLE_STEPS}
          activeStep={
            employees.some(e => e.user_id) ? 5
            : Object.values(onboardingProgress).some(p => p.completed > 0) ? 4
            : employees.some(e => e.invitation_status === 'pending') ? 3
            : employees.length > 0 ? 2
            : 1
          }
          storageKey="employee-wizard-collapsed-v1"
          title="Employee Lifecycle"
        />
      </div>

      {showFirstEmployeeBanner && (
        <div className={`${t.alertWarn} px-4 py-3 text-[11px] rounded-xl`}>
          <p className={`font-bold uppercase tracking-wider ${t.alertWarnText}`}>No employees yet</p>
          <p className={`mt-1 ${t.alertWarnText} opacity-80`}>
            Use the Employee Lifecycle wizard to choose the best path for your first hires:
            Add Employee for one person, Batch Wizard for a few, or Bulk CSV if you already have a spreadsheet.
          </p>
        </div>
      )}

      {/* Help Panel */}
      {/* ... keeping help panel same as it uses grid-cols-1 md:grid-cols-2 already */}

      {/* Error message */}
      {error && (
        <div className={`${t.alertError} rounded-xl p-4 flex items-center justify-between gap-4`}>
          <div className="flex items-center gap-3">
             <AlertTriangle className={t.alertErrorText} size={16} />
             <p className={`text-sm ${t.alertErrorText} font-mono`}>{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className={`text-xs ${t.alertErrorText} uppercase tracking-wider font-bold shrink-0`}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filter tabs */}
      <div data-tour="emp-tabs" className={`border-b ${t.borderTab} -mx-4 px-4 sm:mx-0 sm:px-0`}>
        <nav className="-mb-px flex space-x-8 overflow-x-auto pb-px no-scrollbar">
          {[
            { value: '', label: 'All' },
            { value: 'active', label: 'Active' },
            { value: 'invited', label: 'Pending Invite' },
            { value: 'terminated', label: 'Terminated' },
          ].map((tab) => (
            <button
              key={tab.value}
              onClick={() => setFilter(tab.value)}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors whitespace-nowrap ${
                filter === tab.value ? t.tabActive : t.tabInactive
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Search + Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search size={14} className={`absolute left-3 top-1/2 -translate-y-1/2 ${t.textFaint}`} />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search name, email, title..."
            className={`w-full pl-9 pr-3 py-2.5 ${t.inputCls} text-xs`}
          />
        </div>
        {departments.length > 0 && (
          <select
            value={filterDepartment}
            onChange={(e) => setFilterDepartment(e.target.value)}
            className={`px-3 py-2.5 ${t.inputCls} text-xs`}
          >
            <option value="">All Departments</option>
            {departments.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        )}
        <select
          value={filterEmploymentType}
          onChange={(e) => setFilterEmploymentType(e.target.value)}
          className={`px-3 py-2.5 ${t.inputCls} text-xs`}
        >
          <option value="">All Types</option>
          <option value="full_time">Full Time</option>
          <option value="part_time">Part Time</option>
          <option value="contractor">Contractor</option>
          <option value="intern">Intern</option>
        </select>
        {locations.length > 0 && (
          <select
            value={filterLocation}
            onChange={(e) => setFilterLocation(e.target.value)}
            className={`px-3 py-2.5 ${t.inputCls} text-xs`}
          >
            <option value="">All Locations</option>
            {locations.map((loc) => {
              const val = loc.city ? `${loc.state}|${loc.city}` : loc.state;
              const label = loc.city ? `${loc.state} — ${loc.city}` : loc.state;
              return <option key={val} value={val}>{label}</option>;
            })}
          </select>
        )}
        <button
          onClick={() => setGroupByLocation(!groupByLocation)}
          className={`flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-bold uppercase tracking-wider transition-colors ${
            groupByLocation ? t.btnSecondaryActive : t.btnSecondary
          }`}
        >
          <MapPin size={12} />
          Group by Location
        </button>
        {(searchInput || filterDepartment || filterEmploymentType || filterLocation) && (
          <button
            onClick={() => { setSearchInput(''); setSearchQuery(''); setFilterDepartment(''); setFilterEmploymentType(''); setFilterLocation(''); }}
            className={`text-xs ${t.textMuted} hover:${t.textMain} uppercase tracking-wider font-bold`}
          >
            Clear
          </button>
        )}
      </div>

      {/* Employee list */}
      {employees.length === 0 ? (
        <div className={`text-center py-24 ${t.emptyBorder}`}>
          <div className={`w-16 h-16 mx-auto mb-6 rounded-full ${t.emptyIcon} flex items-center justify-center`}>
            <EmptyStateIcon size={24} className={t.textFaint} />
          </div>
          <>
            <h3 className={`${t.textMain} text-sm font-bold mb-1 uppercase tracking-wide`}>{emptyState.title}</h3>
            <p className={`${t.textMuted} text-xs mb-6 font-mono uppercase`}>{emptyState.description}</p>
            {emptyState.action && emptyState.actionLabel && (
              <button
                onClick={emptyState.action}
                className={`flex items-center gap-2 mx-auto px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
              >
                <Plus size={14} />
                {emptyState.actionLabel}
              </button>
            )}
          </>
        </div>
      ) : (
        <div data-tour="emp-list" className={`${t.cardDark} overflow-x-auto shadow-lg`}>
          <div className="min-w-[1024px]">
           {/* Table Header */}
           {!groupByLocation && (
             <div className={`hidden xl:flex items-center gap-6 py-4 px-6 text-[10px] ${DK.textMuted} font-bold uppercase tracking-wider border-b border-white/5`}>
                <div className="flex-1 min-w-[240px]">Name / Role</div>
                <div className="w-24 text-left">Department</div>
                <div className="w-28 text-left">Location</div>
                <div className="w-20 text-left">Type</div>
                <div className="w-10 text-center">IR</div>
                <div className="w-28 text-left">Onboarding</div>
                <div className="w-48 text-right pr-6">Status / Action</div>
                <div className="w-6"></div>
             </div>
           )}

          {groupByLocation ? (
            (() => {
              const groups: Record<string, Employee[]> = {};
              employees.forEach((emp) => {
                const key = emp.work_state
                  ? emp.work_city ? `${emp.work_state}|${emp.work_city}` : `${emp.work_state}|`
                  : '__none__';
                if (!groups[key]) groups[key] = [];
                groups[key].push(emp);
              });
              const sortedKeys = Object.keys(groups).sort((a, b) => {
                if (a === '__none__') return 1;
                if (b === '__none__') return -1;
                return a.localeCompare(b);
              });
              return (
                <div className="space-y-0">
                  {sortedKeys.map((key) => {
                    const emps = groups[key];
                    const [state, city] = key === '__none__' ? ['', ''] : key.split('|');
                    const label = key === '__none__'
                      ? 'Remote / No Location'
                      : city ? `${state} — ${city}` : state;
                    return (
                      <details key={key} open className="group/loc">
                        <summary className={`flex items-center gap-3 px-6 py-3 cursor-pointer bg-zinc-800/80 ${DK.textDim} text-xs font-bold uppercase tracking-wider`}>
                          <ChevronDown size={14} className="transition-transform group-open/loc:rotate-0 -rotate-90" />
                          <MapPin size={12} />
                          {label}
                          <span className={`${DK.textFaint} font-mono ml-1`}>({emps.length})</span>
                        </summary>
                        <div className="divide-y divide-white/5">
                          {emps.map((employee) => (
                            <EmployeeRow key={employee.id} employee={employee} navigate={navigate} onboardingProgress={onboardingProgress} handleSendInvite={handleSendInvite} invitingId={invitingId} incidentCount={incidentCounts[employee.id] || 0} />
                          ))}
                        </div>
                      </details>
                    );
                  })}
                </div>
              );
            })()
          ) : (
          <div className="divide-y divide-white/5">
          {employees.map((employee) => (
            <EmployeeRow key={employee.id} employee={employee} navigate={navigate} onboardingProgress={onboardingProgress} handleSendInvite={handleSendInvite} invitingId={invitingId} incidentCount={incidentCounts[employee.id] || 0} />          ))}
          </div>
          )}
          </div>
        </div>
      )}
    </div>
    </div>
  );
}
