import { useState, useEffect } from 'react';
import { onboarding } from '../api/client';
import type { OnboardingNotificationSettings as Settings } from '../api/client';
import { X } from 'lucide-react';

const DEFAULTS: Settings = {
  email_enabled: true,
  hr_escalation_emails: [],
  reminder_days_before_due: 2,
  escalate_to_manager_after_days: 3,
  escalate_to_hr_after_days: 5,
  timezone: 'America/New_York',
};

export default function OnboardingNotificationSettings() {
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
      <p className="text-xs text-zinc-500 font-mono uppercase tracking-wider animate-pulse py-8 text-center">
        Loading notification settings...
      </p>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {error && (
        <div className="border border-red-500/30 bg-red-950/20 px-4 py-3 text-xs text-red-300">
          {error}
        </div>
      )}
      {success && (
        <div className="border border-emerald-500/30 bg-emerald-950/20 px-4 py-3 text-xs text-emerald-300">
          {success}
        </div>
      )}

      {/* Email notifications toggle */}
      <div className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-bold uppercase tracking-widest text-white">Email Notifications</h3>
            <p className="text-[10px] text-zinc-500 mt-1">
              Send email reminders and escalation alerts for onboarding tasks.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setSettings((s) => ({ ...s, email_enabled: !s.email_enabled }))}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border transition-colors ${
              settings.email_enabled
                ? 'bg-emerald-600 border-emerald-500/50'
                : 'bg-zinc-700 border-zinc-600'
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
      <div className="border border-white/10 bg-zinc-900/50 p-5 space-y-4">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-widest text-white">HR Escalation Emails</h3>
          <p className="text-[10px] text-zinc-500 mt-1">
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
            className="flex-1 bg-zinc-900 border border-white/10 text-xs text-zinc-200 px-3 py-2 placeholder-zinc-600 focus:outline-none focus:border-white/30"
          />
          <button
            type="button"
            onClick={addEmail}
            className="px-4 py-2 bg-white text-black text-[10px] font-bold uppercase tracking-wider hover:bg-zinc-200"
          >
            Add
          </button>
        </div>

        {settings.hr_escalation_emails.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {settings.hr_escalation_emails.map((email) => (
              <span
                key={email}
                className="inline-flex items-center gap-1.5 border border-white/10 bg-zinc-800 px-2.5 py-1 text-[11px] text-zinc-300"
              >
                {email}
                <button
                  type="button"
                  onClick={() => removeEmail(email)}
                  className="text-zinc-500 hover:text-white"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Timing Settings */}
      <div className="border border-white/10 bg-zinc-900/50 p-5 space-y-5">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-widest text-white">Timing</h3>
          <p className="text-[10px] text-zinc-500 mt-1">
            Configure when reminders and escalations are triggered.
          </p>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <label className="text-[11px] text-zinc-400">Remind before due date (days)</label>
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
              className="w-20 bg-zinc-900 border border-white/10 text-xs text-zinc-200 px-3 py-2 text-center focus:outline-none focus:border-white/30"
            />
          </div>

          <div className="flex items-center justify-between gap-4">
            <label className="text-[11px] text-zinc-400">Escalate to manager after (days overdue)</label>
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
              className="w-20 bg-zinc-900 border border-white/10 text-xs text-zinc-200 px-3 py-2 text-center focus:outline-none focus:border-white/30"
            />
          </div>

          <div className="flex items-center justify-between gap-4">
            <label className="text-[11px] text-zinc-400">Escalate to HR after (days overdue)</label>
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
              className="w-20 bg-zinc-900 border border-white/10 text-xs text-zinc-200 px-3 py-2 text-center focus:outline-none focus:border-white/30"
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
          className="px-6 py-2.5 bg-white text-black text-[10px] font-bold uppercase tracking-wider hover:bg-zinc-200 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}
