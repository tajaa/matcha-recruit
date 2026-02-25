import { useEffect, useMemo, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { handbooks } from '../api/client';
import type { HandbookDistributionRecipient } from '../types';

type DistributionMode = 'all' | 'specific';

interface HandbookDistributeModalProps {
  open: boolean;
  handbookId: string | null;
  handbookTitle?: string;
  submitting?: boolean;
  onClose: () => void;
  onSubmit: (employeeIds?: string[]) => Promise<void>;
}

export function HandbookDistributeModal({
  open,
  handbookId,
  handbookTitle,
  submitting = false,
  onClose,
  onSubmit,
}: HandbookDistributeModalProps) {
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<DistributionMode>('all');
  const [query, setQuery] = useState('');
  const [recipients, setRecipients] = useState<HandbookDistributionRecipient[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setMode('all');
      setQuery('');
      setRecipients([]);
      setSelectedIds(new Set());
      setLoadError(null);
      setSubmitError(null);
      return;
    }
    if (!handbookId) return;

    let mounted = true;
    const loadRecipients = async () => {
      try {
        setLoading(true);
        setLoadError(null);
        const data = await handbooks.listDistributionRecipients(handbookId);
        if (!mounted) return;
        setRecipients(data || []);
      } catch (error) {
        if (!mounted) return;
        setLoadError(error instanceof Error ? error.message : 'Failed to load employees');
      } finally {
        if (mounted) setLoading(false);
      }
    };

    void loadRecipients();
    return () => {
      mounted = false;
    };
  }, [open, handbookId]);

  const eligibleRecipients = useMemo(
    () => recipients.filter((recipient) => !recipient.already_assigned),
    [recipients],
  );

  const filteredRecipients = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return eligibleRecipients;
    return eligibleRecipients.filter((recipient) => {
      const haystack = `${recipient.name} ${recipient.email}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [eligibleRecipients, query]);

  const alreadyAssignedCount = useMemo(
    () => recipients.filter((recipient) => recipient.already_assigned).length,
    [recipients],
  );

  const handleToggleRecipient = (employeeId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(employeeId)) {
        next.delete(employeeId);
      } else {
        next.add(employeeId);
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!handbookId || submitting) return;
    setSubmitError(null);
    if (mode === 'specific') {
      if (selectedIds.size === 0) {
        setSubmitError('Select at least one employee.');
        return;
      }
      await onSubmit(Array.from(selectedIds));
      return;
    }
    await onSubmit();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 px-4">
      <div className="w-full max-w-2xl border border-zinc-700 bg-zinc-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
          <div>
            <h3 className="text-sm font-semibold text-white uppercase tracking-wider">Send Handbook For E-Signature</h3>
            {handbookTitle && (
              <p className="mt-1 text-[11px] text-zinc-500">{handbookTitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={() => {
              if (!submitting) onClose();
            }}
            className="rounded border border-zinc-700 p-1 text-zinc-400 hover:text-white"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          {loading ? (
            <div className="flex items-center gap-2 text-[11px] text-zinc-400 uppercase tracking-wider">
              <Loader2 size={12} className="animate-spin" />
              Loading employees...
            </div>
          ) : (
            <>
              <div className="space-y-3 rounded border border-zinc-800 bg-zinc-900/50 p-3">
                <label className="flex items-start gap-2 text-sm text-zinc-200">
                  <input
                    type="radio"
                    name="distribution-mode"
                    checked={mode === 'all'}
                    onChange={() => setMode('all')}
                    className="mt-0.5"
                  />
                  <span>
                    Send to all active employees
                    <span className="mt-0.5 block text-[11px] text-zinc-500">
                      {eligibleRecipients.length} eligible now
                    </span>
                  </span>
                </label>
                <label className="flex items-start gap-2 text-sm text-zinc-200">
                  <input
                    type="radio"
                    name="distribution-mode"
                    checked={mode === 'specific'}
                    onChange={() => setMode('specific')}
                    disabled={eligibleRecipients.length === 0}
                    className="mt-0.5"
                  />
                  <span>
                    Send to specific employees
                    <span className="mt-0.5 block text-[11px] text-zinc-500">
                      Select individual recipients for this run
                    </span>
                  </span>
                </label>
              </div>

              {mode === 'specific' && (
                <div className="space-y-3 rounded border border-zinc-800 bg-zinc-900/30 p-3">
                  <input
                    type="text"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search by name or email"
                    className="w-full border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 focus:border-zinc-500 focus:outline-none"
                  />
                  <div className="max-h-64 overflow-y-auto border border-zinc-800 bg-zinc-950">
                    {filteredRecipients.length === 0 ? (
                      <div className="px-3 py-6 text-center text-[11px] uppercase tracking-wider text-zinc-500">
                        No eligible employees found
                      </div>
                    ) : (
                      filteredRecipients.map((recipient) => (
                        <label
                          key={recipient.employee_id}
                          className="flex cursor-pointer items-start gap-3 border-b border-zinc-900 px-3 py-2 last:border-b-0 hover:bg-zinc-900/50"
                        >
                          <input
                            type="checkbox"
                            checked={selectedIds.has(recipient.employee_id)}
                            onChange={() => handleToggleRecipient(recipient.employee_id)}
                            className="mt-1"
                          />
                          <div className="min-w-0">
                            <p className="truncate text-sm text-zinc-100">{recipient.name}</p>
                            <p className="truncate text-[11px] text-zinc-500">{recipient.email}</p>
                          </div>
                        </label>
                      ))
                    )}
                  </div>
                  <p className="text-[11px] text-zinc-500">
                    Selected: {selectedIds.size}
                  </p>
                </div>
              )}

              {(alreadyAssignedCount > 0 || loadError || submitError) && (
                <div className="space-y-2 text-[11px]">
                  {alreadyAssignedCount > 0 && (
                    <p className="text-zinc-500">
                      {alreadyAssignedCount} employee{alreadyAssignedCount === 1 ? '' : 's'} already have this handbook assigned.
                    </p>
                  )}
                  {loadError && <p className="text-red-400">{loadError}</p>}
                  {submitError && <p className="text-red-400">{submitError}</p>}
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-zinc-800 px-5 py-4">
          <button
            type="button"
            onClick={() => {
              if (!submitting) onClose();
            }}
            className="border border-zinc-700 px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-300 hover:text-white"
            disabled={submitting}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading || submitting || Boolean(loadError)}
            className="bg-sky-600 px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {submitting ? 'Sending...' : mode === 'all' ? 'Send To All' : 'Send To Selected'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default HandbookDistributeModal;
