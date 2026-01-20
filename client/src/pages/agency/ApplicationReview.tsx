import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Filter,
  ChevronDown,
  Clock,
  CheckCircle2,
  XCircle,
  Star,
  DollarSign,
  Calendar,
  ArrowUpRight
} from 'lucide-react';
import { api } from '../../api/client';
import type { DealApplication, ApplicationStatus, BrandDeal } from '../../types/deals';

export function ApplicationReview() {
  const navigate = useNavigate();
  const [applications, setApplications] = useState<DealApplication[]>([]);
  const [deals, setDeals] = useState<BrandDeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDeal, setSelectedDeal] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [expandedApp, setExpandedApp] = useState<string | null>(null);
  const [agencyNotes, setAgencyNotes] = useState<string>('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const dealsRes = await api.deals.listAgencyDeals();
      setDeals(dealsRes);

      // Load applications for all deals
      const allApps: DealApplication[] = [];
      for (const deal of dealsRes) {
        const apps = await api.deals.listDealApplications(deal.id);
        allApps.push(...apps);
      }
      setApplications(allApps);
    } catch (err) {
      console.error('Failed to load data:', err);
    } finally {
      setLoading(false);
    }
  };

  const updateApplicationStatus = async (appId: string, status: ApplicationStatus, notes?: string) => {
    try {
      await api.deals.updateApplicationStatus(appId, { status, agency_notes: notes });
      setExpandedApp(null);
      setAgencyNotes('');
      loadData();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const createContract = async (application: DealApplication) => {
    try {
      const deal = deals.find(d => d.id === application.deal_id);
      if (!deal) return;

      await api.deals.createContract(application.id, {
        agreed_rate: application.proposed_rate || deal.compensation_min || 0,
        agreed_deliverables: application.proposed_deliverables.length > 0
          ? application.proposed_deliverables
          : deal.deliverables,
      });

      navigate('/app/gumfit/agency/contracts');
    } catch (err) {
      console.error('Failed to create contract:', err);
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
        return { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Pending' };
      case 'under_review':
        return { icon: Clock, color: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Under Review' };
      case 'shortlisted':
        return { icon: Star, color: 'text-purple-500', bg: 'bg-purple-500/10', label: 'Shortlisted' };
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

  const statuses: ApplicationStatus[] = ['pending', 'under_review', 'shortlisted', 'accepted', 'rejected'];

  // Filter applications
  const filteredApps = applications.filter(app => {
    const matchesDeal = selectedDeal === 'all' || app.deal_id === selectedDeal;
    const matchesStatus = selectedStatus === 'all' || app.status === selectedStatus;
    return matchesDeal && matchesStatus;
  });

  // Stats
  const stats = {
    pending: applications.filter(a => a.status === 'pending').length,
    under_review: applications.filter(a => a.status === 'under_review').length,
    shortlisted: applications.filter(a => a.status === 'shortlisted').length,
    total: applications.length,
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
            <div className="px-2 py-1 border border-amber-500/20 bg-amber-900/10 text-amber-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Applications
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Review Applications
          </h1>
        </div>
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
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Under Review</div>
          <div className="text-2xl font-light text-blue-400">{stats.under_review}</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Shortlisted</div>
          <div className="text-2xl font-light text-purple-400">{stats.shortlisted}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative min-w-[200px]">
          <select
            value={selectedDeal}
            onChange={(e) => setSelectedDeal(e.target.value)}
            className="w-full appearance-none px-4 py-3 pr-10 bg-zinc-900 border border-white/10 text-white focus:outline-none focus:border-white/30"
          >
            <option value="all">All Deals</option>
            {deals.map(deal => (
              <option key={deal.id} value={deal.id}>{deal.title}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedStatus('all')}
            className={`px-4 py-2 text-xs font-mono uppercase tracking-widest transition-all border ${
              selectedStatus === 'all'
                ? 'bg-white text-black border-white'
                : 'border-white/20 text-zinc-400 hover:border-white/40'
            }`}
          >
            All
          </button>
          {statuses.map((status) => {
            const count = applications.filter(a => a.status === status).length;
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
      </div>

      {/* Results */}
      <div className="flex items-center gap-2 text-zinc-500">
        <Filter className="w-4 h-4" />
        <span className="text-xs">{filteredApps.length} applications</span>
      </div>

      {/* Applications List */}
      {filteredApps.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <Users className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No applications found</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredApps.map((app) => {
            const statusConfig = getStatusConfig(app.status);
            const StatusIcon = statusConfig.icon;
            const isExpanded = expandedApp === app.id;
            const deal = deals.find(d => d.id === app.deal_id);

            return (
              <div
                key={app.id}
                className="border border-white/10 bg-zinc-900/30"
              >
                {/* Application Header */}
                <div
                  onClick={() => setExpandedApp(isExpanded ? null : app.id)}
                  className="p-6 hover:bg-white/5 transition-colors cursor-pointer"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-lg font-medium text-white">
                          {app.creator_name || 'Anonymous Creator'}
                        </h3>
                        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-widest ${statusConfig.bg} ${statusConfig.color}`}>
                          <StatusIcon className="w-3 h-3" />
                          {statusConfig.label}
                        </span>
                        {app.match_score && (
                          <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded">
                            {app.match_score}% match
                          </span>
                        )}
                      </div>

                      <div className="text-sm text-zinc-500 mb-3">
                        Applied to: {deal?.title || app.deal_title}
                      </div>

                      <p className="text-sm text-zinc-400 line-clamp-2">
                        {app.pitch}
                      </p>

                      <div className="flex flex-wrap items-center gap-4 mt-4 text-xs text-zinc-500">
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
                      </div>
                    </div>

                    <ArrowUpRight className={`w-5 h-5 text-zinc-600 transition-transform ${isExpanded ? 'rotate-45' : ''}`} />
                  </div>
                </div>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="border-t border-white/10 p-6 space-y-6">
                    {/* Full Pitch */}
                    <div>
                      <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Full Pitch</h4>
                      <p className="text-sm text-zinc-300">{app.pitch}</p>
                    </div>

                    {/* Portfolio Links */}
                    {app.portfolio_links.length > 0 && (
                      <div>
                        <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Portfolio</h4>
                        <div className="flex flex-wrap gap-2">
                          {app.portfolio_links.map((link, i) => (
                            <a
                              key={i}
                              href={link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1.5 bg-white/5 text-blue-400 text-xs hover:bg-white/10 transition-colors"
                            >
                              {new URL(link).hostname}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Proposed Deliverables */}
                    {app.proposed_deliverables.length > 0 && (
                      <div>
                        <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Proposed Deliverables</h4>
                        <div className="flex flex-wrap gap-2">
                          {app.proposed_deliverables.map((d, i) => (
                            <span key={i} className="px-3 py-1.5 bg-white/5 text-sm text-zinc-300">
                              {d.quantity && `${d.quantity}x `}{d.type}
                              {d.platform && ` (${d.platform})`}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Availability */}
                    {app.availability_notes && (
                      <div>
                        <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Availability</h4>
                        <p className="text-sm text-zinc-400">{app.availability_notes}</p>
                      </div>
                    )}

                    {/* Agency Notes Input */}
                    {['pending', 'under_review', 'shortlisted'].includes(app.status) && (
                      <div>
                        <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Internal Notes</h4>
                        <textarea
                          value={agencyNotes}
                          onChange={(e) => setAgencyNotes(e.target.value)}
                          placeholder="Add notes visible only to your team..."
                          rows={3}
                          className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30 resize-none text-sm"
                        />
                      </div>
                    )}

                    {/* Action Buttons */}
                    {['pending', 'under_review', 'shortlisted'].includes(app.status) && (
                      <div className="flex flex-wrap gap-2 pt-4 border-t border-white/10">
                        {app.status === 'pending' && (
                          <button
                            onClick={() => updateApplicationStatus(app.id, 'under_review', agencyNotes)}
                            className="px-4 py-2 bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono uppercase tracking-widest hover:bg-blue-500/20"
                          >
                            Mark Under Review
                          </button>
                        )}
                        {['pending', 'under_review'].includes(app.status) && (
                          <button
                            onClick={() => updateApplicationStatus(app.id, 'shortlisted', agencyNotes)}
                            className="px-4 py-2 bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-mono uppercase tracking-widest hover:bg-purple-500/20"
                          >
                            Shortlist
                          </button>
                        )}
                        <button
                          onClick={() => updateApplicationStatus(app.id, 'accepted', agencyNotes)}
                          className="px-4 py-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono uppercase tracking-widest hover:bg-emerald-500/20"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => updateApplicationStatus(app.id, 'rejected', agencyNotes)}
                          className="px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono uppercase tracking-widest hover:bg-red-500/20"
                        >
                          Reject
                        </button>
                      </div>
                    )}

                    {/* Create Contract Button */}
                    {app.status === 'accepted' && (
                      <div className="pt-4 border-t border-white/10">
                        <button
                          onClick={() => createContract(app)}
                          className="px-6 py-3 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 font-bold"
                        >
                          Create Contract
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default ApplicationReview;
