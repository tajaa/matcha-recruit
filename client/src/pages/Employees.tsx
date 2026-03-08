import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAccessToken, provisioning, onboardingDraft, employees as employeesApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { complianceAPI } from '../api/compliance';
import { Plus, X, Mail, AlertTriangle, CheckCircle, UserX, Clock, ChevronRight, HelpCircle, ChevronDown, Settings, ClipboardCheck, Upload, Download, Search, MapPin } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { useIsLightMode } from '../hooks/useIsLightMode';
import type { GoogleWorkspaceConnectionStatus } from '../types';
import OnboardingAgentConsole from '../components/OnboardingAgentConsole';

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
  job_title: string | null;
  department: string | null;
  created_at: string;
}

interface NewEmployee {
  work_email: string;
  personal_email: string;
  first_name: string;
  last_name: string;
  office_location: string;
  work_state: string;
  employment_type: string;
  start_date: string;
  pay_classification: string;
  pay_rate: string;
  work_city: string;
  job_title: string;
  department: string;
}

type EmailEntryMode = 'generated' | 'existing';
type WorkLocationMode = 'remote' | 'office';
type AddWizardStep = 1 | 2 | 3;
type BatchWizardStep = 1 | 2 | 3;

interface BatchEmployeeRow {
  id: string;
  first_name: string;
  last_name: string;
  work_email: string;
  personal_email: string;
  work_state: string;
  office_location: string;
  employment_type: string;
  start_date: string;
  skip_google_workspace_provisioning: boolean;
  pay_classification: string;
  pay_rate: string;
  work_city: string;
}

interface BatchCreateError {
  row_number: number;
  name: string;
  error: string;
}

interface BatchCreateResult {
  created: number;
  failed: number;
  errors: BatchCreateError[];
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

function sanitizeEmailLocalPart(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/['`]/g, '')
    .replace(/[^a-z0-9._-]+/g, '.')
    .replace(/\.+/g, '.')
    .replace(/^[._-]+|[._-]+$/g, '');
}

function buildGeneratedEmailLocalPart(firstName: string, lastName: string): string {
  const first = sanitizeEmailLocalPart(firstName);
  const last = sanitizeEmailLocalPart(lastName);
  if (first && last) return `${first}.${last}`;
  return first || last;
}

function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function createBatchRow(defaultStartDate: string): BatchEmployeeRow {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    first_name: '',
    last_name: '',
    work_email: '',
    personal_email: '',
    work_state: '',
    office_location: '',
    employment_type: 'full_time',
    start_date: defaultStartDate,
    skip_google_workspace_provisioning: true,
    pay_classification: '',
    pay_rate: '',
    work_city: '',
  };
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
    description: 'Add new hires to your directory. You can use a single form, the Batch Wizard for up to 50 people, or a Bulk CSV upload.',
    action: 'Click "Onboard New Employee" or "Add Employee" to begin.',
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

function StatusActionBadge({ employee, isLight, handleSendInvite, invitingId }: { employee: Employee, isLight: boolean, handleSendInvite: (id: string) => void, invitingId: string | null }) {
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [selectedAction, setSelectedAction] = useState('invite');

  const base = 'inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] uppercase tracking-wider font-bold';

  if (employee.termination_date) {
    const neutral = isLight ? 'bg-stone-200 text-stone-600 border border-stone-300' : 'bg-zinc-800 text-zinc-400 border border-zinc-700';
    return <span className={`${base} ${neutral}`}><UserX size={10} /> Terminated</span>;
  }
  if (employee.user_id) {
    const active = isLight ? 'bg-emerald-50 text-emerald-700 border border-emerald-300' : 'bg-emerald-950/40 text-emerald-400 border border-emerald-500/30';
    return <span className={`${base} ${active}`}><CheckCircle size={10} /> Active</span>;
  }

  const isPending = employee.invitation_status === 'pending';
  const badgeLabel = isPending ? 'Invited' : 'Not Invited';
  const bwClass = isLight ? 'bg-white text-zinc-900 border border-zinc-300 shadow-sm' : 'bg-zinc-100 text-zinc-900 border border-zinc-300';
  const notInvitedClass = isLight ? 'bg-stone-200 text-stone-500 border border-stone-300' : 'bg-zinc-800 text-zinc-500 border border-zinc-700';

  if (mode === 'view') {
    return (
      <button
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
        className={`px-2 py-1 text-[10px] uppercase tracking-wider font-bold rounded-lg cursor-pointer focus:outline-none ${isLight ? 'bg-white text-zinc-900 border border-zinc-300' : 'bg-zinc-800 text-zinc-100 border border-zinc-600'}`}
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
        className={`px-2 py-1 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-colors ${isLight ? 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800' : 'bg-zinc-100 text-zinc-900 hover:bg-white'} disabled:opacity-50`}
      >
        {invitingId === employee.id ? '...' : 'Submit'}
      </button>
      <button
        onClick={() => setMode('view')}
        className={`p-1 rounded-full ${isLight ? 'text-zinc-500 hover:bg-stone-200' : 'text-zinc-400 hover:bg-zinc-700'}`}
      >
        <X size={12} />
      </button>
    </div>
  );
}

function EmployeeRow({ employee, t, isLight, navigate, onboardingProgress, handleSendInvite, invitingId, incidentCount }: {
  employee: Employee;
  t: typeof LT | typeof DK;
  isLight: boolean;
  navigate: (path: string) => void;
  onboardingProgress: Record<string, OnboardingProgress>;
  handleSendInvite: (id: string) => void;
  invitingId: string | null;
  incidentCount: number;
}) {
  return (
    <div
      onClick={() => navigate(`/app/matcha/employees/${employee.id}`)}
      className={`group ${isLight ? 'hover:bg-stone-50' : 'hover:bg-white/5'} transition-colors py-3 px-4 md:px-6 flex flex-col xl:flex-row xl:items-center gap-4 cursor-pointer`}
    >
      <div className="flex items-center min-w-[240px] flex-1">
        <div className="flex-shrink-0">
          <div className={`h-9 w-9 rounded-xl ${isLight ? 'bg-zinc-900 text-zinc-50' : 'bg-zinc-200 text-zinc-900'} flex items-center justify-center font-bold text-[11px]`}>
            {employee.first_name[0]}{employee.last_name[0]}
          </div>
        </div>
        <div className="ml-3 min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className={`text-sm font-bold ${t.textMain} truncate`}>
              {employee.first_name || employee.last_name 
                ? `${employee.first_name} ${employee.last_name}`.trim() 
                : (employee.work_email || employee.email || 'Unknown')}
            </p>
          </div>
          {(employee.first_name || employee.last_name) && (
            <p className={`text-[11px] ${t.textMuted} truncate mt-0.5`}>
              {employee.job_title || (employee.work_email || employee.email)}
            </p>
          )}
          {!(employee.first_name || employee.last_name) && employee.job_title && (
            <p className={`text-[11px] ${t.textMuted} truncate mt-0.5`}>
              {employee.job_title}
            </p>
          )}
        </div>
        <div className="xl:hidden">
          <ChevronRight size={16} className={t.textFaint} />
        </div>
      </div>

      <div className={`grid grid-cols-2 sm:flex sm:items-center justify-between xl:justify-end gap-x-4 gap-y-3 xl:gap-6 w-full xl:w-auto border-t ${isLight ? 'border-stone-200' : 'border-white/5'} pt-3 xl:border-0 xl:pt-0`}>
        <div className="xl:text-left xl:w-24">
          <p className={`text-[9px] ${t.textMuted} uppercase tracking-wider xl:hidden mb-0.5`}>Department</p>
          <p className={`text-xs ${isLight ? 'text-stone-600' : 'text-zinc-300'} truncate`}>{employee.department || '—'}</p>
        </div>
        <div className="xl:text-left xl:w-28">
          <p className={`text-[9px] ${t.textMuted} uppercase tracking-wider xl:hidden mb-0.5`}>Location</p>
          <p className={`text-[10px] ${isLight ? 'text-stone-600' : 'text-zinc-300'} font-mono leading-tight`}>{employee.work_city ? `${employee.work_city}, ${employee.work_state}` : (employee.work_state || '—')}</p>
        </div>
        <div className="xl:text-left xl:w-20">
          <p className={`text-[9px] ${t.textMuted} uppercase tracking-wider xl:hidden mb-0.5`}>Type</p>
          <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider truncate`}>
            {employee.employment_type?.replace('_', ' ') || '—'}
          </p>
        </div>
        <div className="xl:text-center xl:w-10">
          <p className={`text-[9px] ${t.textMuted} uppercase tracking-wider xl:hidden mb-0.5`}>IR</p>
          {incidentCount > 0 ? (
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded ${isLight ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-amber-950/40 text-amber-400 border border-amber-500/30'}`}>
              <AlertTriangle size={10} />
              {incidentCount}
            </span>
          ) : (
            <span className={`text-[10px] ${t.textFaint}`}>—</span>
          )}
        </div>
        <div data-tour="emp-onboarding-col" className="xl:w-28 flex flex-col xl:items-start xl:justify-center">
          <p className={`text-[9px] ${t.textMuted} uppercase tracking-wider xl:hidden mb-0.5`}>Onboarding</p>
          {onboardingProgress[employee.id]?.has_onboarding ? (
            <div className="flex items-center gap-2">
              <div className={`w-12 h-1.5 ${isLight ? 'bg-stone-300' : 'bg-zinc-800'} rounded-full overflow-hidden`}>
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all"
                  style={{
                    width: `${(onboardingProgress[employee.id].completed / onboardingProgress[employee.id].total) * 100}%`,
                  }}
                />
              </div>
              <span className={`text-[10px] ${t.textMuted} font-mono`}>
                {onboardingProgress[employee.id].completed}/{onboardingProgress[employee.id].total}
              </span>
            </div>
          ) : (
            <span className={`text-[10px] ${t.textFaint} uppercase tracking-wider`}>Not started</span>
          )}
        </div>
        <div className="col-span-2 sm:col-auto xl:w-48 flex xl:justify-end mt-2 sm:mt-0 xl:pr-4">
          <p className={`text-[9px] ${t.textMuted} uppercase tracking-wider xl:hidden mb-0.5`}>Status</p>
          <StatusActionBadge employee={employee} isLight={isLight} handleSendInvite={handleSendInvite} invitingId={invitingId} />
        </div>
        <div className="hidden xl:flex w-6 justify-end">
          <ChevronRight size={14} className={`${t.textFaint} group-hover:${isLight ? 'text-stone-600' : 'text-zinc-300'} transition-colors`} />
        </div>
      </div>
    </div>
  );
}

export default function Employees({ mode = 'directory' }: { mode?: 'onboarding' | 'directory' }) {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filter, setFilter] = useState<string>(mode === 'directory' ? 'active' : '');
  const [newEmployee, setNewEmployee] = useState<NewEmployee>({
    work_email: '',
    personal_email: '',
    first_name: '',
    last_name: '',
    office_location: '',
    work_state: '',
    employment_type: 'full_time',
    start_date: new Date().toISOString().split('T')[0],
    pay_classification: '',
    pay_rate: '',
    work_city: '',
    job_title: '',
    department: '',
  });
  const [emailEntryMode, setEmailEntryMode] = useState<EmailEntryMode>('existing');
  const [generatedEmailLocalPart, setGeneratedEmailLocalPart] = useState('');
  const [generatedEmailEdited, setGeneratedEmailEdited] = useState(false);
  const [skipGoogleAutoProvision, setSkipGoogleAutoProvision] = useState(false);
  const [workLocationMode, setWorkLocationMode] = useState<WorkLocationMode>('remote');
  const [addWizardStep, setAddWizardStep] = useState<AddWizardStep>(1);

  const [showBatchWizardModal, setShowBatchWizardModal] = useState(false);
  const [batchWizardStep, setBatchWizardStep] = useState<BatchWizardStep>(1);
  const [batchEmailMode, setBatchEmailMode] = useState<EmailEntryMode>('existing');
  const [batchWorkLocationMode, setBatchWorkLocationMode] = useState<WorkLocationMode>('remote');
  const [batchRows, setBatchRows] = useState<BatchEmployeeRow[]>([]);
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [batchResult, setBatchResult] = useState<BatchCreateResult | null>(null);
  const [draftLoaded, setDraftLoaded] = useState(false);
  const [draftDirty, setDraftDirty] = useState(false);
  const [draftSaving, setDraftSaving] = useState(false);
  const draftSnapshotRef = useRef<string>('');

  const [submitting, setSubmitting] = useState(false);
  const [invitingId, setInvitingId] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [onboardingProgress, setOnboardingProgress] = useState<Record<string, OnboardingProgress>>({});
  const { hasFeature } = useAuth();
  const [incidentCounts, setIncidentCounts] = useState<Record<string, number>>({});
  const [agentEmployee, setAgentEmployee] = useState<{
    id: string; name: string; workEmail: string; personalEmail: string;
  } | null>(null);
  const [showSettingsDropdown, setShowSettingsDropdown] = useState(false);
  const [googleWorkspaceStatus, setGoogleWorkspaceStatus] = useState<GoogleWorkspaceConnectionStatus | null>(null);
  const [googleWorkspaceStatusLoading, setGoogleWorkspaceStatusLoading] = useState(false);

  // Bulk upload state
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [sendInvitationsOnUpload, setSendInvitationsOnUpload] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [bulkInviting, setBulkInviting] = useState(false);
  const [bulkInviteResult, setBulkInviteResult] = useState<{ sent: number; failed: number } | null>(null);
  const [inviteAllLoading, setInviteAllLoading] = useState(false);
  const [inviteAllResult, setInviteAllResult] = useState<{ sent: number; failed: number } | null>(null);

  // Search & filter state
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterDepartment, setFilterDepartment] = useState('');
  const [filterEmploymentType, setFilterEmploymentType] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [groupByLocation, setGroupByLocation] = useState(false);
  const [departments, setDepartments] = useState<string[]>([]);
  const [locations, setLocations] = useState<{ state: string; city: string | null }[]>([]);
  const [complianceLocations, setComplianceLocations] = useState<{ city: string; state: string }[]>([]);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const normalizedGoogleDomain = (googleWorkspaceStatus?.domain || '')
    .trim()
    .replace(/^@/, '')
    .toLowerCase();
  const googleDomainAvailable = Boolean(
    normalizedGoogleDomain &&
      googleWorkspaceStatus?.connected &&
      googleWorkspaceStatus.status === 'connected'
  );
  const showFirstEmployeeBanner = employees.length === 0 && (mode === 'onboarding' || filter === '');

  const resetAddEmployeeForm = useCallback(() => {
    setNewEmployee({
      work_email: '',
      personal_email: '',
      first_name: '',
      last_name: '',
      office_location: '',
      work_state: '',
      employment_type: 'full_time',
      start_date: new Date().toISOString().split('T')[0],
      pay_classification: '',
      pay_rate: '',
      work_city: '',
      job_title: '',
      department: '',
    });
    setEmailEntryMode(googleDomainAvailable ? 'generated' : 'existing');
    setGeneratedEmailLocalPart('');
    setGeneratedEmailEdited(false);
    setSkipGoogleAutoProvision(false);
    setWorkLocationMode('remote');
    setAddWizardStep(1);
  }, [googleDomainAvailable]);

  const resetBatchWizard = useCallback(() => {
    const defaultStartDate = new Date().toISOString().split('T')[0];
    setBatchWizardStep(1);
    setBatchEmailMode(googleDomainAvailable ? 'generated' : 'existing');
    setBatchWorkLocationMode('remote');
    setBatchRows([
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
      createBatchRow(defaultStartDate),
    ]);
    setBatchResult(null);
  }, [googleDomainAvailable]);

  // Dirty detection for batch wizard draft
  useEffect(() => {
    if (!draftLoaded) return;
    const current = JSON.stringify({ batchRows, emailMode: batchEmailMode, workLocationMode: batchWorkLocationMode, wizardStep: batchWizardStep });
    setDraftDirty(current !== draftSnapshotRef.current);
  }, [batchRows, batchEmailMode, batchWorkLocationMode, batchWizardStep, draftLoaded]);

  // Autosave batch wizard draft with 5-second debounce
  const DRAFT_AUTOSAVE_MS = 5000;
  useEffect(() => {
    if (!draftLoaded || !draftDirty) return;
    const timer = setTimeout(async () => {
      setDraftSaving(true);
      try {
        const state = { batchRows, emailMode: batchEmailMode, workLocationMode: batchWorkLocationMode, wizardStep: batchWizardStep };
        await onboardingDraft.save(state as unknown as Record<string, unknown>);
        draftSnapshotRef.current = JSON.stringify(state);
        setDraftDirty(false);
      } catch {
        // silently fail autosave
      } finally {
        setDraftSaving(false);
      }
    }, DRAFT_AUTOSAVE_MS);
    return () => clearTimeout(timer);
  }, [draftLoaded, draftDirty, batchRows, batchEmailMode, batchWorkLocationMode, batchWizardStep]);

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
    complianceAPI.getLocations().then(
      (locs) => setComplianceLocations(locs.map((l) => ({ city: l.city, state: l.state }))),
      () => {} // non-critical
    );
  }, []);

  useEffect(() => {
    if (!showAddModal) return;
    setEmailEntryMode(googleDomainAvailable ? 'generated' : 'existing');
    setGeneratedEmailEdited(false);
    setSkipGoogleAutoProvision(false);
    setWorkLocationMode('remote');
    if (!googleDomainAvailable) setGeneratedEmailLocalPart('');
  }, [showAddModal, googleDomainAvailable]);

  useEffect(() => {
    if (!showAddModal || emailEntryMode !== 'generated' || generatedEmailEdited) return;
    const generated = buildGeneratedEmailLocalPart(newEmployee.first_name, newEmployee.last_name);
    setGeneratedEmailLocalPart(generated);
  }, [
    showAddModal,
    emailEntryMode,
    generatedEmailEdited,
    newEmployee.first_name,
    newEmployee.last_name,
  ]);

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

  const handleAddEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const token = getAccessToken();
      const generatedWorkEmail = googleDomainAvailable && generatedEmailLocalPart
        ? `${generatedEmailLocalPart}@${normalizedGoogleDomain}`
        : '';
      const resolvedWorkEmail = (
        emailEntryMode === 'generated' ? generatedWorkEmail : newEmployee.work_email
      )
        .trim()
        .toLowerCase();
      if (!resolvedWorkEmail) {
        throw new Error('Work email is required');
      }
      if (workLocationMode === 'remote' && (!newEmployee.work_state || !newEmployee.work_city)) {
        throw new Error('Work location is required for remote employees');
      }
      if (workLocationMode === 'office' && !newEmployee.office_location.trim()) {
        throw new Error('Office/store location is required for on-site employees');
      }

      const payload = {
        email: resolvedWorkEmail,
        work_email: resolvedWorkEmail,
        personal_email: newEmployee.personal_email || undefined,
        first_name: newEmployee.first_name,
        last_name: newEmployee.last_name,
        work_state: workLocationMode === 'remote' ? (newEmployee.work_state || undefined) : undefined,
        address: workLocationMode === 'office' ? (newEmployee.office_location || undefined) : undefined,
        employment_type: newEmployee.employment_type,
        start_date: newEmployee.start_date,
        skip_google_workspace_provisioning:
          emailEntryMode === 'existing' && skipGoogleAutoProvision,
        pay_classification: newEmployee.pay_classification || undefined,
        pay_rate: newEmployee.pay_rate ? parseFloat(newEmployee.pay_rate) : undefined,
        work_city: newEmployee.work_city || undefined,
        job_title: newEmployee.job_title || undefined,
        department: newEmployee.department || undefined,
      };
      const response = await fetch(`${API_BASE}/employees`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'Failed to add employee'));
      }

      const createdEmployee = await response.json();

      setAgentEmployee({
        id: createdEmployee.id,
        name: `${newEmployee.first_name} ${newEmployee.last_name}`,
        workEmail: resolvedWorkEmail,
        personalEmail: newEmployee.personal_email,
      });

      fetchEmployees();
      fetchOnboardingProgress();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
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

  const handleDownloadTemplate = async () => {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/bulk-upload/template`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error('Failed to download template');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'employee_bulk_upload_template.csv';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download template');
    }
  };

  const handleBulkUpload = async () => {
    if (!uploadFile) return;

    setUploadLoading(true);
    setUploadResult(null);

    try {
      const token = getAccessToken();
      const formData = new FormData();
      formData.append('file', uploadFile);

      const response = await fetch(
        `${API_BASE}/employees/bulk-upload?send_invitations=${sendInvitationsOnUpload}`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        }
      );

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'Failed to upload CSV'));
      }

      const result = await response.json();
      setUploadResult(result);
      fetchEmployees();
      fetchOnboardingProgress();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload CSV');
    } finally {
      setUploadLoading(false);
    }
  };

  const handleFileSelect = (file: File | null) => {
    if (file && file.type === 'text/csv') {
      setUploadFile(file);
      setUploadResult(null);
    } else if (file) {
      setError('Please select a CSV file');
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    handleFileSelect(file);
  };

  // Unique "City, ST" pairs from compliance locations for the work location dropdown
  const complianceLocationOptions = Array.from(
    new Set(complianceLocations.map((l) => `${l.city}|${l.state}`))
  ).map((key) => {
    const [city, state] = key.split('|');
    return { city, state, label: `${city}, ${state}` };
  }).sort((a, b) => a.label.localeCompare(b.label));

  const generatedSingleWorkEmail = googleDomainAvailable && generatedEmailLocalPart
    ? `${generatedEmailLocalPart}@${normalizedGoogleDomain}`
    : '';
  const canProceedAddStep1 = Boolean(
    newEmployee.first_name.trim() && newEmployee.last_name.trim()
  );
  const canProceedAddStep2 = emailEntryMode === 'generated'
    ? Boolean(generatedSingleWorkEmail)
    : looksLikeEmail(newEmployee.work_email);
  const hasSingleLocation = workLocationMode === 'remote'
    ? Boolean(newEmployee.work_state && newEmployee.work_city)
    : Boolean(newEmployee.office_location.trim());
  const canSubmitSingleWizard = canProceedAddStep1 && canProceedAddStep2 && hasSingleLocation;

  const BATCH_MAX_ROWS = 50;
  const batchRowsWithInput = batchRows.filter((row) =>
    Boolean(
      row.first_name.trim() ||
        row.last_name.trim() ||
        row.work_email.trim() ||
        row.personal_email.trim() ||
        row.work_state.trim() ||
        row.office_location.trim()
    )
  );

  const resolveBatchRowWorkEmail = (row: BatchEmployeeRow): string => {
    if (batchEmailMode === 'generated') {
      const localPart = buildGeneratedEmailLocalPart(row.first_name, row.last_name);
      return localPart && normalizedGoogleDomain ? `${localPart}@${normalizedGoogleDomain}` : '';
    }
    return row.work_email.trim().toLowerCase();
  };

  const batchRowValidationError = (row: BatchEmployeeRow): string | null => {
    if (!row.first_name.trim() || !row.last_name.trim()) return 'First and last name are required';
    if (batchEmailMode === 'generated') {
      if (!googleDomainAvailable) return 'Google Workspace domain is required for generated emails';
      if (!resolveBatchRowWorkEmail(row)) return 'Could not generate work email from name';
    } else if (!looksLikeEmail(row.work_email)) {
      return 'Valid work email is required';
    }

    if (batchWorkLocationMode === 'remote' && (!row.work_state.trim() || !row.work_city.trim())) {
      return 'Work location is required for remote employees';
    }
    if (batchWorkLocationMode === 'office' && !row.office_location.trim()) {
      return 'Office/store is required for on-site employees';
    }
    return null;
  };

  const canProceedBatchStep2 = batchRowsWithInput.length > 0 && batchRowsWithInput.every((row) => !batchRowValidationError(row));

  const updateBatchRowField = <K extends keyof BatchEmployeeRow>(
    rowId: string,
    field: K,
    value: BatchEmployeeRow[K]
  ) => {
    setBatchRows((prev) =>
      prev.map((row) => (row.id === rowId ? { ...row, [field]: value } : row))
    );
  };

  const addBatchRow = () => {
    if (batchRows.length >= BATCH_MAX_ROWS) return;
    const defaultStartDate = new Date().toISOString().split('T')[0];
    setBatchRows((prev) => [...prev, createBatchRow(defaultStartDate)]);
  };

  const removeBatchRow = (rowId: string) => {
    setBatchRows((prev) => {
      const next = prev.filter((row) => row.id !== rowId);
      return next.length > 0 ? next : [createBatchRow(new Date().toISOString().split('T')[0])];
    });
  };

  const handleBatchCreate = async () => {
    if (!canProceedBatchStep2) return;
    setBatchSubmitting(true);
    setBatchResult(null);

    try {
      const token = getAccessToken();
      let created = 0;
      let failed = 0;
      const errors: BatchCreateError[] = [];

      for (let idx = 0; idx < batchRowsWithInput.length; idx += 1) {
        const row = batchRowsWithInput[idx];
        const rowError = batchRowValidationError(row);
        if (rowError) {
          failed += 1;
          errors.push({
            row_number: idx + 1,
            name: `${row.first_name} ${row.last_name}`.trim() || `Row ${idx + 1}`,
            error: rowError,
          });
          continue;
        }

        const resolvedWorkEmail = resolveBatchRowWorkEmail(row);
        const payload = {
          email: resolvedWorkEmail,
          work_email: resolvedWorkEmail,
          personal_email: row.personal_email.trim() || undefined,
          first_name: row.first_name.trim(),
          last_name: row.last_name.trim(),
          work_state: batchWorkLocationMode === 'remote' ? row.work_state.trim() : undefined,
          address: batchWorkLocationMode === 'office' ? row.office_location.trim() : undefined,
          employment_type: row.employment_type,
          start_date: row.start_date,
          skip_google_workspace_provisioning:
            batchEmailMode === 'existing' ? row.skip_google_workspace_provisioning : false,
          pay_classification: row.pay_classification || undefined,
          pay_rate: row.pay_rate ? parseFloat(row.pay_rate) : undefined,
          work_city: row.work_city || undefined,
        };

        try {
          const response = await fetch(`${API_BASE}/employees`, {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
          });

          if (!response.ok) {
            failed += 1;
            errors.push({
              row_number: idx + 1,
              name: `${row.first_name} ${row.last_name}`.trim() || `Row ${idx + 1}`,
              error: await readErrorMessage(response, 'Failed to create employee'),
            });
            continue;
          }

          created += 1;
        } catch {
          failed += 1;
          errors.push({
            row_number: idx + 1,
            name: `${row.first_name} ${row.last_name}`.trim() || `Row ${idx + 1}`,
            error: 'Network error while creating employee',
          });
        }
      }

      setBatchResult({ created, failed, errors });
      fetchEmployees();
      fetchOnboardingProgress();
      // Clear the draft after a successful batch submission
      try { await onboardingDraft.clear(); } catch { /* ignore */ }
      draftSnapshotRef.current = '';
      setDraftDirty(false);
    } finally {
      setBatchSubmitting(false);
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
    if (mode === 'onboarding') {
      return {
        title: 'Onboard your first employee',
        description: 'Your directory is empty. Use the lifecycle wizard below to pick the fastest onboarding path.',
        actionLabel: 'Add Employee',
        action: () => {
          resetAddEmployeeForm();
          setShowAddModal(true);
        },
        icon: 'add',
      };
    }

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

  const wrapperClass = mode === 'directory'
    ? `-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen ${t.pageBg}`
    : '';

  return (
    <div className={wrapperClass}>
    <div className={`mx-auto space-y-8 ${mode === 'directory' ? 'max-w-5xl animate-in fade-in duration-500' : 'max-w-7xl'}`}>
      {/* Header */}
      <div className={`flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b ${t.borderTab} pb-8`}>
        {mode === 'directory' ? (
          <>
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
                onClick={() => navigate('/app/matcha/onboarding?tab=employees')}
                className={`flex items-center justify-center gap-2 px-4 sm:px-6 py-2.5 ${t.btnPrimary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
              >
                <Plus size={14} />
                Onboard New Employee
              </button>
            </div>
          </>
        ) : (
          <div className="grid grid-cols-2 sm:flex sm:items-center gap-2 sm:gap-3">
            <button
              data-tour="emp-help-btn"
              onClick={() => setShowHelp(!showHelp)}
              className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 border text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors ${
                showHelp ? t.btnSecondaryActive : t.btnSecondary
              }`}
            >
              <HelpCircle size={14} />
              <span>Help</span>
              <ChevronDown size={12} className={`transition-transform ${showHelp ? 'rotate-180' : ''}`} />
            </button>

            <div className="relative">
              <button
                onClick={() => setShowSettingsDropdown(!showSettingsDropdown)}
                className={`w-full flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 border text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors ${
                  showSettingsDropdown ? t.btnSecondaryActive : t.btnSecondary
                }`}
              >
                <Settings size={14} />
                <span>Tools</span>
              </button>
              {showSettingsDropdown && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowSettingsDropdown(false)}
                  />
                  <div className={`absolute right-0 mt-2 w-56 ${t.dropdownBg} z-20 rounded-xl overflow-hidden`}>
                    <button
                      onClick={() => {
                        setShowSettingsDropdown(false);
                        navigate('/app/matcha/onboarding-templates');
                      }}
                      className={`w-full flex items-center gap-3 px-4 py-3 text-left text-xs font-medium ${t.dropdownItem} transition-colors`}
                    >
                      <ClipboardCheck size={14} />
                      Onboarding Templates
                    </button>
                  </div>
                </>
              )}
            </div>

            <button
              data-tour="emp-bulk-btn"
              onClick={() => setShowBulkUploadModal(true)}
              className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 ${t.btnSecondary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
            >
              <Upload size={14} />
              <span>Bulk CSV</span>
            </button>

            <button
              onClick={async () => {
                resetBatchWizard();
                setDraftLoaded(false);
                setDraftDirty(false);
                setShowBatchWizardModal(true);
                try {
                  const draft = await onboardingDraft.get();
                  if (draft?.draft_state && Array.isArray((draft.draft_state as Record<string, unknown>).batchRows) && ((draft.draft_state as Record<string, unknown>).batchRows as unknown[]).length > 0) {
                    const s = draft.draft_state as Record<string, unknown>;
                    setBatchRows(s.batchRows as BatchEmployeeRow[]);
                    setBatchEmailMode((s.emailMode as EmailEntryMode) ?? 'existing');
                    setBatchWorkLocationMode((s.workLocationMode as WorkLocationMode) ?? 'remote');
                    setBatchWizardStep((s.wizardStep as BatchWizardStep) ?? 1);
                  }
                  draftSnapshotRef.current = JSON.stringify(draft?.draft_state ?? {});
                } catch {
                  draftSnapshotRef.current = '';
                }
                setDraftLoaded(true);
              }}
              className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 ${t.btnSecondary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
            >
              <ClipboardCheck size={14} />
              <span>Batch Wizard</span>
            </button>

            <button
              data-tour="emp-add-btn"
              onClick={() => {
                resetAddEmployeeForm();
                setShowAddModal(true);
              }}
              className={`flex items-center justify-center gap-2 px-4 sm:px-6 py-2.5 ${t.btnPrimary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
            >
              <Plus size={14} />
              Add Employee
            </button>

            {/* Invite All button — only in onboarding mode when uninvited employees exist */}
            {mode === 'onboarding' && (() => {
              const uninvitedCount = employees.filter(e => !e.user_id && !e.termination_date && e.invitation_status !== 'pending').length;
              if (uninvitedCount === 0) return null;
              return (
                <button
                  onClick={async () => {
                    setInviteAllLoading(true);
                    setInviteAllResult(null);
                    try {
                      const token = getAccessToken();
                      const res = await fetch(`${API_BASE}/employees/invite-all`, {
                        method: 'POST',
                        headers: { Authorization: `Bearer ${token}` },
                      });
                      if (res.ok) {
                        const data = await res.json();
                        setInviteAllResult({ sent: data.sent, failed: data.failed });
                        // Refresh employee list to update invitation statuses
                        const empRes = await fetch(`${API_BASE}/employees`, {
                          headers: { Authorization: `Bearer ${token}` },
                        });
                        if (empRes.ok) {
                          const empData = await empRes.json();
                          setEmployees(empData);
                        }
                      } else {
                        setInviteAllResult({ sent: 0, failed: -1 });
                      }
                    } catch (err) {
                      console.error('Invite all failed:', err);
                      setInviteAllResult({ sent: 0, failed: -1 });
                    } finally {
                      setInviteAllLoading(false);
                    }
                  }}
                  disabled={inviteAllLoading}
                  className={`flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 ${t.btnSecondary} text-[10px] sm:text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50`}
                >
                  {inviteAllLoading ? (
                    <span className="w-3 h-3 border-2 border-current/20 border-t-current rounded-full animate-spin" />
                  ) : (
                    <Mail size={14} />
                  )}
                  {inviteAllResult
                    ? inviteAllResult.failed === -1
                      ? 'Failed — try again'
                      : `${inviteAllResult.sent} Sent${inviteAllResult.failed ? `, ${inviteAllResult.failed} Failed` : ''}`
                    : `Invite All (${uninvitedCount})`
                  }
                </button>
              );
            })()}
          </div>
        )}
      </div>

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

      {showFirstEmployeeBanner && (
        <div className={`${t.alertWarn} px-4 py-3 text-[11px] rounded-xl`}>
          <p className={`font-bold uppercase tracking-wider ${t.alertWarnText}`}>No employees yet</p>
          <p className={`mt-1 ${t.alertWarnText} opacity-80`}>
            Use the Employee Lifecycle wizard to choose the best path for your first hires:
            Add Employee for one person, Batch Wizard for a few, or Bulk CSV if you already have a spreadsheet.
          </p>
        </div>
      )}

      {mode === 'onboarding' && (
        <div className="bg-zinc-900 rounded-2xl p-5 text-[11px] text-zinc-400 space-y-1">
          <p className="uppercase tracking-wider text-zinc-500">Onboarding flows</p>
          <p>
            Use <span className="text-zinc-200 font-medium">Add Employee</span> for one hire,{' '}
            <span className="text-zinc-200 font-medium">Batch Wizard</span> for up to 50 hires, or{' '}
            <span className="text-zinc-200 font-medium">Bulk CSV</span> when you already have a spreadsheet.
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
             <div className={`hidden xl:flex items-center gap-6 py-4 px-6 text-[10px] ${t.textMuted} font-bold uppercase tracking-wider border-b ${isLight ? 'border-stone-200' : 'border-white/5'}`}>
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
                        <summary className={`flex items-center gap-3 px-6 py-3 cursor-pointer ${isLight ? 'bg-stone-200/80' : 'bg-zinc-800/80'} ${t.textDim} text-xs font-bold uppercase tracking-wider`}>
                          <ChevronDown size={14} className="transition-transform group-open/loc:rotate-0 -rotate-90" />
                          <MapPin size={12} />
                          {label}
                          <span className={`${t.textFaint} font-mono ml-1`}>({emps.length})</span>
                        </summary>
                        <div className={`divide-y ${isLight ? 'divide-stone-200' : 'divide-white/5'}`}>
                          {emps.map((employee) => (
                            <EmployeeRow key={employee.id} employee={employee} t={t} isLight={isLight} navigate={navigate} onboardingProgress={onboardingProgress} handleSendInvite={handleSendInvite} invitingId={invitingId} incidentCount={incidentCounts[employee.id] || 0} />
                          ))}
                        </div>
                      </details>
                    );
                  })}
                </div>
              );
            })()
          ) : (
          <div className={`divide-y ${isLight ? 'divide-stone-200' : 'divide-white/5'}`}>
          {employees.map((employee) => (
            <EmployeeRow key={employee.id} employee={employee} t={t} isLight={isLight} navigate={navigate} onboardingProgress={onboardingProgress} handleSendInvite={handleSendInvite} invitingId={invitingId} incidentCount={incidentCounts[employee.id] || 0} />          ))}
          </div>
          )}
          </div>
        </div>
      )}
      {/* Add Employee Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className={`w-full max-w-lg ${t.modalBg} max-h-[90vh] overflow-hidden flex flex-col`} onClick={(e) => e.stopPropagation()}>
              {agentEmployee ? (
                <OnboardingAgentConsole
                  employeeId={agentEmployee.id}
                  employeeName={agentEmployee.name}
                  companyName=""
                  workEmail={agentEmployee.workEmail}
                  personalEmail={agentEmployee.personalEmail}
                  googleEnabled={googleDomainAvailable}
                  onAddAnother={() => {
                    setAgentEmployee(null);
                    resetAddEmployeeForm();
                  }}
                  onViewProfile={(id) => {
                    setShowAddModal(false);
                    setAgentEmployee(null);
                    navigate(`/app/matcha/employees/${id}`);
                  }}
                  onClose={() => {
                    setShowAddModal(false);
                    setAgentEmployee(null);
                    resetAddEmployeeForm();
                  }}
                />
              ) : (
              <>
              <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
                  <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>Add Personnel</h3>
                  <button
                    onClick={() => {
                      setShowAddModal(false);
                      resetAddEmployeeForm();
                    }}
                    className={t.closeBtnCls}
                  >
                    <X size={20} />
                  </button>
              </div>

              <form onSubmit={handleAddEmployee} className="flex-1 overflow-y-auto p-8">
                <div className="space-y-6">
                  <div className={`${t.innerEl} p-3`}>
                    <p className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                      Step {addWizardStep} of 3
                    </p>
                    <p className={`text-xs ${t.textDim} mt-1`}>
                      {addWizardStep === 1 &&
                        'Start with name and optional personal email. Work email setup comes next.'}
                      {addWizardStep === 2 &&
                        'Choose generated or existing work email. Generated mode uses your configured Google domain.'}
                      {addWizardStep === 3 &&
                        'Set remote state or office/store, confirm details, then create the employee.'}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    {[1, 2, 3].map((step) => (
                      <div key={step} className="flex items-center gap-3">
                        <div
                          className={`h-6 w-6 rounded-full border text-[10px] font-bold flex items-center justify-center ${
                            addWizardStep >= step ? t.wizardActive : t.wizardInactive
                          }`}
                        >
                          {step}
                        </div>
                        {step < 3 && <div className={`h-px w-8 ${t.separator}`} />}
                      </div>
                    ))}
                  </div>

                  {addWizardStep === 1 && (
                    <div className="space-y-6">
                      <p className={`text-[11px] ${t.textMuted}`}>
                        Required now: first and last name.
                      </p>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            First Name <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            required
                            value={newEmployee.first_name}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, first_name: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          />
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Last Name <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            required
                            value={newEmployee.last_name}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, last_name: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          />
                        </div>
                      </div>

                      <div>
                        <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                          Personal Email (Optional)
                        </label>
                        <input
                          type="email"
                          value={newEmployee.personal_email}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, personal_email: e.target.value })
                          }
                          className={`w-full px-3 py-2 ${t.inputCls}`}
                          placeholder="johnny_bravo@gmail.com"
                        />
                      </div>
                    </div>
                  )}

                  {addWizardStep === 2 && (
                    <div className="space-y-6">
                      <p className={`text-[11px] ${t.textMuted}`}>
                        Choose generated email for new Workspace accounts, or existing email for already provisioned employees.
                      </p>
                      <div className="space-y-3">
                        <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                          Work Email Setup <span className="text-red-500">*</span>
                        </label>

                        {googleDomainAvailable ? (
                          <div className={`space-y-3 ${t.innerEl} p-3`}>
                            <label className="flex items-start gap-3 cursor-pointer">
                              <input
                                type="radio"
                                name="email_entry_mode"
                                checked={emailEntryMode === 'generated'}
                                onChange={() => {
                                  setEmailEntryMode('generated');
                                  setSkipGoogleAutoProvision(false);
                                  if (!generatedEmailEdited) {
                                    setGeneratedEmailLocalPart(
                                      buildGeneratedEmailLocalPart(newEmployee.first_name, newEmployee.last_name)
                                    );
                                  }
                                }}
                                className="mt-0.5"
                              />
                              <div className="space-y-0.5">
                                <p className={`text-xs ${t.textMain} font-medium`}>Generate from first + last name</p>
                                <p className={`text-[11px] ${t.textMuted}`}>
                                  Domain detected from Google Workspace: <span className={t.textMain}>@{normalizedGoogleDomain}</span>
                                </p>
                              </div>
                            </label>

                            <label className="flex items-start gap-3 cursor-pointer">
                              <input
                                type="radio"
                                name="email_entry_mode"
                                checked={emailEntryMode === 'existing'}
                                onChange={() => {
                                  setEmailEntryMode('existing');
                                  setSkipGoogleAutoProvision(true);
                                  if (!newEmployee.work_email && generatedEmailLocalPart) {
                                    setNewEmployee({
                                      ...newEmployee,
                                      work_email: `${generatedEmailLocalPart}@${normalizedGoogleDomain}`,
                                    });
                                  }
                                }}
                                className="mt-0.5"
                              />
                              <div className="space-y-0.5">
                                <p className={`text-xs ${t.textMain} font-medium`}>Use existing work email</p>
                                <p className={`text-[11px] ${t.textMuted}`}>
                                  Use this when the employee already has a company mailbox.
                                </p>
                              </div>
                            </label>
                          </div>
                        ) : (
                          <p className={`text-[11px] ${t.textMuted}`}>
                            Configure Google Workspace domain in onboarding settings to auto-generate work emails.
                          </p>
                        )}
                      </div>

                      <div>
                        {emailEntryMode === 'generated' && googleDomainAvailable ? (
                          <div className="space-y-2">
                            <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                              Work Email Username <span className="text-red-500">*</span>
                            </label>
                            <div className={`flex items-center ${t.inputCls} overflow-hidden`}>
                              <input
                                type="text"
                                required
                                value={generatedEmailLocalPart}
                                onChange={(e) => {
                                  setGeneratedEmailEdited(true);
                                  setGeneratedEmailLocalPart(sanitizeEmailLocalPart(e.target.value));
                                }}
                                className={`w-full px-3 py-2 bg-transparent ${t.textMain} text-sm focus:outline-none`}
                                placeholder="firstname.lastname"
                              />
                              <span className={`px-3 py-2 text-sm ${t.textMuted} border-l ${t.border}`}>
                                @{normalizedGoogleDomain}
                              </span>
                            </div>
                            <p className={`text-[11px] ${t.textMuted}`}>
                              Final email: <span className={t.textMain}>{generatedEmailLocalPart || 'firstname.lastname'}@{normalizedGoogleDomain}</span>
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                              Work Email <span className="text-red-500">*</span>
                            </label>
                            <input
                              type="email"
                              required
                              value={newEmployee.work_email}
                              onChange={(e) =>
                                setNewEmployee({ ...newEmployee, work_email: e.target.value })
                              }
                              className={`w-full px-3 py-2 ${t.inputCls}`}
                              placeholder="johnny.bravo@energyco.com"
                            />
                            {googleDomainAvailable && (
                              <label className={`inline-flex items-center gap-2 text-[11px] ${t.textMuted}`}>
                                <input
                                  type="checkbox"
                                  checked={skipGoogleAutoProvision}
                                  onChange={(e) => setSkipGoogleAutoProvision(e.target.checked)}
                                />
                                Skip Google auto-provisioning (employee already has Workspace account)
                              </label>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {addWizardStep === 3 && (
                    <div className="space-y-6">
                      <p className={`text-[11px] ${t.textMuted}`}>
                        Final step: define where they work and verify a quick summary before creating.
                      </p>
                      <div className="space-y-2">
                        <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                          Work Location
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            type="button"
                            onClick={() => setWorkLocationMode('remote')}
                            className={`border px-3 py-2 text-xs font-bold uppercase tracking-wider rounded-xl transition-colors ${
                              workLocationMode === 'remote'
                                ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                                : t.btnSecondary
                            }`}
                          >
                            Remote
                          </button>
                          <button
                            type="button"
                            onClick={() => setWorkLocationMode('office')}
                            className={`border px-3 py-2 text-xs font-bold uppercase tracking-wider rounded-xl transition-colors ${
                              workLocationMode === 'office'
                                ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                                : t.btnSecondary
                            }`}
                          >
                            Office / Store
                          </button>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          {workLocationMode === 'remote' ? (
                            <>
                              <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                                Work Location <span className="text-red-500">*</span>
                              </label>
                              {complianceLocationOptions.length > 0 ? (
                                <select
                                  value={newEmployee.work_city && newEmployee.work_state ? `${newEmployee.work_city}|${newEmployee.work_state}` : ''}
                                  onChange={(e) => {
                                    if (!e.target.value) {
                                      setNewEmployee({ ...newEmployee, work_city: '', work_state: '' });
                                    } else {
                                      const [city, state] = e.target.value.split('|');
                                      setNewEmployee({ ...newEmployee, work_city: city, work_state: state });
                                    }
                                  }}
                                  className={`w-full px-3 py-2 ${t.inputCls}`}
                                >
                                  <option value="">Select location</option>
                                  {complianceLocationOptions.map((loc) => (
                                    <option key={`${loc.city}|${loc.state}`} value={`${loc.city}|${loc.state}`}>
                                      {loc.label}
                                    </option>
                                  ))}
                                </select>
                              ) : (
                                <p className={`text-xs ${t.textMuted} px-3 py-2 ${t.innerEl}`}>
                                  No compliance locations found. Add locations in the Compliance page first.
                                </p>
                              )}
                            </>
                          ) : (
                            <>
                              <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                                Office / Store <span className="text-red-500">*</span>
                              </label>
                              <input
                                type="text"
                                value={newEmployee.office_location}
                                onChange={(e) =>
                                  setNewEmployee({ ...newEmployee, office_location: e.target.value })
                                }
                                className={`w-full px-3 py-2 ${t.inputCls}`}
                                placeholder="Downtown HQ"
                              />
                            </>
                          )}
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Employment Type
                          </label>
                          <select
                            value={newEmployee.employment_type}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, employment_type: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          >
                            <option value="full_time">Full Time</option>
                            <option value="part_time">Part Time</option>
                            <option value="contractor">Contractor</option>
                            <option value="intern">Intern</option>
                          </select>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Job Title
                          </label>
                          <input
                            type="text"
                            value={newEmployee.job_title}
                            onChange={(e) => setNewEmployee({ ...newEmployee, job_title: e.target.value })}
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                            placeholder="Software Engineer"
                          />
                        </div>
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Department
                          </label>
                          <input
                            type="text"
                            value={newEmployee.department}
                            onChange={(e) => setNewEmployee({ ...newEmployee, department: e.target.value })}
                            list="add-dept-options"
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                            placeholder="Engineering"
                          />
                          <datalist id="add-dept-options">
                            {departments.map((d) => <option key={d} value={d} />)}
                          </datalist>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                            Pay Classification
                          </label>
                          <select
                            value={newEmployee.pay_classification}
                            onChange={(e) =>
                              setNewEmployee({ ...newEmployee, pay_classification: e.target.value })
                            }
                            className={`w-full px-3 py-2 ${t.inputCls}`}
                          >
                            <option value="">Not specified</option>
                            <option value="hourly">Hourly</option>
                            <option value="exempt">Exempt (Salaried)</option>
                          </select>
                        </div>
                        {newEmployee.pay_classification && (
                          <div>
                            <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                              {newEmployee.pay_classification === 'hourly' ? 'Hourly Rate ($)' : 'Annual Salary ($)'}
                            </label>
                            <input
                              type="number"
                              min="0"
                              step="0.01"
                              value={newEmployee.pay_rate}
                              onChange={(e) =>
                                setNewEmployee({ ...newEmployee, pay_rate: e.target.value })
                              }
                              className={`w-full px-3 py-2 ${t.inputCls}`}
                              placeholder={newEmployee.pay_classification === 'hourly' ? '18.50' : '65000'}
                            />
                          </div>
                        )}
                      </div>

                      <div>
                        <label className={`block text-[10px] font-bold uppercase tracking-widest ${t.textMuted} mb-2`}>
                          Start Date
                        </label>
                        <input
                          type="date"
                          value={newEmployee.start_date}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, start_date: e.target.value })
                          }
                          className={`w-full px-3 py-2 ${t.inputCls}`}
                        />
                      </div>

                      <div className={`${t.innerEl} p-3 text-[11px] ${t.textMuted} space-y-1`}>
                        <p>
                          <span className={t.textMain}>Work email:</span>{' '}
                          {emailEntryMode === 'generated' ? generatedSingleWorkEmail : newEmployee.work_email}
                        </p>
                        <p>
                          <span className={t.textMain}>Location:</span>{' '}
                          {workLocationMode === 'remote'
                            ? `Remote (${newEmployee.work_city && newEmployee.work_state ? `${newEmployee.work_city}, ${newEmployee.work_state}` : 'location required'})`
                            : `Office/Store (${newEmployee.office_location || 'location required'})`}
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {error && (
                  <div className={`${t.alertError} rounded-xl p-3 flex items-center gap-3 mt-4`}>
                    <AlertTriangle className={t.alertErrorText} size={14} />
                    <p className={`text-xs ${t.alertErrorText} font-mono flex-1`}>{error}</p>
                    <button onClick={() => setError(null)} className={`text-[10px] ${t.alertErrorText} uppercase tracking-wider font-bold shrink-0`}>
                      Dismiss
                    </button>
                  </div>
                )}

                <div className={`mt-8 flex justify-end gap-3 pt-6 ${t.modalFooter}`}>
                  <button
                    type="button"
                    onClick={() => {
                      setShowAddModal(false);
                      resetAddEmployeeForm();
                    }}
                    className={`px-4 py-2 ${t.cancelBtn} text-xs font-bold uppercase tracking-wider transition-colors`}
                  >
                    Cancel
                  </button>
                  {addWizardStep > 1 && (
                    <button
                      type="button"
                      onClick={() => setAddWizardStep((prev) => (prev - 1) as AddWizardStep)}
                      className={`px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                    >
                      Back
                    </button>
                  )}
                  {addWizardStep < 3 && (
                    <button
                      type="button"
                      onClick={() => setAddWizardStep((prev) => (prev + 1) as AddWizardStep)}
                      disabled={(addWizardStep === 1 && !canProceedAddStep1) || (addWizardStep === 2 && !canProceedAddStep2)}
                      className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                    >
                      Next
                    </button>
                  )}
                  {addWizardStep === 3 && (
                    <button
                      type="submit"
                      disabled={submitting || !canSubmitSingleWizard}
                      className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                    >
                      {submitting ? 'Adding...' : 'Add Employee'}
                    </button>
                  )}
                </div>
              </form>
              </>
              )}
            </div>
        </div>
      )}

      {/* Batch Wizard Modal */}
      {showBatchWizardModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-6xl ${t.modalBg} max-h-[90vh] overflow-hidden flex flex-col`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
              <div>
                <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>Batch Onboarding Wizard</h3>
                <div className="flex items-center gap-3 mt-1">
                  <p className={`text-xs ${t.textMuted}`}>Create up to 50 employees in one guided flow</p>
                  {draftLoaded && (
                    <span className={`text-[10px] uppercase tracking-wider ${draftSaving ? t.textMuted : t.textFaint}`}>
                      {draftSaving ? 'Saving…' : draftDirty ? '' : 'Draft saved'}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={async () => {
                  try { await onboardingDraft.clear(); } catch { /* ignore */ }
                  draftSnapshotRef.current = '';
                  setDraftDirty(false);
                  setDraftLoaded(false);
                  setShowBatchWizardModal(false);
                  setBatchResult(null);
                }}
                className={`${t.closeBtnCls}`}
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              <div className={`${t.innerEl} p-3`}>
                <p className={`text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                  Step {batchWizardStep} of 3
                </p>
                <p className={`text-xs ${t.textDim} mt-1`}>
                  {batchWizardStep === 1 &&
                    'Set defaults for email and location handling. These apply to every row in step 2.'}
                  {batchWizardStep === 2 &&
                    'Enter up to 50 rows. Only rows with data are submitted, and invalid rows are blocked.'}
                  {batchWizardStep === 3 &&
                    'Review counts and submit. Any failed rows will be listed with row-level errors.'}
                </p>
              </div>

              <div className="flex items-center gap-3">
                {[1, 2, 3].map((step) => (
                  <div key={step} className="flex items-center gap-3">
                    <div
                      className={`h-6 w-6 rounded-full border text-[10px] font-bold flex items-center justify-center ${
                        batchWizardStep >= step
                          ? 'border-zinc-900 text-zinc-50 bg-zinc-900'
                          : t.wizardInactive
                      }`}
                    >
                      {step}
                    </div>
                    {step < 3 && <div className={`h-px w-8 ${t.separator}`} />}
                  </div>
                ))}
              </div>

              {batchWizardStep === 1 && (
                <div className="space-y-6">
                  <div className="space-y-2">
                    <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                      Work Email Mode
                    </label>
                    {googleDomainAvailable ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setBatchEmailMode('generated')}
                          className={`border p-3 text-left rounded-xl transition-colors ${
                            batchEmailMode === 'generated'
                              ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                              : t.btnSecondary
                          }`}
                        >
                          <p className={`text-xs font-bold uppercase tracking-wider ${batchEmailMode === 'generated' ? 'text-zinc-50' : t.textMain}`}>Generate From Name</p>
                          <p className={`text-[11px] mt-1 ${batchEmailMode === 'generated' ? 'text-zinc-400' : t.textMuted}`}>Uses @{normalizedGoogleDomain}</p>
                        </button>
                        <button
                          type="button"
                          onClick={() => setBatchEmailMode('existing')}
                          className={`border p-3 text-left rounded-xl transition-colors ${
                            batchEmailMode === 'existing'
                              ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                              : t.btnSecondary
                          }`}
                        >
                          <p className={`text-xs font-bold uppercase tracking-wider ${batchEmailMode === 'existing' ? 'text-zinc-50' : t.textMain}`}>Existing Work Emails</p>
                          <p className={`text-[11px] mt-1 ${batchEmailMode === 'existing' ? 'text-zinc-400' : t.textMuted}`}>For already-provisioned mailboxes</p>
                        </button>
                      </div>
                    ) : (
                      <div className={`${t.innerEl} p-3 text-[11px] ${t.textMuted}`}>
                        Google Workspace domain is not configured, so batch mode uses existing work emails.
                      </div>
                    )}
                  </div>

                  <div className="space-y-2">
                    <label className={`block text-[10px] uppercase tracking-wider ${t.textMuted}`}>
                      Work Location Mode
                    </label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setBatchWorkLocationMode('remote')}
                        className={`border p-3 text-left rounded-xl transition-colors ${
                          batchWorkLocationMode === 'remote'
                            ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                            : t.btnSecondary
                        }`}
                      >
                        <p className={`text-xs font-bold uppercase tracking-wider ${batchWorkLocationMode === 'remote' ? 'text-zinc-50' : t.textMain}`}>Remote</p>
                        <p className={`text-[11px] mt-1 ${batchWorkLocationMode === 'remote' ? 'text-zinc-400' : t.textMuted}`}>Each employee must include a compliance location</p>
                      </button>
                      <button
                        type="button"
                        onClick={() => setBatchWorkLocationMode('office')}
                        className={`border p-3 text-left rounded-xl transition-colors ${
                          batchWorkLocationMode === 'office'
                            ? 'border-zinc-900 bg-zinc-900 text-zinc-50'
                            : t.btnSecondary
                        }`}
                      >
                        <p className={`text-xs font-bold uppercase tracking-wider ${batchWorkLocationMode === 'office' ? 'text-zinc-50' : t.textMain}`}>Office / Store</p>
                        <p className={`text-[11px] mt-1 ${batchWorkLocationMode === 'office' ? 'text-zinc-400' : t.textMuted}`}>Each employee must include office/store location</p>
                      </button>
                    </div>
                  </div>

                  <div className={`${t.innerEl} p-3 text-[11px] ${t.textMuted} space-y-1`}>
                    <p>Step 2 lets you enter up to 50 rows.</p>
                    <p>Only non-empty rows are processed.</p>
                    <p>Use Add Row for more lines, and remove any line with the X action.</p>
                  </div>
                </div>
              )}

              {batchWizardStep === 2 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className={`text-xs ${t.textMuted} uppercase tracking-wider`}>
                      Rows: {batchRows.length}/{BATCH_MAX_ROWS}
                    </p>
                    <button
                      type="button"
                      onClick={addBatchRow}
                      disabled={batchRows.length >= BATCH_MAX_ROWS}
                      className={`inline-flex items-center gap-2 px-3 py-1.5 ${t.btnSecondary} text-[10px] font-bold uppercase tracking-wider rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
                    >
                      <Plus size={12} />
                      Add Row
                    </button>
                  </div>

                  <div className={`overflow-auto border ${t.border} rounded-xl`}>
                    <table className="min-w-[1200px] w-full text-xs">
                      <thead className={`${t.tableHeader} uppercase tracking-wider text-[10px]`}>
                        <tr>
                          <th className="px-2 py-2 text-left">#</th>
                          <th className="px-2 py-2 text-left">First</th>
                          <th className="px-2 py-2 text-left">Last</th>
                          <th className="px-2 py-2 text-left">{batchEmailMode === 'generated' ? 'Generated Email' : 'Work Email'}</th>
                          <th className="px-2 py-2 text-left">Personal Email</th>
                          <th className="px-2 py-2 text-left">{batchWorkLocationMode === 'remote' ? 'Location' : 'Office/Store'}</th>
                          <th className="px-2 py-2 text-left">Type</th>
                          <th className="px-2 py-2 text-left">Start</th>
                          {batchEmailMode === 'existing' && <th className="px-2 py-2 text-left">Skip Google</th>}
                          <th className="px-2 py-2 text-left">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchRows.map((row, idx) => {
                          const rowEmailPreview = resolveBatchRowWorkEmail(row);
                          const rowError = row.first_name || row.last_name || row.work_email || row.personal_email || row.work_state || row.office_location
                            ? batchRowValidationError(row)
                            : null;
                          return (
                            <tr key={row.id} className={`border-t ${t.border} align-top`}>
                              <td className={`px-2 py-2 ${t.textMuted}`}>{idx + 1}</td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.first_name}
                                  onChange={(e) => updateBatchRowField(row.id, 'first_name', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                />
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="text"
                                  value={row.last_name}
                                  onChange={(e) => updateBatchRowField(row.id, 'last_name', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                />
                              </td>
                              <td className="px-2 py-2">
                                {batchEmailMode === 'generated' ? (
                                  <div className={`px-2 py-1.5 ${t.genPreview} rounded-lg min-w-[220px]`}>
                                    {rowEmailPreview || 'auto-generated from name'}
                                  </div>
                                ) : (
                                  <input
                                    type="email"
                                    value={row.work_email}
                                    onChange={(e) => updateBatchRowField(row.id, 'work_email', e.target.value)}
                                    className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                  />
                                )}
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="email"
                                  value={row.personal_email}
                                  onChange={(e) => updateBatchRowField(row.id, 'personal_email', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                />
                              </td>
                              <td className="px-2 py-2">
                                {batchWorkLocationMode === 'remote' ? (
                                  complianceLocationOptions.length > 0 ? (
                                    <select
                                      value={row.work_city && row.work_state ? `${row.work_city}|${row.work_state}` : ''}
                                      onChange={(e) => {
                                        if (!e.target.value) {
                                          updateBatchRowField(row.id, 'work_city', '');
                                          updateBatchRowField(row.id, 'work_state', '');
                                        } else {
                                          const [city, state] = e.target.value.split('|');
                                          updateBatchRowField(row.id, 'work_city', city);
                                          updateBatchRowField(row.id, 'work_state', state);
                                        }
                                      }}
                                      className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                    >
                                      <option value="">Location</option>
                                      {complianceLocationOptions.map((loc) => (
                                        <option key={`${loc.city}|${loc.state}`} value={`${loc.city}|${loc.state}`}>
                                          {loc.label}
                                        </option>
                                      ))}
                                    </select>
                                  ) : (
                                    <span className={`text-[10px] ${t.textMuted} px-2 py-1.5`}>No locations</span>
                                  )
                                ) : (
                                  <input
                                    type="text"
                                    value={row.office_location}
                                    onChange={(e) => updateBatchRowField(row.id, 'office_location', e.target.value)}
                                    className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                    placeholder="Downtown HQ"
                                  />
                                )}
                              </td>
                              <td className="px-2 py-2">
                                <select
                                  value={row.employment_type}
                                  onChange={(e) => updateBatchRowField(row.id, 'employment_type', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                >
                                  <option value="full_time">Full Time</option>
                                  <option value="part_time">Part Time</option>
                                  <option value="contractor">Contractor</option>
                                  <option value="intern">Intern</option>
                                </select>
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  type="date"
                                  value={row.start_date}
                                  onChange={(e) => updateBatchRowField(row.id, 'start_date', e.target.value)}
                                  className={`w-full px-2 py-1.5 ${t.batchInputCls}`}
                                />
                              </td>
                              {batchEmailMode === 'existing' && (
                                <td className="px-2 py-2">
                                  <input
                                    type="checkbox"
                                    checked={row.skip_google_workspace_provisioning}
                                    onChange={(e) =>
                                      updateBatchRowField(
                                        row.id,
                                        'skip_google_workspace_provisioning',
                                        e.target.checked
                                      )
                                    }
                                  />
                                </td>
                              )}
                              <td className="px-2 py-2">
                                <button
                                  type="button"
                                  onClick={() => removeBatchRow(row.id)}
                                  className={`${t.textFaint} hover:text-red-500`}
                                  aria-label="Remove row"
                                >
                                  <X size={14} />
                                </button>
                                {rowError && (
                                  <p className="mt-2 text-[10px] text-red-400 whitespace-nowrap">{rowError}</p>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {batchWizardStep === 3 && (
                <div className="space-y-4">
                  <div className={`${t.innerEl} p-4 text-xs ${t.textMuted} space-y-1`}>
                    <p>
                      Ready to create <span className={`${t.textMain} font-semibold`}>{batchRowsWithInput.length}</span> employees.
                    </p>
                    <p>Email mode: <span className={t.textMain}>{batchEmailMode === 'generated' ? 'Generated' : 'Existing'}</span></p>
                    <p>Location mode: <span className={t.textMain}>{batchWorkLocationMode === 'remote' ? 'Remote (state)' : 'Office/Store'}</span></p>
                  </div>

                  {batchResult && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="border border-emerald-300 bg-emerald-50 p-3 rounded-xl">
                          <p className="text-2xl font-bold text-emerald-700">{batchResult.created}</p>
                          <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Created</p>
                        </div>
                        <div className="border border-red-300 bg-red-50 p-3 rounded-xl">
                          <p className="text-2xl font-bold text-red-700">{batchResult.failed}</p>
                          <p className={`text-[10px] ${t.textMuted} uppercase tracking-wider`}>Failed</p>
                        </div>
                      </div>
                      {batchResult.errors.length > 0 && (
                        <div className="max-h-56 overflow-y-auto space-y-2 border border-red-300 bg-red-50 p-3 rounded-xl">
                          {batchResult.errors.map((err) => (
                            <div key={`${err.row_number}-${err.name}`} className="text-xs">
                              <p className="text-red-700">
                                Row {err.row_number} {err.name ? `(${err.name})` : ''}
                              </p>
                              <p className={t.textMuted}>{err.error}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className={`p-6 ${t.modalFooter} flex justify-end gap-3`}>
              <button
                type="button"
                onClick={async () => {
                  try { await onboardingDraft.clear(); } catch { /* ignore */ }
                  draftSnapshotRef.current = '';
                  setDraftDirty(false);
                  setDraftLoaded(false);
                  setShowBatchWizardModal(false);
                  setBatchResult(null);
                }}
                className={`px-4 py-2 ${t.cancelBtn} text-xs font-bold uppercase tracking-wider transition-colors`}
              >
                Cancel
              </button>
              {batchWizardStep > 1 && !batchSubmitting && (
                <button
                  type="button"
                  onClick={() => setBatchWizardStep((prev) => (prev - 1) as BatchWizardStep)}
                  className={`px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                >
                  Back
                </button>
              )}
              {batchWizardStep < 3 && (
                <button
                  type="button"
                  onClick={() => setBatchWizardStep((prev) => (prev + 1) as BatchWizardStep)}
                  disabled={
                    (batchWizardStep === 1 && batchEmailMode === 'generated' && !googleDomainAvailable) ||
                    (batchWizardStep === 2 && !canProceedBatchStep2)
                  }
                  className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  Next
                </button>
              )}
              {batchWizardStep === 3 && !batchResult && (
                <button
                  type="button"
                  onClick={handleBatchCreate}
                  disabled={batchSubmitting || !canProceedBatchStep2}
                  className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  {batchSubmitting ? 'Creating...' : `Create ${batchRowsWithInput.length} Employees`}
                </button>
              )}
              {batchWizardStep === 3 && batchResult && (
                <button
                  type="button"
                  onClick={() => {
                    setDraftLoaded(false);
                    setShowBatchWizardModal(false);
                    setBatchResult(null);
                  }}
                  className={`px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                >
                  Done
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Bulk Upload Modal */}
      {showBulkUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className={`w-full max-w-2xl ${t.modalBg} max-h-[90vh] overflow-hidden flex flex-col`} onClick={(e) => e.stopPropagation()}>
            <div className={`flex items-center justify-between p-6 ${t.modalHeader}`}>
              <div>
                <h3 className={`text-xl font-bold ${t.textMain} uppercase tracking-tight`}>Bulk Upload Employees</h3>
                <p className={`text-xs ${t.textMuted} mt-1`}>Upload a CSV file to add multiple employees at once</p>
              </div>
              <button
                onClick={() => {
                  setShowBulkUploadModal(false);
                  setUploadFile(null);
                  setUploadResult(null);
                }}
                className={`${t.closeBtnCls}`}
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              {!uploadResult ? (
                <div className="space-y-6">
                  {/* Download Template Button */}
                  <div className={`${t.innerEl} p-4`}>
                    <div className="flex items-start gap-3">
                      <Download className="text-emerald-600 mt-0.5" size={16} />
                      <div className="flex-1">
                        <h4 className={`text-sm font-bold ${t.textMain} uppercase tracking-wide mb-1`}>Step 1: Download Template</h4>
                        <p className={`text-xs ${t.textMuted} mb-3`}>
                          Get the CSV template with the correct format and column headers.
                        </p>
                        <button
                          onClick={handleDownloadTemplate}
                          className={`inline-flex items-center gap-2 px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                        >
                          <Download size={12} />
                          Download Template
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Upload Area */}
                  <div className={`${t.innerEl} p-4`}>
                    <div className="flex items-start gap-3 mb-4">
                      <Upload className="text-emerald-600 mt-0.5" size={16} />
                      <div className="flex-1">
                        <h4 className={`text-sm font-bold ${t.textMain} uppercase tracking-wide mb-1`}>Step 2: Upload CSV</h4>
                        <p className={`text-xs ${t.textMuted}`}>
                          Drag and drop your CSV file or click to browse.
                        </p>
                      </div>
                    </div>

                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                        isDragging ? t.uploadZoneDrag : uploadFile ? t.uploadZoneDone : t.uploadZone
                      }`}
                    >
                      {uploadFile ? (
                        <div className="space-y-3">
                          <CheckCircle className="w-10 h-10 text-emerald-600 mx-auto" />
                          <div>
                            <p className={`text-sm font-medium ${t.textMain}`}>{uploadFile.name}</p>
                            <p className={`text-xs ${t.textMuted} mt-1`}>
                              {(uploadFile.size / 1024).toFixed(2)} KB
                            </p>
                          </div>
                          <button
                            onClick={() => setUploadFile(null)}
                            className={`text-xs ${t.cancelBtn} uppercase tracking-wider`}
                          >
                            Remove File
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <Upload className={`w-10 h-10 ${t.textDim} mx-auto`} />
                          <div>
                            <p className={`text-sm font-medium ${t.textDim}`}>Drop your CSV file here</p>
                            <p className={`text-xs ${t.textMuted} mt-1`}>or</p>
                          </div>
                          <label className="inline-block">
                            <input
                              type="file"
                              accept=".csv"
                              onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                              className="hidden"
                            />
                            <span className={`inline-flex items-center gap-2 px-4 py-2 ${t.btnSecondary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors cursor-pointer`}>
                              Browse Files
                            </span>
                          </label>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Options */}
                  {uploadFile && (
                    <div className={`${t.innerEl} p-4`}>
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          id="send-invites"
                          checked={sendInvitationsOnUpload}
                          onChange={(e) => setSendInvitationsOnUpload(e.target.checked)}
                          className={`w-4 h-4 rounded ${isLight ? 'border-stone-300 bg-white' : 'border-zinc-600 bg-zinc-700'} text-emerald-600 focus:ring-emerald-500 focus:ring-offset-0`}
                        />
                        <label htmlFor="send-invites" className={`text-sm ${t.textMain} cursor-pointer`}>
                          Send invitation emails automatically
                        </label>
                      </div>
                      <p className={`text-xs ${t.textMuted} mt-2 ml-7`}>
                        Employees will receive an email to set up their account and access the portal.
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                /* Upload Results */
                <div className="space-y-4">
                  <div className={`${t.innerEl} p-6`}>
                    <div className="flex items-center gap-3 mb-4">
                      <CheckCircle className="text-emerald-600" size={24} />
                      <div>
                        <h4 className={`text-lg font-bold ${t.textMain} uppercase tracking-wide`}>Upload Complete</h4>
                        <p className={`text-xs ${t.textMuted} mt-1`}>
                          {uploadResult.created} of {uploadResult.total_rows} employees created successfully
                        </p>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-4 mt-6">
                      <div className={`${t.resultCard} p-4 rounded-xl text-center`}>
                        <div className="text-2xl font-bold text-emerald-600">{uploadResult.created}</div>
                        <div className={`text-xs ${t.textMuted} uppercase tracking-wider mt-1`}>Created</div>
                      </div>
                      <div className={`${t.resultCard} p-4 rounded-xl text-center`}>
                        <div className="text-2xl font-bold text-red-600">{uploadResult.failed}</div>
                        <div className={`text-xs ${t.textMuted} uppercase tracking-wider mt-1`}>Failed</div>
                      </div>
                      <div className={`${t.resultCard} p-4 rounded-xl text-center`}>
                        <div className={`text-2xl font-bold ${t.textDim}`}>{uploadResult.total_rows}</div>
                        <div className={`text-xs ${t.textMuted} uppercase tracking-wider mt-1`}>Total</div>
                      </div>
                    </div>
                  </div>

                  {uploadResult.errors && uploadResult.errors.length > 0 && (
                    <div className={`${t.alertError} rounded-xl p-4`}>
                      <div className="flex items-center gap-2 mb-3">
                        <AlertTriangle className={t.alertErrorText} size={16} />
                        <h5 className={`text-sm font-bold ${t.alertErrorText} uppercase tracking-wide`}>
                          Errors ({uploadResult.errors.length})
                        </h5>
                      </div>
                      <div className="space-y-2 max-h-60 overflow-y-auto">
                        {uploadResult.errors.map((err: any, idx: number) => (
                          <div key={idx} className={`${t.resultCard} p-3 rounded-lg text-xs`}>
                            <div className={`flex items-center gap-2 ${t.alertErrorText} font-medium mb-1`}>
                              <span>Row {err.row}</span>
                              {err.email && <span className={t.textFaint}>•</span>}
                              {err.email && <span className={`${t.textDim} font-mono`}>{err.email}</span>}
                            </div>
                            <p className={t.textMuted}>{err.error}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Send Invitations button — shown when auto-send was off and employees were created */}
                  {!sendInvitationsOnUpload && uploadResult.created > 0 && uploadResult.employee_ids?.length > 0 && (
                    <div className={`${t.innerEl} p-4`}>
                      {bulkInviteResult ? (
                        <div className="flex items-center gap-3">
                          <CheckCircle className="text-emerald-600" size={18} />
                          <div>
                            <p className={`text-sm ${t.textMain} font-medium`}>
                              {bulkInviteResult.sent} invitation{bulkInviteResult.sent !== 1 ? 's' : ''} sent
                            </p>
                            {bulkInviteResult.failed > 0 && (
                              <p className="text-xs text-red-600 mt-1">
                                {bulkInviteResult.failed} failed to send
                              </p>
                            )}
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between">
                          <div>
                            <p className={`text-sm ${t.textMain} font-medium`}>Send invitation emails?</p>
                            <p className={`text-xs ${t.textMuted} mt-1`}>
                              Invite {uploadResult.created} new employee{uploadResult.created !== 1 ? 's' : ''} to set up their portal accounts
                            </p>
                          </div>
                          <button
                            onClick={async () => {
                              setBulkInviting(true);
                              try {
                                const token = getAccessToken();
                                const res = await fetch(`${API_BASE}/employees/bulk-invite`, {
                                  method: 'POST',
                                  headers: {
                                    Authorization: `Bearer ${token}`,
                                    'Content-Type': 'application/json',
                                  },
                                  body: JSON.stringify(uploadResult.employee_ids),
                                });
                                if (res.ok) {
                                  const data = await res.json();
                                  setBulkInviteResult({ sent: data.sent, failed: data.failed });
                                }
                              } catch (err) {
                                console.error('Bulk invite failed:', err);
                              } finally {
                                setBulkInviting(false);
                              }
                            }}
                            disabled={bulkInviting}
                            className={`flex items-center gap-2 px-4 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50 shrink-0`}
                          >
                            {bulkInviting ? (
                              <>
                                <span className="w-3 h-3 border-2 border-zinc-50/20 border-t-zinc-50 rounded-full animate-spin" />
                                Sending...
                              </>
                            ) : (
                              <>
                                <Mail size={14} />
                                Send Invitations
                              </>
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    onClick={() => {
                      setShowBulkUploadModal(false);
                      setUploadFile(null);
                      setUploadResult(null);
                      setBulkInviteResult(null);
                    }}
                    className={`w-full px-4 py-3 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors`}
                  >
                    Done
                  </button>
                </div>
              )}
            </div>

            {!uploadResult && uploadFile && (
              <div className={`p-6 ${t.modalFooter} flex justify-end gap-3`}>
                <button
                  onClick={() => {
                    setShowBulkUploadModal(false);
                    setUploadFile(null);
                    setUploadResult(null);
                  }}
                  className={`px-4 py-2 ${t.cancelBtn} text-xs font-bold uppercase tracking-wider transition-colors`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleBulkUpload}
                  disabled={uploadLoading || !uploadFile}
                  className={`flex items-center gap-2 px-6 py-2 ${t.btnPrimary} text-xs font-bold uppercase tracking-wider rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {uploadLoading ? (
                    <>
                      <span className="w-3 h-3 border-2 border-zinc-50/20 border-t-zinc-50 rounded-full animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload size={14} />
                      Upload Employees
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
    </div>
  );
}
