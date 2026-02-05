import { useEffect, useState } from 'react';
import { Search, Send, Clock, CheckCircle, XCircle, Plus, X } from 'lucide-react';
import { api } from '../../api/client';
import type { GumFitInvite, GumFitInviteCreate } from '../../api/client';

export function GumFitInvites() {
  const [invites, setInvites] = useState<GumFitInvite[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'accepted' | 'expired'>('all');
  const [showNewInviteModal, setShowNewInviteModal] = useState(false);

  // New invite form state
  const [newInvite, setNewInvite] = useState<GumFitInviteCreate>({
    email: '',
    invite_type: 'creator',
    message: '',
  });
  const [sending, setSending] = useState(false);

  useEffect(() => {
    loadInvites();
  }, [search, statusFilter]);

  const loadInvites = async () => {
    try {
      const invite_status = statusFilter !== 'all' ? statusFilter : undefined;
      const res = await api.gumfit.listInvites({ search: search || undefined, invite_status });
      setInvites(res.invites);
    } catch (err) {
      console.error('Failed to load invites:', err);
    } finally {
      setLoading(false);
    }
  };

  // Filtering is now done on the server side
  const filteredInvites = invites;

  const sendInvite = async () => {
    if (!newInvite.email) return;

    setSending(true);
    try {
      const created = await api.gumfit.sendInvite(newInvite);
      setInvites([created, ...invites]);
      setNewInvite({ email: '', invite_type: 'creator', message: '' });
      setShowNewInviteModal(false);
    } catch (err) {
      console.error('Failed to send invite:', err);
    } finally {
      setSending(false);
    }
  };

  const resendInvite = async (inviteId: string) => {
    try {
      await api.gumfit.resendInvite(inviteId);
      loadInvites(); // Refresh the list
    } catch (err) {
      console.error('Failed to resend invite:', err);
    }
  };

  const getStatusBadge = (status: 'pending' | 'accepted' | 'expired') => {
    switch (status) {
      case 'pending':
        return (
          <span className="flex items-center gap-1 text-amber-400 text-xs">
            <Clock className="w-3 h-3" />
            Pending
          </span>
        );
      case 'accepted':
        return (
          <span className="flex items-center gap-1 text-emerald-400 text-xs">
            <CheckCircle className="w-3 h-3" />
            Accepted
          </span>
        );
      case 'expired':
        return (
          <span className="flex items-center gap-1 text-red-400 text-xs">
            <XCircle className="w-3 h-3" />
            Expired
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
            GumFit Admin
          </div>
          <h1 className="text-2xl font-bold text-white">Invites</h1>
          <p className="text-sm text-zinc-400 mt-1">
            Send and manage platform invitations
          </p>
        </div>
        <button
          onClick={() => setShowNewInviteModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-white text-black text-xs uppercase tracking-widest font-bold hover:bg-zinc-200 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Send Invite
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search invites..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-zinc-900 border border-white/10 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-white/30"
          />
        </div>
        <div className="flex gap-2">
          {(['all', 'pending', 'accepted', 'expired'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setStatusFilter(f)}
              className={`px-4 py-2 text-xs uppercase tracking-widest transition-colors ${
                statusFilter === f
                  ? 'bg-white text-black'
                  : 'bg-zinc-900 text-zinc-400 hover:text-white border border-white/10'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Invites Table */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Email
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Type
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Sent
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Expires
                </th>
                <th className="text-right px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredInvites.map((invite) => (
                <tr key={invite.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-4 py-4">
                    <div className="text-sm text-white">{invite.email}</div>
                    {invite.message && (
                      <div className="text-xs text-zinc-500 mt-1 truncate max-w-xs">
                        {invite.message}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={`px-2 py-1 text-xs uppercase tracking-widest ${
                        invite.invite_type === 'creator'
                          ? 'text-blue-400 bg-blue-500/10'
                          : 'text-purple-400 bg-purple-500/10'
                      }`}
                    >
                      {invite.invite_type}
                    </span>
                  </td>
                  <td className="px-4 py-4">{getStatusBadge(invite.status)}</td>
                  <td className="px-4 py-4">
                    <div className="text-sm text-zinc-400">
                      {new Date(invite.created_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-sm text-zinc-400">
                      {new Date(invite.expires_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center justify-end gap-2">
                      {(invite.status === 'pending' || invite.status === 'expired') && (
                        <button
                          onClick={() => resendInvite(invite.id)}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs text-white bg-white/10 hover:bg-white/20 transition-colors"
                        >
                          <Send className="w-3 h-3" />
                          Resend
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filteredInvites.length === 0 && (
          <div className="text-center py-12">
            <p className="text-zinc-500 text-sm">No invites found</p>
          </div>
        )}
      </div>

      {/* New Invite Modal */}
      {showNewInviteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="bg-zinc-900 border border-white/10 w-full max-w-md mx-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-4 border-b border-white/10">
              <h2 className="text-sm font-bold text-white uppercase tracking-widest">
                Send Invite
              </h2>
              <button
                onClick={() => setShowNewInviteModal(false)}
                className="text-zinc-400 hover:text-white transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Email Address
                </label>
                <input
                  type="email"
                  value={newInvite.email}
                  onChange={(e) =>
                    setNewInvite({ ...newInvite, email: e.target.value })
                  }
                  placeholder="user@example.com"
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-white/30"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Invite Type
                </label>
                <div className="flex gap-2">
                  {(['creator', 'agency'] as const).map((type) => (
                    <button
                      key={type}
                      onClick={() =>
                        setNewInvite({ ...newInvite, invite_type: type })
                      }
                      className={`flex-1 px-4 py-2 text-xs uppercase tracking-widest transition-colors ${
                        newInvite.invite_type === type
                          ? 'bg-white text-black'
                          : 'bg-zinc-800 text-zinc-400 hover:text-white border border-white/10'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Personal Message (Optional)
                </label>
                <textarea
                  value={newInvite.message}
                  onChange={(e) =>
                    setNewInvite({ ...newInvite, message: e.target.value })
                  }
                  placeholder="Add a personal message..."
                  rows={3}
                  className="w-full px-3 py-2 bg-zinc-800 border border-white/10 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-white/30 resize-none"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 p-4 border-t border-white/10">
              <button
                onClick={() => setShowNewInviteModal(false)}
                className="px-4 py-2 text-xs uppercase tracking-widest text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={sendInvite}
                disabled={!newInvite.email || sending}
                className="flex items-center gap-2 px-4 py-2 bg-white text-black text-xs uppercase tracking-widest font-bold hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="w-4 h-4" />
                {sending ? 'Sending...' : 'Send Invite'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default GumFitInvites;
