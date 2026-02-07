import { useState, useEffect, useCallback } from 'react';
import { Button, Modal } from '../../components';
import { adminBusinessRegistrations, adminBusinessInvites } from '../../api/client';
import type { BusinessRegistration, BusinessRegistrationStatus, BusinessInvite } from '../../types';
import { Building2, Mail, Phone, Briefcase, Calendar, CheckCircle, XCircle, Clock, Link2, Copy, Plus, Trash2 } from 'lucide-react';

export function BusinessRegistrations() {
  const [registrations, setRegistrations] = useState<BusinessRegistration[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<BusinessRegistrationStatus | 'all'>('pending');
  const [error, setError] = useState<string | null>(null);

  // Reject modal state
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [selectedRegistration, setSelectedRegistration] = useState<BusinessRegistration | null>(null);
  const [processing, setProcessing] = useState(false);

  // Invite state
  const [invites, setInvites] = useState<BusinessInvite[]>([]);
  const [inviteNote, setInviteNote] = useState('');
  const [generatingInvite, setGeneratingInvite] = useState(false);
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [showInvites, setShowInvites] = useState(false);

  const fetchRegistrations = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await adminBusinessRegistrations.list(
        statusFilter === 'all' ? undefined : statusFilter
      );
      setRegistrations(data.registrations);
    } catch (err) {
      console.error('Failed to fetch registrations:', err);
      setError('Failed to load business registrations');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchRegistrations();
  }, [fetchRegistrations]);

  const handleApprove = async (registration: BusinessRegistration) => {
    try {
      setProcessing(true);
      await adminBusinessRegistrations.approve(registration.id);
      // Update local state
      setRegistrations(prev =>
        prev.map(r =>
          r.id === registration.id
            ? { ...r, status: 'approved' as BusinessRegistrationStatus }
            : r
        )
      );
      // If we're filtering by pending, remove from list
      if (statusFilter === 'pending') {
        setRegistrations(prev => prev.filter(r => r.id !== registration.id));
      }
    } catch (err) {
      console.error('Failed to approve:', err);
      setError('Failed to approve registration');
    } finally {
      setProcessing(false);
    }
  };

  const openRejectModal = (registration: BusinessRegistration) => {
    setSelectedRegistration(registration);
    setRejectReason('');
    setRejectModalOpen(true);
  };

  const handleReject = async () => {
    if (!selectedRegistration || !rejectReason.trim()) return;

    try {
      setProcessing(true);
      await adminBusinessRegistrations.reject(selectedRegistration.id, rejectReason.trim());
      // Update local state
      setRegistrations(prev =>
        prev.map(r =>
          r.id === selectedRegistration.id
            ? { ...r, status: 'rejected' as BusinessRegistrationStatus, rejection_reason: rejectReason.trim() }
            : r
        )
      );
      // If we're filtering by pending, remove from list
      if (statusFilter === 'pending') {
        setRegistrations(prev => prev.filter(r => r.id !== selectedRegistration.id));
      }
      setRejectModalOpen(false);
    } catch (err) {
      console.error('Failed to reject:', err);
      setError('Failed to reject registration');
    } finally {
      setProcessing(false);
    }
  };

  const fetchInvites = useCallback(async () => {
    try {
      const data = await adminBusinessInvites.list();
      setInvites(data.invites);
    } catch (err) {
      console.error('Failed to fetch invites:', err);
    }
  }, []);

  useEffect(() => {
    if (showInvites) fetchInvites();
  }, [showInvites, fetchInvites]);

  const handleGenerateInvite = async () => {
    try {
      setGeneratingInvite(true);
      const invite = await adminBusinessInvites.create(inviteNote || undefined);
      setInvites(prev => [invite, ...prev]);
      setInviteNote('');
      // Auto-copy the URL
      try {
        await navigator.clipboard.writeText(invite.invite_url);
        setCopiedToken(invite.token);
        setTimeout(() => setCopiedToken(null), 3000);
      } catch {
        console.warn('Clipboard write failed — invite was created but URL was not copied');
      }
    } catch (err) {
      console.error('Failed to generate invite:', err);
      setError('Failed to generate invite link');
    } finally {
      setGeneratingInvite(false);
    }
  };

  const handleCancelInvite = async (inviteId: string) => {
    try {
      await adminBusinessInvites.cancel(inviteId);
      setInvites(prev => prev.map(i => i.id === inviteId ? { ...i, status: 'cancelled' } : i));
    } catch (err) {
      console.error('Failed to cancel invite:', err);
    }
  };

  const copyInviteUrl = async (invite: BusinessInvite) => {
    await navigator.clipboard.writeText(invite.invite_url);
    setCopiedToken(invite.token);
    setTimeout(() => setCopiedToken(null), 3000);
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusBadge = (status: BusinessRegistrationStatus) => {
    switch (status) {
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 text-[10px] uppercase tracking-wider font-bold">
            <Clock size={12} />
            Pending
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] uppercase tracking-wider font-bold">
            <CheckCircle size={12} />
            Approved
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-red-500/10 text-red-400 border border-red-500/20 text-[10px] uppercase tracking-wider font-bold">
            <XCircle size={12} />
            Rejected
          </span>
        );
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-3 border-b border-white/10 pb-6 md:pb-8">
        <div>
          <h1 className="text-2xl md:text-4xl font-bold tracking-tighter text-white uppercase">Business Registrations</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Review and approve new business accounts
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800 text-xs text-zinc-400 font-mono">
            <span className="w-2 h-2 bg-amber-500 rounded-full animate-pulse" />
            {registrations.filter(r => r.status === 'pending').length} Pending
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {(['pending', 'approved', 'rejected', 'all'] as const).map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            className={`px-3 md:px-4 py-2 text-xs uppercase tracking-wider font-bold border transition-colors ${
              statusFilter === status
                ? 'bg-white text-black border-white'
                : 'bg-transparent text-zinc-500 border-zinc-800 hover:border-zinc-600 hover:text-zinc-300'
            }`}
          >
            {status}
          </button>
        ))}
      </div>

      {/* Main Table */}
      <div className="border border-white/10 bg-zinc-900/30">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="text-xs text-zinc-500 uppercase tracking-wider animate-pulse">Loading registrations...</div>
          </div>
        ) : registrations.length === 0 ? (
          <div className="text-center py-24 text-zinc-500 font-mono text-sm uppercase tracking-wider">
            No {statusFilter !== 'all' ? statusFilter : ''} registrations found
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10 bg-zinc-950">
                    <th className="text-left px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Company
                    </th>
                    <th className="text-left px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Owner
                    </th>
                    <th className="text-center px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Status
                    </th>
                    <th className="text-left px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Registered
                    </th>
                    <th className="text-right px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {registrations.map((registration) => (
                    <tr
                      key={registration.id}
                      className="border-b border-white/5 hover:bg-white/5 transition-colors bg-zinc-950"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                            <Building2 size={18} className="text-zinc-400" />
                          </div>
                          <div>
                            <div className="text-sm text-white font-bold">{registration.company_name}</div>
                            <div className="flex items-center gap-3 mt-1">
                              {registration.industry && (
                                <span className="text-[10px] text-zinc-500 font-mono">{registration.industry}</span>
                              )}
                              {registration.company_size && (
                                <span className="text-[10px] text-zinc-600 font-mono">{registration.company_size}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <div className="space-y-1">
                          <div className="text-sm text-white">{registration.owner_name}</div>
                          <div className="flex items-center gap-1 text-[10px] text-zinc-500 font-mono">
                            <Mail size={10} />
                            {registration.owner_email}
                          </div>
                          {registration.owner_phone && (
                            <div className="flex items-center gap-1 text-[10px] text-zinc-600 font-mono">
                              <Phone size={10} />
                              {registration.owner_phone}
                            </div>
                          )}
                          {registration.owner_job_title && (
                            <div className="flex items-center gap-1 text-[10px] text-zinc-600 font-mono">
                              <Briefcase size={10} />
                              {registration.owner_job_title}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-4 text-center">
                        <div className="space-y-2">
                          {getStatusBadge(registration.status)}
                          {registration.status === 'rejected' && registration.rejection_reason && (
                            <div className="text-[10px] text-red-400/70 max-w-[200px] truncate" title={registration.rejection_reason}>
                              {registration.rejection_reason}
                            </div>
                          )}
                          {registration.status === 'approved' && registration.approved_at && (
                            <div className="text-[10px] text-zinc-600">{formatDate(registration.approved_at)}</div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <div className="flex items-center gap-1 text-xs text-zinc-400 font-mono">
                          <Calendar size={12} />
                          {formatDate(registration.created_at)}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        {registration.status === 'pending' && (
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              size="sm"
                              onClick={() => handleApprove(registration)}
                              disabled={processing}
                              className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 px-3 py-1.5 text-[10px] uppercase tracking-wider"
                            >
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => openRejectModal(registration)}
                              disabled={processing}
                              className="bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 px-3 py-1.5 text-[10px] uppercase tracking-wider"
                            >
                              Reject
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile card layout */}
            <div className="md:hidden divide-y divide-white/5">
              {registrations.map((registration) => (
                <div key={registration.id} className="p-4 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                        <Building2 size={14} className="text-zinc-400" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm text-white font-bold truncate">{registration.company_name}</div>
                        <div className="flex items-center gap-2 mt-0.5">
                          {registration.industry && (
                            <span className="text-[10px] text-zinc-500 font-mono">{registration.industry}</span>
                          )}
                          {registration.company_size && (
                            <span className="text-[10px] text-zinc-600 font-mono">{registration.company_size}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    {getStatusBadge(registration.status)}
                  </div>

                  <div className="space-y-1 pl-11">
                    <div className="text-sm text-white">{registration.owner_name}</div>
                    <div className="flex items-center gap-1 text-[10px] text-zinc-500 font-mono">
                      <Mail size={10} />
                      <span className="truncate">{registration.owner_email}</span>
                    </div>
                    {registration.owner_phone && (
                      <div className="flex items-center gap-1 text-[10px] text-zinc-600 font-mono">
                        <Phone size={10} />
                        {registration.owner_phone}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between pl-11">
                    <div className="flex items-center gap-1 text-[10px] text-zinc-500 font-mono">
                      <Calendar size={10} />
                      {formatDate(registration.created_at)}
                    </div>
                    {registration.status === 'pending' && (
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          onClick={() => handleApprove(registration)}
                          disabled={processing}
                          className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 px-3 py-1.5 text-[10px] uppercase tracking-wider"
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => openRejectModal(registration)}
                          disabled={processing}
                          className="bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 px-3 py-1.5 text-[10px] uppercase tracking-wider"
                        >
                          Reject
                        </Button>
                      </div>
                    )}
                  </div>

                  {registration.status === 'rejected' && registration.rejection_reason && (
                    <div className="text-[10px] text-red-400/70 pl-11 truncate" title={registration.rejection_reason}>
                      {registration.rejection_reason}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Reject Modal */}
      <Modal
        isOpen={rejectModalOpen}
        onClose={() => setRejectModalOpen(false)}
        title="Reject Registration"
      >
        <div className="space-y-6">
          {selectedRegistration && (
            <div className="p-4 bg-zinc-900 border border-zinc-800">
              <div className="text-sm text-white font-bold">{selectedRegistration.company_name}</div>
              <div className="text-xs text-zinc-500 mt-1">{selectedRegistration.owner_name} &bull; {selectedRegistration.owner_email}</div>
            </div>
          )}

          <div>
            <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
              Rejection Reason *
            </label>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Please provide a reason for rejection..."
              rows={4}
              className="w-full bg-zinc-950 border border-zinc-800 text-white text-sm p-3 focus:outline-none focus:border-zinc-600 resize-none"
            />
            <p className="text-[10px] text-zinc-600 mt-2">
              This reason will be included in the rejection email sent to the business owner.
            </p>
          </div>

          <div className="flex gap-3 pt-4">
            <Button
              variant="secondary"
              onClick={() => setRejectModalOpen(false)}
              className="flex-1 bg-transparent border-zinc-700 text-zinc-400 hover:text-white hover:bg-zinc-800"
            >
              Cancel
            </Button>
            <Button
              onClick={handleReject}
              disabled={processing || !rejectReason.trim()}
              className="flex-1 bg-red-500 text-white hover:bg-red-600 font-bold uppercase tracking-wider"
            >
              {processing ? 'Processing...' : 'Confirm Rejection'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Invite Links Section */}
      <div className="border-t border-white/10 pt-8">
        <div className="flex flex-col sm:flex-row justify-between sm:items-end gap-3 mb-6">
          <div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tighter text-white uppercase">Invite Links</h2>
            <p className="text-xs text-zinc-500 mt-1 font-mono tracking-wide uppercase">
              Generate invite URLs for auto-approved registration
            </p>
          </div>
          <button
            onClick={() => setShowInvites(!showInvites)}
            className="self-start sm:self-auto px-4 py-2 text-xs uppercase tracking-wider font-bold border border-zinc-800 text-zinc-400 hover:border-zinc-600 hover:text-zinc-300 transition-colors"
          >
            {showInvites ? 'Hide' : 'Show'}
          </button>
        </div>

        {showInvites && (
          <div className="space-y-4">
            {/* Generate invite */}
            <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
              <div className="flex-1">
                <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
                  Note <span className="text-zinc-600 font-normal normal-case">(optional)</span>
                </label>
                <input
                  type="text"
                  value={inviteNote}
                  onChange={(e) => setInviteNote(e.target.value)}
                  placeholder="e.g. For Acme Corp onboarding"
                  className="w-full bg-zinc-950 border border-zinc-800 text-white text-sm px-3 py-2 focus:outline-none focus:border-zinc-600"
                />
              </div>
              <button
                onClick={handleGenerateInvite}
                disabled={generatingInvite}
                className="flex items-center justify-center gap-2 px-4 py-2 bg-white text-black text-xs uppercase tracking-wider font-bold hover:bg-zinc-200 disabled:opacity-50 transition-colors whitespace-nowrap"
              >
                <Plus size={14} />
                {generatingInvite ? 'Generating...' : 'Generate Link'}
              </button>
            </div>

            {/* Invites list — card layout for mobile, table for desktop */}
            {invites.length > 0 && (
              <>
                {/* Desktop table */}
                <div className="hidden md:block border border-white/10 bg-zinc-900/30">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/10 bg-zinc-950">
                        <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Link</th>
                        <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Note</th>
                        <th className="text-center px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Status</th>
                        <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Used By</th>
                        <th className="text-left px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Expires</th>
                        <th className="text-right px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invites.map((invite) => (
                        <tr key={invite.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <Link2 size={12} className="text-zinc-500 shrink-0" />
                              <span className="text-xs text-zinc-400 font-mono truncate max-w-[180px]">
                                .../{invite.token.slice(0, 12)}...
                              </span>
                              <button
                                onClick={() => copyInviteUrl(invite)}
                                className="text-zinc-500 hover:text-white transition-colors"
                                title="Copy invite URL"
                              >
                                {copiedToken === invite.token ? (
                                  <CheckCircle size={14} className="text-emerald-400" />
                                ) : (
                                  <Copy size={14} />
                                )}
                              </button>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-xs text-zinc-400 max-w-[150px] truncate">
                            {invite.note || '-'}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`inline-flex items-center px-2 py-0.5 text-[10px] uppercase tracking-wider font-bold border ${
                              invite.status === 'pending' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                              invite.status === 'used' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                              invite.status === 'expired' ? 'bg-zinc-500/10 text-zinc-500 border-zinc-500/20' :
                              'bg-red-500/10 text-red-400 border-red-500/20'
                            }`}>
                              {invite.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-zinc-400">
                            {invite.used_by_company_name || '-'}
                          </td>
                          <td className="px-4 py-3 text-xs text-zinc-500 font-mono">
                            {formatDate(invite.expires_at)}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {invite.status === 'pending' && (
                              <button
                                onClick={() => handleCancelInvite(invite.id)}
                                className="text-zinc-500 hover:text-red-400 transition-colors"
                                title="Cancel invite"
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Mobile card layout */}
                <div className="md:hidden space-y-3">
                  {invites.map((invite) => (
                    <div key={invite.id} className="border border-white/10 bg-zinc-900/30 p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className={`inline-flex items-center px-2 py-0.5 text-[10px] uppercase tracking-wider font-bold border ${
                          invite.status === 'pending' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                          invite.status === 'used' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                          invite.status === 'expired' ? 'bg-zinc-500/10 text-zinc-500 border-zinc-500/20' :
                          'bg-red-500/10 text-red-400 border-red-500/20'
                        }`}>
                          {invite.status}
                        </span>
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => copyInviteUrl(invite)}
                            className="text-zinc-500 hover:text-white transition-colors p-1"
                            title="Copy invite URL"
                          >
                            {copiedToken === invite.token ? (
                              <CheckCircle size={16} className="text-emerald-400" />
                            ) : (
                              <Copy size={16} />
                            )}
                          </button>
                          {invite.status === 'pending' && (
                            <button
                              onClick={() => handleCancelInvite(invite.id)}
                              className="text-zinc-500 hover:text-red-400 transition-colors p-1"
                              title="Cancel invite"
                            >
                              <Trash2 size={16} />
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Link2 size={12} className="text-zinc-500 shrink-0" />
                        <span className="text-xs text-zinc-400 font-mono truncate">
                          .../{invite.token.slice(0, 16)}...
                        </span>
                      </div>

                      {invite.note && (
                        <p className="text-xs text-zinc-400 truncate">{invite.note}</p>
                      )}

                      <div className="flex items-center justify-between text-[10px] text-zinc-500 font-mono">
                        <span>Expires {formatDate(invite.expires_at)}</span>
                        {invite.used_by_company_name && (
                          <span className="text-zinc-400">{invite.used_by_company_name}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default BusinessRegistrations;
