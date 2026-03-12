import { useState, useEffect } from 'react';
import { irIncidents } from '../../api/client';
import type { IRWitness, InvestigationInterviewCreateRequest } from '../../types';
import { useIsLightMode } from '../../hooks/useIsLightMode';

const LT = {
  modalBg: 'bg-stone-100 border border-stone-300 rounded-xl',
  modalInput: 'w-full px-2.5 py-1.5 bg-white border border-stone-300 rounded-xl text-sm text-zinc-900 focus:outline-none focus:border-stone-400',
  modalSelect: 'w-full px-2.5 py-1.5 bg-white border border-stone-300 rounded-xl text-sm text-zinc-900 focus:outline-none focus:border-stone-400 cursor-pointer',
  label: 'text-[10px] text-stone-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800 rounded-xl',
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  border: 'border-stone-200',
  rowBg: 'bg-white border border-stone-200 rounded-xl',
  textarea: 'w-full px-2.5 py-1.5 bg-white border border-stone-300 rounded-xl text-sm text-zinc-900 focus:outline-none focus:border-stone-400 resize-none',
} as const;

const DK = {
  modalBg: 'bg-zinc-900 border border-zinc-800 rounded-xl',
  modalInput: 'w-full px-2.5 py-1.5 bg-transparent border border-zinc-800 rounded-xl text-sm text-white focus:outline-none focus:border-zinc-600',
  modalSelect: 'w-full px-2.5 py-1.5 bg-transparent border border-zinc-800 rounded-xl text-sm text-white focus:outline-none focus:border-zinc-600 cursor-pointer',
  label: 'text-[10px] text-zinc-500 uppercase tracking-widest font-bold',
  btnGhost: 'text-zinc-600 hover:text-zinc-100',
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600 rounded-xl',
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  border: 'border-white/10',
  rowBg: 'bg-zinc-800/50 border border-white/10 rounded-xl',
  textarea: 'w-full px-2.5 py-1.5 bg-transparent border border-zinc-800 rounded-xl text-sm text-white focus:outline-none focus:border-zinc-600 resize-none',
} as const;

interface InterviewRow {
  name: string;
  email: string;
  role: 'witness' | 'complainant' | 'respondent' | 'manager';
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  incidentId: string;
  witnesses: IRWitness[];
  onSuccess: (count: number) => void;
}

export function ScheduleInterviewsModal({ isOpen, onClose, incidentId, witnesses, onSuccess }: Props) {
  const isLight = useIsLightMode();
  const t = isLight ? LT : DK;

  const [rows, setRows] = useState<InterviewRow[]>([]);
  const [customMessage, setCustomMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successResult, setSuccessResult] = useState<{ count: number; errors: Array<{ interviewee_name: string; error: string }> } | null>(null);

  // Pre-fill rows from witnesses on open
  useEffect(() => {
    if (isOpen) {
      setError(null);
      setSuccessResult(null);
      setCustomMessage('');
      if (witnesses.length > 0) {
        setRows(
          witnesses.map((w) => ({
            name: w.name,
            email: w.contact && w.contact.includes('@') ? w.contact : '',
            role: 'witness' as const,
          }))
        );
      } else {
        setRows([{ name: '', email: '', role: 'witness' }]);
      }
    }
  }, [isOpen, witnesses]);

  const addRow = () => {
    setRows((prev) => [...prev, { name: '', email: '', role: 'witness' }]);
  };

  const removeRow = (idx: number) => {
    setRows((prev) => prev.filter((_, i) => i !== idx));
  };

  const updateRow = (idx: number, field: keyof InterviewRow, value: string) => {
    setRows((prev) =>
      prev.map((row, i) =>
        i === idx ? { ...row, [field]: value } : row
      )
    );
  };

  const handleSend = async () => {
    setError(null);
    const validRows = rows.filter((r) => r.name.trim() && r.email.trim());
    if (validRows.length === 0) {
      setError('Add at least one interviewee with a name and email.');
      return;
    }

    const payload: InvestigationInterviewCreateRequest[] = validRows.map((r) => ({
      interviewee_name: r.name.trim(),
      interviewee_email: r.email.trim(),
      interviewee_role: r.role,
      send_invite: true,
      custom_message: customMessage.trim() || undefined,
    }));

    setLoading(true);
    try {
      const result = await irIncidents.createInvestigationInterviews(incidentId, payload);
      setSuccessResult({ count: result.created, errors: result.errors });
      if (result.created > 0) {
        onSuccess(result.created);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to schedule interviews');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className={`relative ${t.modalBg} w-full max-w-xl p-6 space-y-4 max-h-[85vh] overflow-y-auto`}>
        {successResult ? (
          <div className="space-y-4">
            <h3 className={`text-sm font-medium ${t.textMain}`}>Invites Sent</h3>
            <p className={`text-sm ${t.textMuted}`}>
              {successResult.count} interview invite{successResult.count !== 1 ? 's' : ''} scheduled successfully.
            </p>
            {successResult.errors.length > 0 && (
              <div>
                <div className={`${t.label} mb-2`}>Errors</div>
                <ul className="space-y-1">
                  {successResult.errors.map((e, i) => (
                    <li key={i} className="text-xs text-red-400">
                      {e.interviewee_name}: {e.error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex justify-end pt-2">
              <button
                onClick={onClose}
                className={`px-3 py-1.5 ${t.btnPrimary} text-xs uppercase tracking-wider font-bold`}
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="flex justify-between items-center">
              <h3 className={`text-sm font-medium ${t.textMain}`}>Schedule Investigation Interviews</h3>
              <button onClick={onClose} className={`text-xs ${t.btnGhost}`}>✕</button>
            </div>

            <p className={`text-xs ${t.textMuted}`}>
              Interviewees will receive an email invite with a secure link to complete their interview.
            </p>

            {/* Rows */}
            <div className="space-y-3">
              {rows.map((row, idx) => (
                <div key={idx} className={`${t.rowBg} p-3 space-y-2`}>
                  <div className="flex items-center justify-between">
                    <span className={`${t.label}`}>Interviewee {idx + 1}</span>
                    {rows.length > 1 && (
                      <button
                        onClick={() => removeRow(idx)}
                        className="text-[10px] text-red-500 hover:text-red-400 uppercase tracking-wider font-bold"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className={`${t.label} block mb-1`}>Name</label>
                      <input
                        value={row.name}
                        onChange={(e) => updateRow(idx, 'name', e.target.value)}
                        placeholder="Full name"
                        className={t.modalInput}
                      />
                    </div>
                    <div>
                      <label className={`${t.label} block mb-1`}>Email</label>
                      <input
                        type="email"
                        value={row.email}
                        onChange={(e) => updateRow(idx, 'email', e.target.value)}
                        placeholder="email@example.com"
                        className={t.modalInput}
                      />
                    </div>
                  </div>
                  <div>
                    <label className={`${t.label} block mb-1`}>Role</label>
                    <select
                      value={row.role}
                      onChange={(e) => updateRow(idx, 'role', e.target.value)}
                      className={t.modalSelect}
                    >
                      <option value="witness">Witness</option>
                      <option value="complainant">Complainant</option>
                      <option value="respondent">Respondent</option>
                      <option value="manager">Manager</option>
                    </select>
                  </div>
                </div>
              ))}
            </div>

            <button
              onClick={addRow}
              className={`text-xs ${t.btnGhost} uppercase tracking-wider font-bold`}
            >
              + Add Another
            </button>

            {/* Custom message */}
            <div>
              <label className={`${t.label} block mb-1`}>Custom Message (optional)</label>
              <textarea
                value={customMessage}
                onChange={(e) => setCustomMessage(e.target.value)}
                rows={3}
                placeholder="Add a personal note to include in the invite email..."
                className={t.textarea}
              />
            </div>

            {error && <p className="text-xs text-red-400">{error}</p>}

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={onClose}
                className={`text-xs ${t.btnGhost} uppercase tracking-wider font-bold`}
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={loading}
                className={`px-3 py-1.5 ${t.btnPrimary} text-xs disabled:opacity-50 uppercase tracking-wider font-bold`}
              >
                {loading ? 'Sending...' : 'Send Invites'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default ScheduleInterviewsModal;
