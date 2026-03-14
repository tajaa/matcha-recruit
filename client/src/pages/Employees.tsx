import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAccessToken, provisioning, employees as employeesApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Plus, X, Mail, AlertTriangle, CheckCircle, UserX, Clock, ChevronRight, ChevronDown, MapPin } from 'lucide-react';
import { FeatureGuideTrigger } from '../features/feature-guides';
import { LifecycleWizard } from '../components/LifecycleWizard';
import { SearchInput } from '../components/ui/SearchInput';
import { FilterSelect } from '../components/ui/FilterSelect';
import { TabNav } from '../components/ui/TabNav';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { PageHeader } from '../components/ui/PageHeader';
import type { GoogleWorkspaceConnectionStatus } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

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

const FILTER_TABS = [
  { value: '', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'invited', label: 'Pending Invite' },
  { value: 'terminated', label: 'Terminated' },
];

const EMPLOYMENT_TYPE_OPTIONS = [
  { value: 'full_time', label: 'Full Time' },
  { value: 'part_time', label: 'Part Time' },
  { value: 'contractor', label: 'Contractor' },
  { value: 'intern', label: 'Intern' },
];

function StatusActionBadge({ employee, handleSendInvite, invitingId }: { employee: Employee, handleSendInvite: (id: string) => void, invitingId: string | null }) {
  const [mode, setMode] = useState<'view' | 'edit'>('view');
  const [selectedAction, setSelectedAction] = useState('invite');

  const base = 'inline-flex items-center gap-1 px-2 py-0.5 border rounded text-xs';

  if (employee.termination_date || employee.employment_status === 'terminated' || employee.employment_status === 'offboarded') {
    return <span data-tour="emp-status-badge" className={`${base} border-zinc-700 text-zinc-500`}><UserX size={11} /> Terminated</span>;
  }
  if (employee.user_id) {
    const status = employee.employment_status;
    if (status === 'on_leave')  return <span data-tour="emp-status-badge" className={`${base} border-zinc-600 text-zinc-400`}><Clock size={11} /> On Leave</span>;
    if (status === 'suspended') return <span data-tour="emp-status-badge" className={`${base} border-zinc-600 text-zinc-300`}><AlertTriangle size={11} /> Suspended</span>;
    if (status === 'on_notice') return <span data-tour="emp-status-badge" className={`${base} border-zinc-600 text-zinc-300`}><AlertTriangle size={11} /> On Notice</span>;
    if (status === 'furloughed') return <span data-tour="emp-status-badge" className={`${base} border-zinc-600 text-zinc-400`}><Clock size={11} /> Furloughed</span>;
    return <span data-tour="emp-status-badge" className={`${base} border-zinc-600 text-zinc-200`}><CheckCircle size={11} /> Active</span>;
  }

  const isPending = employee.invitation_status === 'pending';

  if (mode === 'view') {
    return (
      <button
        data-tour="emp-status-badge"
        onClick={(e) => { e.stopPropagation(); setMode('edit'); setSelectedAction('invite'); }}
        className={`${base} ${isPending ? 'border-zinc-500 text-zinc-200' : 'border-zinc-700 text-zinc-500'} hover:border-zinc-400`}
      >
        {isPending ? <Clock size={11} /> : <Mail size={11} />}
        {isPending ? 'Invited' : 'Not Invited'}
        <ChevronDown size={10} className="opacity-50" />
      </button>
    );
  }

  return (
    <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
      <select
        value={selectedAction}
        onChange={(e) => setSelectedAction(e.target.value)}
        className="px-2 py-0.5 text-xs rounded bg-zinc-800 text-zinc-200 border border-zinc-700 focus:outline-none"
      >
        <option value="invite">{isPending ? 'Resend Invite' : 'Send Invite'}</option>
      </select>
      <button
        onClick={() => { if (selectedAction === 'invite') handleSendInvite(employee.id); setMode('view'); }}
        disabled={invitingId === employee.id}
        className="px-2 py-0.5 text-xs rounded bg-zinc-200 text-zinc-900 hover:bg-white disabled:opacity-50"
      >
        {invitingId === employee.id ? '…' : 'Go'}
      </button>
      <button onClick={() => setMode('view')} className="text-zinc-500 hover:text-zinc-300">
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
          <div className="h-8 w-8 rounded bg-zinc-800 text-zinc-300 flex items-center justify-center text-xs font-medium">
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
          <p className="text-xs text-zinc-300 truncate">{employee.department || '\u2014'}</p>
        </div>
        <div className="xl:text-left xl:w-28">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Location</p>
          <p className="text-[10px] text-zinc-300 font-mono leading-tight">{employee.work_city ? `${employee.work_city}, ${employee.work_state}` : (employee.work_state || '\u2014')}</p>
        </div>
        <div className="xl:text-left xl:w-20">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Type</p>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider truncate">
            {employee.employment_type?.replace('_', ' ') || '\u2014'}
          </p>
        </div>
        <div className="xl:text-center xl:w-10">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">IR</p>
          {incidentCount > 0 ? (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs rounded border border-zinc-600 text-zinc-300">
              <AlertTriangle size={10} />{incidentCount}
            </span>
          ) : (
            <span className="text-xs text-zinc-600">&mdash;</span>
          )}
        </div>
        <div data-tour="emp-onboarding-col" className="xl:w-28 flex flex-col xl:items-start xl:justify-center">
          <p className="text-[9px] text-zinc-500 uppercase tracking-wider xl:hidden mb-0.5">Onboarding</p>
          {onboardingProgress[employee.id]?.has_onboarding ? (
            <div className="flex items-center gap-2">
              <div className="w-12 h-1 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-zinc-400 rounded-full transition-all"
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

  const [searchQuery, setSearchQuery] = useState('');
  const [filterDepartment, setFilterDepartment] = useState('');
  const [filterEmploymentType, setFilterEmploymentType] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [groupByLocation, setGroupByLocation] = useState(false);
  const [departments, setDepartments] = useState<string[]>([]);
  const [locations, setLocations] = useState<{ state: string; city: string | null }[]>([]);

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
        const [st, ct] = filterLocation.split('|');
        if (st) params.set('work_state', st);
        if (ct) params.set('work_city', ct);
      }
      const qs = params.toString();
      const url = `${API_BASE}/employees${qs ? `?${qs}` : ''}`;

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
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
        headers: { Authorization: `Bearer ${token}` },
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
    if (googleWorkspaceStatusLoading) return { label: 'Loading', cls: 'text-zinc-500' };
    if (!googleWorkspaceStatus || !googleWorkspaceStatus.connected || googleWorkspaceStatus.status === 'disconnected') return { label: 'Disconnected', cls: 'text-zinc-500' };
    if (googleWorkspaceStatus.status === 'error' || googleWorkspaceStatus.status === 'needs_action') return { label: 'Needs Attention', cls: 'text-zinc-300' };
    if (googleWorkspaceStatus.auto_provision_on_employee_create) return { label: 'On', cls: 'text-zinc-200' };
    return { label: 'Off', cls: 'text-zinc-500' };
  };

  const handleSendInvite = async (employeeId: string) => {
    setInvitingId(employeeId);
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${employeeId}/invite`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
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
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading directory...</div>
      </div>
    );
  }

  const googleBadge = googleAutoProvisionBadge();

  const emptyStateFor = () => {
    if (filter === 'terminated') return { title: 'No terminated employees yet', description: 'Employees will show up here after they have been marked as terminated in the system.', icon: UserX as typeof Plus, hasAction: false };
    if (filter === 'invited') return { title: 'No pending invites', description: 'Employees will show up here after you send them a portal invitation.', icon: Mail as typeof Plus, hasAction: false };
    if (filter === 'active') return { title: 'No active employees yet', description: 'Use the onboarding wizard to add your first employee, then active employees will appear here.', icon: Plus, hasAction: true };
    return { title: 'No employees found', description: 'Use the onboarding wizard to add your first employee, then they will appear here.', icon: Plus, hasAction: true };
  };

  const locationOptions = locations.map((loc) => ({
    value: loc.city ? `${loc.state}|${loc.city}` : loc.state,
    label: loc.city ? `${loc.state} \u2014 ${loc.city}` : loc.state,
  }));

  const departmentOptions = departments.map((d) => ({ value: d, label: d }));

  const hasFilters = searchQuery || filterDepartment || filterEmploymentType || filterLocation;

  return (
    <div className="-mx-4 sm:-mx-6 lg:-mx-8 -mt-20 md:-mt-6 -mb-12 px-4 sm:px-6 lg:px-8 py-8 md:pt-10 min-h-screen bg-zinc-950">
    <div className="max-w-5xl mx-auto space-y-8 animate-in fade-in duration-500">
      <PageHeader
        title={<>Employees <FeatureGuideTrigger guideId="employees" /></>}
        subtitle="Manage your team"
        afterSubtitle={
          <button
            onClick={() => navigate('/app/matcha/onboarding?tab=workspace')}
            className="mt-2 inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300"
            title="Open Google Workspace provisioning settings"
          >
            Google Auto-Provision: <span className={googleBadge.cls}>{googleBadge.label}</span>
          </button>
        }
      >
        <button
          data-tour="emp-add-hire-btn"
          onClick={() => navigate('/app/matcha/onboarding?tab=employees')}
          className="flex items-center gap-2 px-4 py-2 bg-zinc-100 text-zinc-900 hover:bg-white text-sm rounded"
        >
          <Plus size={14} />
          Add New Hire
        </button>
      </PageHeader>

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
        <div className="border border-zinc-800 px-4 py-3 rounded text-sm text-zinc-400">
          Use the Employee Lifecycle wizard above to add your first employees.
        </div>
      )}

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <div data-tour="emp-tabs">
        <TabNav
          tabs={FILTER_TABS}
          activeTab={filter}
          onTabChange={setFilter}
          className="-mx-4 px-4 sm:mx-0 sm:px-0"
        />
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search name, email, title..."
        />
        {departments.length > 0 && (
          <FilterSelect
            value={filterDepartment}
            onChange={setFilterDepartment}
            options={departmentOptions}
            placeholder="All Departments"
          />
        )}
        <FilterSelect
          value={filterEmploymentType}
          onChange={setFilterEmploymentType}
          options={EMPLOYMENT_TYPE_OPTIONS}
          placeholder="All Types"
        />
        {locations.length > 0 && (
          <FilterSelect
            value={filterLocation}
            onChange={setFilterLocation}
            options={locationOptions}
            placeholder="All Locations"
          />
        )}
        <button
          onClick={() => setGroupByLocation(!groupByLocation)}
          className={`flex items-center gap-1.5 px-3 py-2 border rounded text-sm ${groupByLocation ? 'border-zinc-500 text-zinc-200' : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'}`}
        >
          <MapPin size={13} />
          Group by location
        </button>
        {hasFilters && (
          <button
            onClick={() => { setSearchQuery(''); setFilterDepartment(''); setFilterEmploymentType(''); setFilterLocation(''); }}
            className="text-sm text-zinc-500 hover:text-zinc-300"
          >
            Clear
          </button>
        )}
      </div>

      {employees.length === 0 ? (
        (() => {
          const es = emptyStateFor();
          return (
            <EmptyState
              icon={es.icon}
              title={es.title}
              description={es.description}
              actionLabel={es.hasAction ? 'Onboard New Employee' : undefined}
              onAction={es.hasAction ? () => navigate('/app/matcha/onboarding?tab=employees') : undefined}
              actionIcon={es.hasAction ? Plus : undefined}
            />
          );
        })()
      ) : (
        <div data-tour="emp-list" className="border border-zinc-800 rounded overflow-x-auto">
          <div className="min-w-[1024px]">
           {!groupByLocation && (
             <div className="hidden xl:flex items-center gap-6 py-3 px-6 text-xs text-zinc-500 border-b border-zinc-800">
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
                      : city ? `${state} \u2014 ${city}` : state;
                    return (
                      <details key={key} open className="group/loc">
                        <summary className="flex items-center gap-2 px-6 py-3 cursor-pointer bg-zinc-900 text-zinc-400 text-xs border-b border-zinc-800">
                          <ChevronDown size={14} className="transition-transform group-open/loc:rotate-0 -rotate-90" />
                          <MapPin size={12} />
                          {label}
                          <span className="text-zinc-600 font-mono ml-1">({emps.length})</span>
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
            <EmployeeRow key={employee.id} employee={employee} navigate={navigate} onboardingProgress={onboardingProgress} handleSendInvite={handleSendInvite} invitingId={invitingId} incidentCount={incidentCounts[employee.id] || 0} />
          ))}
          </div>
          )}
          </div>
        </div>
      )}
    </div>
    </div>
  );
}
