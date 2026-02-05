import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FileText,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  DollarSign,
  Calendar,
  ArrowUpRight,
  Filter
} from 'lucide-react';
import { api } from '../../api/client';
import type { DealApplication, ApplicationStatus } from '../../types/deals';

export function MyApplications() {
  const navigate = useNavigate();
  const [applications, setApplications] = useState<DealApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedStatus, setSelectedStatus] = useState<string>('all');

  useEffect(() => {
    loadApplications();
  }, []);

  const loadApplications = async () => {
    try {
      const res = await api.deals.listMyApplications();
      setApplications(res);
    } catch (err) {
      console.error('Failed to load applications:', err);
    } finally {
      setLoading(false);
    }
  };

  const withdrawApplication = async (id: string) => {
    if (!confirm('Withdraw this application? This action cannot be undone.')) return;
    try {
      await api.deals.withdrawApplication(id);
      loadApplications();
    } catch (err) {
      console.error('Failed to withdraw:', err);
    }
  };

  const formatCurrency = (amount: number | null) => {
    if (!amount) return 'N/A';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const getStatusConfig = (status: ApplicationStatus) => {
    switch (status) {
      case 'pending':
        return { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Pending Review' };
      case 'under_review':
        return { icon: AlertCircle, color: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Under Review' };
      case 'shortlisted':
        return { icon: CheckCircle2, color: 'text-purple-500', bg: 'bg-purple-500/10', label: 'Shortlisted' };
      case 'accepted':
        return { icon: CheckCircle2, color: 'text-emerald-500', bg: 'bg-emerald-500/10', label: 'Accepted' };
      case 'rejected':
        return { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: 'Rejected' };
      case 'withdrawn':
        return { icon: XCircle, color: 'text-zinc-500', bg: 'bg-zinc-500/10', label: 'Withdrawn' };
      default:
        return { icon: Clock, color: 'text-zinc-500', bg: 'bg-zinc-500/10', label: status };
    }
  };

  const statuses: ApplicationStatus[] = ['pending', 'under_review', 'shortlisted', 'accepted', 'rejected', 'withdrawn'];

  const filteredApplications = selectedStatus === 'all'
    ? applications
    : applications.filter(a => a.status === selectedStatus);

  // Stats
  const stats = {
    total: applications.length,
    pending: applications.filter(a => ['pending', 'under_review'].includes(a.status)).length,
    shortlisted: applications.filter(a => a.status === 'shortlisted').length,
    accepted: applications.filter(a => a.status === 'accepted').length,
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="px-2 py-1 border border-blue-500/20 bg-blue-900/10 text-blue-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Applications
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            My Applications
          </h1>
        </div>
        <button
          onClick={() => navigate('/app/gumfit/deals')}
          className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold"
        >
          Browse Deals
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-white/10 border border-white/10">
        <div className="bg-zinc-950 p-6">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Total</div>
          <div className="text-2xl font-light text-white">{stats.total}</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Pending</div>
          <div className="text-2xl font-light text-amber-400">{stats.pending}</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Shortlisted</div>
          <div className="text-2xl font-light text-purple-400">{stats.shortlisted}</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Accepted</div>
          <div className="text-2xl font-light text-emerald-400">{stats.accepted}</div>
        </div>
      </div>

      {/* Status Filter */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedStatus('all')}
          className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
            selectedStatus === 'all'
              ? 'bg-white text-black border-white'
              : 'border-white/20 text-zinc-400 hover:border-white/40'
          }`}
        >
          All ({applications.length})
        </button>
        {statuses.map((status) => {
          const count = applications.filter(a => a.status === status).length;
          if (count === 0) return null;
          const config = getStatusConfig(status);
          return (
            <button
              key={status}
              onClick={() => setSelectedStatus(status)}
              className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
                selectedStatus === status
                  ? 'bg-white text-black border-white'
                  : 'border-white/20 text-zinc-400 hover:border-white/40'
              }`}
            >
              {config.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Applications List */}
      <div className="border border-white/10 bg-zinc-900/30">
        <div className="p-4 border-b border-white/10 flex justify-between items-center">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">
            Applications
          </h2>
          <div className="flex items-center gap-2 text-zinc-500">
            <Filter className="w-4 h-4" />
            <span className="text-[10px]">{filteredApplications.length} results</span>
          </div>
        </div>

        {filteredApplications.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
            <p className="text-zinc-400 mb-2">No applications found</p>
            <button
              onClick={() => navigate('/app/gumfit/deals')}
              className="text-xs text-blue-400 hover:text-blue-300"
            >
              Browse available deals →
            </button>
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {filteredApplications.map((app) => {
              const statusConfig = getStatusConfig(app.status);
              const StatusIcon = statusConfig.icon;

              return (
                <div
                  key={app.id}
                  className="p-6 hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-lg font-medium text-white">
                          {app.deal_title || 'Untitled Deal'}
                        </h3>
                        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-widest ${statusConfig.bg} ${statusConfig.color}`}>
                          <StatusIcon className="w-3 h-3" />
                          {statusConfig.label}
                        </span>
                      </div>

                      <p className="text-sm text-zinc-400 line-clamp-2 mb-4">
                        {app.pitch}
                      </p>

                      <div className="flex flex-wrap items-center gap-4 text-xs text-zinc-500">
                        {app.proposed_rate && (
                          <div className="flex items-center gap-2">
                            <DollarSign className="w-3 h-3" />
                            <span>Proposed: {formatCurrency(app.proposed_rate)}</span>
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <Calendar className="w-3 h-3" />
                          <span>Applied {formatDate(app.created_at)}</span>
                        </div>
                        {app.match_score && (
                          <div className="flex items-center gap-2">
                            <span className="text-emerald-400">Match: {app.match_score}%</span>
                          </div>
                        )}
                      </div>

                      {app.agency_notes && (
                        <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/20 text-xs text-blue-300">
                          <span className="font-bold">Agency Note:</span> {app.agency_notes}
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col items-end gap-2">
                      <button
                        onClick={() => navigate(`/app/gumfit/deals/${app.deal_id}`)}
                        className="p-2 border border-white/20 hover:bg-white/5 transition-colors"
                      >
                        <ArrowUpRight className="w-4 h-4 text-zinc-400" />
                      </button>

                      {['pending', 'under_review'].includes(app.status) && (
                        <button
                          onClick={() => withdrawApplication(app.id)}
                          className="text-[10px] text-red-400 hover:text-red-300 uppercase tracking-widest"
                        >
                          Withdraw
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default MyApplications;
