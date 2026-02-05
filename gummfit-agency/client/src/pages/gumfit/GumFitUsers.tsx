import { useEffect, useState } from 'react';
import { Search, MoreHorizontal, User, ShieldCheck, Ban, Mail } from 'lucide-react';
import { api } from '../../api/client';
import type { GumFitUser } from '../../api/client';

export function GumFitUsers() {
  const [users, setUsers] = useState<GumFitUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<'all' | 'creator' | 'agency'>('all');

  useEffect(() => {
    loadUsers();
  }, [search, roleFilter]);

  const loadUsers = async () => {
    try {
      const role = roleFilter !== 'all' ? roleFilter : undefined;
      const res = await api.gumfit.listUsers({ search: search || undefined, role });
      setUsers(res.users);
    } catch (err) {
      console.error('Failed to load users:', err);
    } finally {
      setLoading(false);
    }
  };

  // Filtering is now done on the server side
  const filteredUsers = users;

  const toggleActive = async (userId: string, currentStatus: boolean) => {
    try {
      await api.gumfit.toggleUserActive(userId, !currentStatus);
      setUsers(
        users.map((u) =>
          u.id === userId ? { ...u, is_active: !currentStatus } : u
        )
      );
    } catch (err) {
      console.error('Failed to toggle active status:', err);
    }
  };

  const getRoleColor = (role: string) => {
    switch (role) {
      case 'creator':
        return 'text-blue-400 bg-blue-500/10';
      case 'agency':
        return 'text-purple-400 bg-purple-500/10';
      case 'admin':
        return 'text-red-400 bg-red-500/10';
      default:
        return 'text-zinc-400 bg-zinc-500/10';
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
      <div>
        <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
          GumFit Admin
        </div>
        <h1 className="text-2xl font-bold text-white">Users</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Manage all platform users
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
          <input
            type="text"
            placeholder="Search users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-zinc-900 border border-white/10 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-white/30"
          />
        </div>
        <div className="flex gap-2">
          {(['all', 'creator', 'agency'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setRoleFilter(f)}
              className={`px-4 py-2 text-xs uppercase tracking-widest transition-colors ${
                roleFilter === f
                  ? 'bg-white text-black'
                  : 'bg-zinc-900 text-zinc-400 hover:text-white border border-white/10'
              }`}
            >
              {f === 'all' ? 'All' : f + 's'}
            </button>
          ))}
        </div>
      </div>

      {/* Users Table */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  User
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Role
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Joined
                </th>
                <th className="text-left px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Last Login
                </th>
                <th className="text-right px-4 py-3 text-[10px] uppercase tracking-widest text-zinc-500 font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredUsers.map((user) => (
                <tr key={user.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-zinc-800 flex items-center justify-center">
                        <User className="w-5 h-5 text-zinc-600" />
                      </div>
                      <div>
                        <div className="text-sm font-medium text-white">
                          {user.profile_name || 'No Name'}
                        </div>
                        <div className="text-xs text-zinc-500">{user.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={`px-2 py-1 text-xs uppercase tracking-widest ${getRoleColor(
                        user.role
                      )}`}
                    >
                      {user.role}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    {user.is_active ? (
                      <span className="flex items-center gap-1 text-emerald-400 text-xs">
                        <ShieldCheck className="w-3 h-3" />
                        Active
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-red-400 text-xs">
                        <Ban className="w-3 h-3" />
                        Inactive
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-sm text-zinc-400">
                      {new Date(user.created_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-sm text-zinc-400">
                      {user.last_login
                        ? new Date(user.last_login).toLocaleDateString()
                        : 'Never'}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => toggleActive(user.id, user.is_active)}
                        className={`p-2 transition-colors ${
                          user.is_active
                            ? 'text-red-400 hover:text-red-300'
                            : 'text-emerald-400 hover:text-emerald-300'
                        }`}
                        title={user.is_active ? 'Deactivate' : 'Activate'}
                      >
                        {user.is_active ? (
                          <Ban className="w-4 h-4" />
                        ) : (
                          <ShieldCheck className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        className="p-2 text-zinc-400 hover:text-white transition-colors"
                        title="Send Email"
                      >
                        <Mail className="w-4 h-4" />
                      </button>
                      <button
                        className="p-2 text-zinc-400 hover:text-white transition-colors"
                        title="More Actions"
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filteredUsers.length === 0 && (
          <div className="text-center py-12">
            <p className="text-zinc-500 text-sm">No users found</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default GumFitUsers;
