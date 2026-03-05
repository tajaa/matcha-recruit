import { useState, useEffect } from 'react';
import { onboarding } from '../api/client';
import type { OnboardingNotificationSettings as Settings } from '../api/client';
import { X } from 'lucide-react';
import { useIsLightMode } from '../hooks/useIsLightMode';

const LT = {
  card: 'bg-stone-100 rounded-2xl',
  cardLight: 'bg-stone-100 rounded-2xl',
  cardDark: 'bg-zinc-900 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-800',
  cardDarkGhost: 'text-zinc-800',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  border: 'border-stone-200',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:outline-none focus:border-stone-400',
  numberInput: 'w-20 bg-white border border-stone-300 text-xs text-zinc-900 px-3 py-2 text-center rounded-xl focus:outline-none focus:border-stone-400',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  label: 'text-stone-500',
  pill: 'border border-stone-200 bg-stone-200 text-stone-600',
  pillClose: 'text-stone-400 hover:text-zinc-900',
  alertError: 'border border-red-300 bg-red-50 text-red-700',
  alertSuccess: 'border border-emerald-300 bg-emerald-50 text-emerald-700',
} as const;

const DK = {
  card: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardLight: 'bg-zinc-900/50 border border-white/10 rounded-2xl',
  cardDark: 'bg-zinc-800 rounded-2xl',
  cardDarkHover: 'hover:bg-zinc-700',
  cardDarkGhost: 'text-zinc-700',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  border: 'border-white/10',
  input: 'bg-zinc-900 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:outline-none focus:border-white/20',
  numberInput: 'w-20 bg-zinc-900 border border-white/10 text-xs text-zinc-200 px-3 py-2 text-center rounded-xl focus:outline-none focus:border-white/30',
  btnPrimary: 'bg-white text-black hover:bg-zinc-200',
  label: 'text-zinc-500',
  pill: 'border border-white/10 bg-zinc-800 text-zinc-300',
  pillClose: 'text-zinc-500 hover:text-white',
  alertError: 'border border-red-500/30 bg-red-950/20 text-red-300',
  alertSuccess: 'border border-emerald-500/30 bg-emerald-950/20 text-emerald-300',
} as const;

const DEFAULTS: Settings = {
  email_enabled: true,
  hr_escalation_emails: [],
  reminder_days_before_due: 2,
  escalate_to_manager_after_days: 3,
  escalate_to_hr_after_days: 5,
  timezone: 'America/New_York',
  auto_send_invitation: false,
};

export default function OnboardingNotificationSettings() {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [emailInput, setEmailInput] = useState('');

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const data = await onboarding.getNotificationSettings();
        if (mounted) setSettings(data);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load settings');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    load();
    return () => { mounted = false; };
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const data = await onboarding.updateNotificationSettings(settings);
      setSettings(data);
      setSuccess('Settings saved.');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const addEmail = () => {
    const email = emailInput.trim().toLowerCase();
    if (!email) return;
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Invalid email address');
      return;
    }
    if (settings.hr_escalation_emails.includes(email)) {
      setError('Email already added');
      return;
    }
    setError('');
    setSettings((s) => ({ ...s, hr_escalation_emails: [...s.hr_escalation_emails, email] }));
    setEmailInput('');
  };

  const removeEmail = (email: string) => {
    setSettings((s) => ({
      ...s,
      hr_escalation_emails: s.hr_escalation_emails.filter((e) => e !== email),
    }));
  };

  if (loading) {
    return (
      <p className={`text-xs ${t.textMuted} font-mono uppercase tracking-wider animate-pulse py-8 text-center`}>
        Loading notification settings...
      </p>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {error && (
        <div className={`${t.alertError} px-4 py-3 text-xs rounded-xl`}>
          {error}
        </div>
      )}
      {success && (
        <div className={`${t.alertSuccess} px-4 py-3 text-xs rounded-xl`}>
          {success}
        </div>
      )}

      {/* Auto-send invitation toggle */}
      <div className={`${t.card} p-5 space-y-4`}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className={`text-xs font-bold uppercase tracking-widest ${t.textMain}`}>Auto-Send Invitation</h3>
            <p className={`text-[10px] ${t.textMuted} mt-1`}>
              Automatically send portal invitation email to new employees — like auto-provisioning for Google Workspace and Slack.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setSettings((s) => ({ ...s, auto_send_invitation: !s.auto_send_invitation }))}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border transition-colors ${
              settings.auto_send_invitation
                ? 'bg-emerald-600 border-emerald-500/50'
                : `${isLight ? 'bg-stone-300 border-stone-300' : 'bg-zinc-700 border-zinc-600'}`
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                settings.auto_send_invitation ? 'translate-x-4' : 'translate-x-0.5'
              } mt-[1px]`}
            />
          </button>
        </div>
      </div>

      {/* Email notifications toggle */}
      <div className={`${t.card} p-5 space-y-4`}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className={`text-xs font-bold uppercase tracking-widest ${t.textMain}`}>Email Notifications</h3>
            <p className={`text-[10px] ${t.textMuted} mt-1`}>
              Send email reminders and escalation alerts for onboarding tasks.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setSettings((s) => ({ ...s, email_enabled: !s.email_enabled }))}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border transition-colors ${
              settings.email_enabled
                ? 'bg-emerald-600 border-emerald-500/50'
                : `${isLight ? 'bg-stone-300 border-stone-300' : 'bg-zinc-700 border-zinc-600'}`
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                settings.email_enabled ? 'translate-x-4' : 'translate-x-0.5'
              } mt-[1px]`}
            />
          </button>
        </div>
      </div>

      {/* HR Escalation Emails */}
      <div className={`${t.card} p-5 space-y-4`}>
        <div>
          <h3 className={`text-xs font-bold uppercase tracking-widest ${t.textMain}`}>HR Escalation Emails</h3>
          <p className={`text-[10px] ${t.textMuted} mt-1`}>
            These addresses receive alerts when tasks are escalated to HR.
          </p>
        </div>

        <div className="flex gap-2">
          <input
            type="email"
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addEmail(); } }}
            placeholder="hr@company.com"
            className={`flex-1 ${t.input} text-xs px-3 py-2`}
          />
          <button
            type="button"
            onClick={addEmail}
            className={`px-4 py-2 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl`}
          >
            Add
          </button>
        </div>

        {settings.hr_escalation_emails.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {settings.hr_escalation_emails.map((email) => (
              <span
                key={email}
                className={`inline-flex items-center gap-1.5 ${t.pill} px-2.5 py-1 text-[11px] rounded-lg`}
              >
                {email}
                <button
                  type="button"
                  onClick={() => removeEmail(email)}
                  className={t.pillClose}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Timing Settings */}
      <div className={`${t.card} p-5 space-y-5`}>
        <div>
          <h3 className={`text-xs font-bold uppercase tracking-widest ${t.textMain}`}>Timing</h3>
          <p className={`text-[10px] ${t.textMuted} mt-1`}>
            Configure when reminders and escalations are triggered.
          </p>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <label className={`text-[11px] ${t.textFaint}`}>Remind before due date (days)</label>
            <input
              type="number"
              min={1}
              max={7}
              value={settings.reminder_days_before_due}
              onChange={(e) =>
                setSettings((s) => ({
                  ...s,
                  reminder_days_before_due: Math.max(1, Math.min(7, parseInt(e.target.value) || 1)),
                }))
              }
              className={t.numberInput}
            />
          </div>

          <div className="flex items-center justify-between gap-4">
            <label className={`text-[11px] ${t.textFaint}`}>Escalate to manager after (days overdue)</label>
            <input
              type="number"
              min={1}
              max={30}
              value={settings.escalate_to_manager_after_days}
              onChange={(e) =>
                setSettings((s) => ({
                  ...s,
                  escalate_to_manager_after_days: Math.max(1, parseInt(e.target.value) || 1),
                }))
              }
              className={t.numberInput}
            />
          </div>

          <div className="flex items-center justify-between gap-4">
            <label className={`text-[11px] ${t.textFaint}`}>Escalate to HR after (days overdue)</label>
            <input
              type="number"
              min={1}
              max={30}
              value={settings.escalate_to_hr_after_days}
              onChange={(e) =>
                setSettings((s) => ({
                  ...s,
                  escalate_to_hr_after_days: Math.max(1, parseInt(e.target.value) || 1),
                }))
              }
              className={t.numberInput}
            />
          </div>
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className={`px-6 py-2.5 ${t.btnPrimary} text-[10px] font-bold uppercase tracking-wider rounded-xl disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
