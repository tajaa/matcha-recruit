import { useState, useEffect, useRef } from 'react';
import { getAccessToken, provisioning } from '../api/client';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

type StepStatus = 'pending' | 'running' | 'success' | 'error' | 'skipped';

interface AgentStep {
  id: string;
  label: string;
  status: StepStatus;
  detail?: string;
  duration?: number;
}

interface Props {
  employeeId: string;
  employeeName: string;
  companyName: string;
  workEmail: string;
  personalEmail: string;
  googleEnabled: boolean;
  onAddAnother: () => void;
  onViewProfile: (id: string) => void;
  onClose: () => void;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const STEP_MIN_DISPLAY_MS = 600;

export default function OnboardingAgentConsole({
  employeeId,
  employeeName,
  companyName,
  workEmail,
  personalEmail,
  googleEnabled,
  onAddAnother,
  onViewProfile,
  onClose,
}: Props) {
  const [steps, setSteps] = useState<AgentStep[]>([
    { id: 'employee_created', label: 'Employee record created', status: 'success', duration: 100 },
    { id: 'google_check', label: 'Google Workspace configured', status: 'pending' },
    { id: 'google_provision', label: `Provisioning ${workEmail || 'work account'}…`, status: 'pending' },
    { id: 'send_invite', label: 'Send invitation email', status: 'pending' },
    { id: 'assign_templates', label: 'Assign onboarding checklist', status: 'pending' },
  ]);
  const [done, setDone] = useState(false);
  const [taskCount, setTaskCount] = useState<number | null>(null);
  const [inviteResult, setInviteResult] = useState<'sent' | 'error' | null>(null);
  const [googleResult, setGoogleResult] = useState<'success' | 'error' | 'skipped' | null>(null);
  const [visibleSteps, setVisibleSteps] = useState<Set<string>>(new Set(['employee_created']));
  const hasRun = useRef(false);

  const updateStep = (id: string, patch: Partial<AgentStep>) => {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  };

  const revealStep = (id: string) => {
    setVisibleSteps((prev) => new Set([...prev, id]));
  };

  useEffect(() => {
    if (hasRun.current) return;
    hasRun.current = true;

    const run = async () => {
      const token = getAccessToken();

      // Step 2: google_check
      revealStep('google_check');
      await sleep(300);
      if (googleEnabled) {
        updateStep('google_check', { status: 'success', duration: 0 });
      } else {
        updateStep('google_check', { status: 'skipped' });
      }
      await sleep(STEP_MIN_DISPLAY_MS);

      // Step 3: google_provision
      revealStep('google_provision');
      await sleep(200);
      if (googleEnabled) {
        updateStep('google_provision', { status: 'running' });
        const startTime = Date.now();
        let success = false;
        let errorDetail: string | undefined;

        try {
          let attempts = 0;
          while (attempts < 15) {
            const status = await provisioning.getEmployeeGoogleWorkspaceStatus(employeeId);
            const latestRun = status.runs?.[0];
            if (!latestRun || latestRun.status === 'pending' || latestRun.status === 'running') {
              await sleep(2000);
              attempts++;
              continue;
            }
            if (latestRun.status === 'completed') {
              success = true;
              break;
            }
            if (latestRun.status === 'failed' || latestRun.status === 'needs_action') {
              errorDetail = latestRun.last_error || latestRun.status;
              break;
            }
            await sleep(2000);
            attempts++;
          }
        } catch {
          errorDetail = 'Could not check provisioning status';
        }

        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, STEP_MIN_DISPLAY_MS - elapsed);
        await sleep(remaining);

        if (success) {
          updateStep('google_provision', {
            status: 'success',
            detail: workEmail,
            duration: Date.now() - startTime,
          });
          setGoogleResult('success');
        } else {
          updateStep('google_provision', {
            status: 'error',
            detail: errorDetail || 'Provisioning incomplete — check Workspace settings',
            duration: Date.now() - startTime,
          });
          setGoogleResult('error');
        }
      } else {
        updateStep('google_provision', { status: 'skipped' });
        setGoogleResult('skipped');
      }
      await sleep(STEP_MIN_DISPLAY_MS);

      // Step 4: send_invite
      revealStep('send_invite');
      await sleep(200);
      updateStep('send_invite', { status: 'running' });
      const inviteStart = Date.now();
      try {
        const res = await fetch(`${API_BASE}/employees/${employeeId}/invite`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
        const elapsed = Date.now() - inviteStart;
        await sleep(Math.max(0, STEP_MIN_DISPLAY_MS - elapsed));
        if (res.ok) {
          updateStep('send_invite', {
            status: 'success',
            detail: personalEmail ? `Sent to ${personalEmail}` : 'Invitation sent',
            duration: Date.now() - inviteStart,
          });
          setInviteResult('sent');
        } else {
          const data = await res.json().catch(() => ({}));
          updateStep('send_invite', {
            status: 'error',
            detail: data.detail || 'Failed to send invitation',
            duration: Date.now() - inviteStart,
          });
          setInviteResult('error');
        }
      } catch {
        const elapsed = Date.now() - inviteStart;
        await sleep(Math.max(0, STEP_MIN_DISPLAY_MS - elapsed));
        updateStep('send_invite', {
          status: 'error',
          detail: 'Network error — invite not sent',
          duration: Date.now() - inviteStart,
        });
        setInviteResult('error');
      }
      await sleep(STEP_MIN_DISPLAY_MS);

      // Step 5: assign_templates
      revealStep('assign_templates');
      await sleep(200);
      updateStep('assign_templates', { status: 'running' });
      const templatesStart = Date.now();
      try {
        const res = await fetch(`${API_BASE}/employees/${employeeId}/onboarding/assign-all`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
        const elapsed = Date.now() - templatesStart;
        await sleep(Math.max(0, STEP_MIN_DISPLAY_MS - elapsed));
        if (res.ok) {
          const data = await res.json().catch(() => ({}));
          const count = data.assigned ?? data.tasks_assigned ?? data.count ?? null;
          setTaskCount(typeof count === 'number' ? count : null);
          updateStep('assign_templates', {
            status: 'success',
            detail: typeof count === 'number' ? `${count} task${count !== 1 ? 's' : ''} assigned` : 'Checklist assigned',
            duration: Date.now() - templatesStart,
          });
        } else {
          const data = await res.json().catch(() => ({}));
          updateStep('assign_templates', {
            status: 'error',
            detail: data.detail || 'No templates to assign',
            duration: Date.now() - templatesStart,
          });
        }
      } catch {
        const elapsed = Date.now() - templatesStart;
        await sleep(Math.max(0, STEP_MIN_DISPLAY_MS - elapsed));
        updateStep('assign_templates', {
          status: 'error',
          detail: 'Network error — templates not assigned',
          duration: Date.now() - templatesStart,
        });
      }

      await sleep(400);
      setDone(true);
    };

    run();
  }, []);

  const totalSteps = steps.filter((s) => s.status !== 'skipped').length;
  const completedSteps = steps.filter(
    (s) => s.status === 'success' || s.status === 'error' || s.status === 'skipped'
  ).length;
  const progressPct = done ? 100 : Math.round((completedSteps / Math.max(totalSteps, 1)) * 100);

  const stepIcon = (status: StepStatus) => {
    if (status === 'success') return <span className="text-emerald-400 font-bold">✓</span>;
    if (status === 'error') return <span className="text-red-400 font-bold">✗</span>;
    if (status === 'skipped') return <span className="text-zinc-700">—</span>;
    if (status === 'running') return <Spinner />;
    return <span className="text-zinc-600">○</span>;
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const firstName = employeeName.split(' ')[0] || employeeName;

  // Summary info for completion card
  const summaryRows: { label: string; value: string }[] = [];
  if (googleEnabled && googleResult === 'success' && workEmail) {
    summaryRows.push({ label: 'Google account', value: workEmail });
  }
  if (inviteResult === 'sent') {
    summaryRows.push({ label: 'Invitation', value: personalEmail ? `sent to ${personalEmail}` : 'sent' });
  }
  if (taskCount !== null && taskCount > 0) {
    summaryRows.push({ label: 'Checklist', value: `${taskCount} task${taskCount !== 1 ? 's' : ''} assigned` });
  } else {
    const assignStep = steps.find((s) => s.id === 'assign_templates');
    if (assignStep?.detail && assignStep.status === 'success') {
      summaryRows.push({ label: 'Checklist', value: assignStep.detail });
    }
  }

  return (
    <div className="bg-zinc-950 rounded-sm overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-4 py-3 bg-black border-b border-zinc-800">
        <span className="text-emerald-400 font-mono text-[10px] uppercase tracking-widest font-bold">◈ Matcha Agent</span>
        <span className="text-zinc-600 font-mono text-[10px]">—</span>
        <span className="text-zinc-400 font-mono text-[10px] truncate">
          Onboarding <span className="text-white">{employeeName}</span>
          {companyName ? <> → <span className="text-zinc-300">{companyName}</span></> : null}
        </span>
      </div>

      {done ? (
        /* ── Completion state ── */
        <div className="p-6 space-y-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-emerald-400 text-lg">✦</span>
              <h3 className="text-white font-bold text-base uppercase tracking-tight">Employee Onboarded</h3>
            </div>
            <p className="text-zinc-400 text-sm font-mono">{firstName} is fully set up</p>
          </div>

          {summaryRows.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-sm p-4 space-y-2">
              {summaryRows.map((row) => (
                <div key={row.label} className="flex gap-4 font-mono text-xs">
                  <span className="text-zinc-500 w-28 shrink-0">{row.label}</span>
                  <span className="text-white">{row.value}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-2 pt-1 flex-wrap">
            <button
              onClick={() => onViewProfile(employeeId)}
              className="px-4 py-2 bg-white text-black hover:bg-zinc-200 text-xs font-bold uppercase tracking-wider transition-colors"
            >
              View Profile
            </button>
            <button
              onClick={onAddAnother}
              className="px-4 py-2 border border-white/20 text-zinc-300 hover:text-white hover:border-white/40 text-xs font-bold uppercase tracking-wider transition-colors"
            >
              Add Another
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 text-zinc-500 hover:text-zinc-300 text-xs font-bold uppercase tracking-wider transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      ) : (
        /* ── Running state ── */
        <div className="p-5 space-y-4">
          {/* Progress bar */}
          <div>
            <div className="flex justify-between mb-1.5">
              <span className="font-mono text-[10px] text-zinc-500 uppercase tracking-widest">Running</span>
              <span className="font-mono text-[10px] text-zinc-500">{progressPct}%</span>
            </div>
            <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-500 transition-all duration-700 ease-out rounded-full"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Step list */}
          <div className="space-y-0">
            {steps.map((step) => {
              const visible = visibleSteps.has(step.id);
              return (
                <div
                  key={step.id}
                  className={`transition-all duration-300 ${
                    visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-1'
                  }`}
                >
                  <div className="flex items-center gap-3 py-2">
                    <span className="w-4 text-center shrink-0 font-mono text-sm leading-none">
                      {stepIcon(step.status)}
                    </span>
                    <span
                      className={`font-mono text-xs flex-1 ${
                        step.status === 'running'
                          ? 'text-white animate-pulse'
                          : step.status === 'success'
                          ? 'text-zinc-200'
                          : step.status === 'error'
                          ? 'text-red-400'
                          : step.status === 'skipped'
                          ? 'text-zinc-700'
                          : 'text-zinc-600'
                      }`}
                    >
                      {step.label}
                    </span>
                    {step.duration !== undefined && step.status !== 'skipped' && (
                      <span className="font-mono text-[10px] text-zinc-600 shrink-0">
                        {formatDuration(step.duration)}
                      </span>
                    )}
                  </div>
                  {step.detail && (step.status === 'success' || step.status === 'error') && (
                    <div className={`ml-7 pb-1 font-mono text-[10px] ${step.status === 'error' ? 'text-red-500/70' : 'text-zinc-500'}`}>
                      {step.detail}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <span className="inline-block w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
  );
}
