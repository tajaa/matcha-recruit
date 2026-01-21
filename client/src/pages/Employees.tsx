import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAccessToken } from '../api/client';
import { Plus, X, Search, Mail, AlertTriangle, CheckCircle, UserX, Clock, ChevronRight, HelpCircle, ChevronDown, Settings, ClipboardCheck } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001/api';

interface Employee {
  id: string;
  email: string;
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
  created_at: string;
}

interface NewEmployee {
  email: string;
  first_name: string;
  last_name: string;
  work_state: string;
  employment_type: string;
  start_date: string;
}

interface OnboardingProgress {
  employee_id: string;
  total: number;
  completed: number;
  pending: number;
  has_onboarding: boolean;
}

export default function Employees() {
  const navigate = useNavigate();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [filter, setFilter] = useState<string>('');
  const [newEmployee, setNewEmployee] = useState<NewEmployee>({
    email: '',
    first_name: '',
    last_name: '',
    work_state: '',
    employment_type: 'full_time',
    start_date: new Date().toISOString().split('T')[0],
  });
  const [submitting, setSubmitting] = useState(false);
  const [invitingId, setInvitingId] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [onboardingProgress, setOnboardingProgress] = useState<Record<string, OnboardingProgress>>({});
  const [showOnboardingPrompt, setShowOnboardingPrompt] = useState(false);
  const [newEmployeeId, setNewEmployeeId] = useState<string | null>(null);
  const [newEmployeeName, setNewEmployeeName] = useState<string>('');
  const [showSettingsDropdown, setShowSettingsDropdown] = useState(false);
  const [assigningOnboarding, setAssigningOnboarding] = useState(false);

  const fetchEmployees = async () => {
    try {
      const token = getAccessToken();
      const url = filter
        ? `${API_BASE}/employees?status=${filter}`
        : `${API_BASE}/employees`;

      const response = await fetch(url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) throw new Error('Failed to fetch employees');

      const data = await response.json();
      setEmployees(data);
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

  useEffect(() => {
    fetchEmployees();
    fetchOnboardingProgress();
  }, [filter]);

  const handleAddEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newEmployee),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to add employee');
      }

      const createdEmployee = await response.json();

      setShowAddModal(false);
      setNewEmployeeId(createdEmployee.id);
      setNewEmployeeName(`${newEmployee.first_name} ${newEmployee.last_name}`);
      setShowOnboardingPrompt(true);

      setNewEmployee({
        email: '',
        first_name: '',
        last_name: '',
        work_state: '',
        employment_type: 'full_time',
        start_date: new Date().toISOString().split('T')[0],
      });
      fetchEmployees();
      fetchOnboardingProgress();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAssignOnboarding = async () => {
    if (!newEmployeeId) return;

    setAssigningOnboarding(true);
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_BASE}/employees/${newEmployeeId}/onboarding/assign-all`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to assign onboarding');
      }

      setShowOnboardingPrompt(false);
      navigate(`/app/matcha/employees/${newEmployeeId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setShowOnboardingPrompt(false);
    } finally {
      setAssigningOnboarding(false);
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
        const data = await response.json();
        throw new Error(data.detail || 'Failed to send invitation');
      }

      fetchEmployees();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setInvitingId(null);
    }
  };

  const getStatusBadge = (employee: Employee) => {
    if (employee.termination_date) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-zinc-800 text-zinc-400 border border-zinc-700">
          <UserX size={10} /> Terminated
        </span>
      );
    }
    if (employee.user_id) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-emerald-900/30 text-emerald-400 border border-emerald-500/20">
          <CheckCircle size={10} /> Active
        </span>
      );
    }
    if (employee.invitation_status === 'pending') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-amber-900/30 text-amber-400 border border-amber-500/20">
          <Clock size={10} /> Invited
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-bold bg-zinc-800 text-zinc-500 border border-zinc-700">
        <Mail size={10} /> Not Invited
      </span>
    );
  };

  const US_STATES = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading directory...</div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Directory</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Manage personnel and access rights
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowHelp(!showHelp)}
            className={`flex items-center gap-2 px-4 py-2 border text-xs font-bold uppercase tracking-wider transition-colors ${
              showHelp
                ? 'border-white/30 text-white bg-zinc-800'
                : 'border-white/10 text-zinc-400 hover:text-white hover:border-white/20'
            }`}
          >
            <HelpCircle size={14} />
            Help
            <ChevronDown size={12} className={`transition-transform ${showHelp ? 'rotate-180' : ''}`} />
          </button>
          <div className="relative">
            <button
              onClick={() => setShowSettingsDropdown(!showSettingsDropdown)}
              className={`flex items-center gap-2 px-4 py-2 border text-xs font-bold uppercase tracking-wider transition-colors ${
                showSettingsDropdown
                  ? 'border-white/30 text-white bg-zinc-800'
                  : 'border-white/10 text-zinc-400 hover:text-white hover:border-white/20'
              }`}
            >
              <Settings size={14} />
            </button>
            {showSettingsDropdown && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowSettingsDropdown(false)}
                />
                <div className="absolute right-0 mt-2 w-56 bg-zinc-900 border border-white/10 shadow-xl z-20">
                  <button
                    onClick={() => {
                      setShowSettingsDropdown(false);
                      navigate('/app/matcha/onboarding-templates');
                    }}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left text-xs font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors"
                  >
                    <ClipboardCheck size={14} />
                    Onboarding Templates
                  </button>
                </div>
              </>
            )}
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
          >
            <Plus size={14} />
            Add Employee
          </button>
        </div>
      </div>

      {/* Help Panel */}
      {showHelp && (
        <div className="bg-zinc-900/50 border border-white/10 rounded-sm overflow-hidden">
          <div className="p-6 space-y-6">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">Getting Started with Employee Management</h3>
                <p className="text-xs text-zinc-500 mt-1">Learn how to manage your team and onboarding tasks</p>
              </div>
              <button onClick={() => setShowHelp(false)} className="text-zinc-500 hover:text-white">
                <X size={16} />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 text-xs font-bold">1</div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider">Add Employees</h4>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed pl-8">
                  Click "Add Employee" to create a new team member record. Enter their name, email, work state, and start date. The employee won't have system access until you send an invitation.
                </p>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 text-xs font-bold">2</div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider">Send Invitations</h4>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed pl-8">
                  Click "Send Invite" to email the employee a link to create their account and access the employee portal. You can resend invitations if needed.
                </p>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 text-xs font-bold">3</div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider">View Employee Details</h4>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed pl-8">
                  Click on any employee row to view their full profile, including personal info, employment details, and their onboarding checklist progress.
                </p>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-400 text-xs font-bold">4</div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider">Manage Onboarding</h4>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed pl-8">
                  In the employee detail view, assign onboarding tasks from your templates. Track completion, mark tasks done, and add notes. Tasks can be assigned to the employee or HR/manager.
                </p>
              </div>
            </div>

            <div className="border-t border-white/10 pt-4">
              <p className="text-xs text-zinc-500">
                <span className="text-zinc-400 font-medium">Tip:</span> Set up your onboarding task templates via the{' '}
                <button
                  onClick={() => navigate('/app/matcha/onboarding-templates')}
                  className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2"
                >
                  Settings (gear icon) → Onboarding Templates
                </button>{' '}
                to streamline new employee setup.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
             <AlertTriangle className="text-red-400" size={16} />
             <p className="text-sm text-red-400 font-mono">{error}</p>
          </div>
          <button
            onClick={() => setError(null)}
            className="text-xs text-red-400 hover:text-red-300 uppercase tracking-wider font-bold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filter tabs */}
      <div className="border-b border-white/10">
        <nav className="-mb-px flex space-x-8">
          {[
            { value: '', label: 'All' },
            { value: 'active', label: 'Active' },
            { value: 'invited', label: 'Pending Invite' },
            { value: 'terminated', label: 'Terminated' },
          ].map((tab) => (
            <button
              key={tab.value}
              onClick={() => setFilter(tab.value)}
              className={`pb-4 px-1 border-b-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                filter === tab.value
                  ? 'border-white text-white'
                  : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Employee list */}
      {employees.length === 0 ? (
        <div className="text-center py-24 border border-dashed border-white/10 bg-white/5">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center">
             <Search size={24} className="text-zinc-600" />
          </div>
          <h3 className="text-white text-sm font-bold mb-1 uppercase tracking-wide">No employees found</h3>
          <p className="text-zinc-500 text-xs mb-6 font-mono">Get started by adding your first team member.</p>
          <button
            onClick={() => setShowAddModal(true)}
            className="text-white text-xs font-bold hover:text-zinc-300 uppercase tracking-wider underline underline-offset-4"
          >
            Add Employee
          </button>
        </div>
      ) : (
        <div className="space-y-px bg-white/10 border border-white/10">
           {/* Table Header */}
           <div className="hidden md:flex items-center gap-4 py-3 px-6 bg-zinc-950 text-[10px] text-zinc-500 uppercase tracking-widest border-b border-white/10">
              <div className="flex-1">Name / Email</div>
              <div className="w-32 text-right">Work State</div>
              <div className="w-32 text-right">Type</div>
              <div className="w-36 text-right">Onboarding</div>
              <div className="w-32 text-right">Status</div>
              <div className="w-32"></div>
           </div>

          {employees.map((employee) => (
            <div
              key={employee.id}
              onClick={() => navigate(`/app/matcha/employees/${employee.id}`)}
              className="group bg-zinc-950 hover:bg-zinc-900 transition-colors p-4 md:px-6 flex flex-col md:flex-row md:items-center gap-4 cursor-pointer"
            >
              <div className="flex items-center min-w-0 flex-1">
                <div className="flex-shrink-0">
                  <div className="h-10 w-10 rounded bg-zinc-800 border border-zinc-700 flex items-center justify-center text-white font-bold text-xs">
                    {employee.first_name[0]}{employee.last_name[0]}
                  </div>
                </div>
                <div className="ml-4 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-bold text-white truncate group-hover:text-zinc-200">
                      {employee.first_name} {employee.last_name}
                    </p>
                  </div>
                  <p className="text-xs text-zinc-500 font-mono truncate">{employee.email}</p>
                </div>
              </div>

              <div className="flex items-center justify-between md:justify-end gap-4 md:gap-8 w-full md:w-auto">
                 <div className="text-right">
                    <p className="text-xs text-zinc-400 font-mono">{employee.work_state || '—'}</p>
                 </div>
                 <div className="text-right w-24">
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider">
                      {employee.employment_type?.replace('_', ' ') || '—'}
                    </p>
                 </div>
                 <div className="w-36 flex justify-end">
                    {onboardingProgress[employee.id]?.has_onboarding ? (
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 rounded-full transition-all"
                            style={{
                              width: `${(onboardingProgress[employee.id].completed / onboardingProgress[employee.id].total) * 100}%`,
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-zinc-400 font-mono">
                          {onboardingProgress[employee.id].completed}/{onboardingProgress[employee.id].total}
                        </span>
                      </div>
                    ) : (
                      <span className="text-[10px] text-zinc-600 uppercase tracking-wider">Not started</span>
                    )}
                 </div>
                 <div className="flex justify-end w-32">
                    {getStatusBadge(employee)}
                 </div>

                 <div className="w-32 flex justify-end">
                    {!employee.user_id && !employee.termination_date && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleSendInvite(employee.id); }}
                        disabled={invitingId === employee.id}
                        className="inline-flex items-center px-3 py-1.5 border border-white/10 text-[10px] font-bold uppercase tracking-wider rounded text-zinc-300 hover:text-white hover:border-white/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-zinc-900"
                      >
                        {invitingId === employee.id ? (
                          <span className="animate-pulse">Sending...</span>
                        ) : employee.invitation_status === 'pending' ? (
                          'Resend Invite'
                        ) : (
                          'Send Invite'
                        )}
                      </button>
                    )}
                 </div>
                 <div className="w-8 flex justify-end">
                    <ChevronRight size={16} className="text-zinc-600 group-hover:text-zinc-400" />
                 </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Employee Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm flex flex-col" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between p-6 border-b border-white/10">
                  <h3 className="text-xl font-bold text-white uppercase tracking-tight">Add Personnel</h3>
                  <button 
                    onClick={() => setShowAddModal(false)}
                    className="text-zinc-500 hover:text-white transition-colors"
                  >
                    <X size={20} />
                  </button>
              </div>

              <form onSubmit={handleAddEmployee} className="flex-1 overflow-y-auto p-8">
                  <div className="space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                          First Name <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          required
                          value={newEmployee.first_name}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, first_name: e.target.value })
                          }
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                          Last Name <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          required
                          value={newEmployee.last_name}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, last_name: e.target.value })
                          }
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                        Email <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="email"
                        required
                        value={newEmployee.email}
                        onChange={(e) =>
                          setNewEmployee({ ...newEmployee, email: e.target.value })
                        }
                        className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors placeholder-zinc-700"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                          Work State
                        </label>
                        <select
                          value={newEmployee.work_state}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, work_state: e.target.value })
                          }
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors"
                        >
                          <option value="">Select state</option>
                          {US_STATES.map((state) => (
                            <option key={state} value={state}>
                              {state}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                          Employment Type
                        </label>
                        <select
                          value={newEmployee.employment_type}
                          onChange={(e) =>
                            setNewEmployee({ ...newEmployee, employment_type: e.target.value })
                          }
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors"
                        >
                          <option value="full_time">Full Time</option>
                          <option value="part_time">Part Time</option>
                          <option value="contractor">Contractor</option>
                          <option value="intern">Intern</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
                        Start Date
                      </label>
                      <input
                        type="date"
                        value={newEmployee.start_date}
                        onChange={(e) =>
                          setNewEmployee({ ...newEmployee, start_date: e.target.value })
                        }
                        className="w-full px-3 py-2 bg-zinc-900 border border-zinc-800 text-white text-sm focus:outline-none focus:border-white/20 transition-colors [color-scheme:dark]"
                      />
                    </div>
                  </div>

                  <div className="mt-8 flex justify-end gap-3 pt-6 border-t border-white/10">
                    <button
                      type="button"
                      onClick={() => setShowAddModal(false)}
                      className="px-4 py-2 text-zinc-500 hover:text-white text-xs font-bold uppercase tracking-wider transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={submitting}
                      className="px-6 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {submitting ? 'Adding...' : 'Add Employee'}
                    </button>
                  </div>
              </form>
            </div>
        </div>
      )}

      {/* Onboarding Prompt Modal */}
      {showOnboardingPrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 shadow-2xl rounded-sm" onClick={(e) => e.stopPropagation()}>
            <div className="p-6 border-b border-white/10">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-full bg-emerald-500/20 flex items-center justify-center">
                  <CheckCircle className="w-5 h-5 text-emerald-400" />
                </div>
                <h3 className="text-xl font-bold text-white uppercase tracking-tight">Employee Added</h3>
              </div>
              <p className="text-sm text-zinc-400 mt-3">
                <span className="text-white font-medium">{newEmployeeName}</span> has been added to your directory.
              </p>
            </div>

            <div className="p-6">
              <p className="text-xs text-zinc-500 uppercase tracking-wider mb-4">
                Would you like to assign the onboarding checklist?
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => {
                    setShowOnboardingPrompt(false);
                    setNewEmployeeId(null);
                  }}
                  className="flex-1 px-4 py-3 border border-white/10 text-zinc-400 hover:text-white hover:border-white/20 text-xs font-bold uppercase tracking-wider transition-colors"
                >
                  Skip for Now
                </button>
                <button
                  onClick={handleAssignOnboarding}
                  disabled={assigningOnboarding}
                  className="flex-1 px-4 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {assigningOnboarding ? (
                    <span className="animate-pulse">Assigning...</span>
                  ) : (
                    <>
                      <ClipboardCheck size={14} />
                      Assign Checklist
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}