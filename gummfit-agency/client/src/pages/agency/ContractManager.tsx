import { useEffect, useState } from 'react';
import {
  FileCheck,
  DollarSign,
  Calendar,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  AlertCircle,
  XCircle,
  Plus,
  Filter
} from 'lucide-react';
import { api } from '../../api/client';
import type { DealContract, ContractPayment, ContractStatus, PaymentStatus } from '../../types/deals';

export function ContractManager() {
  const [contracts, setContracts] = useState<DealContract[]>([]);
  const [payments, setPayments] = useState<Record<string, ContractPayment[]>>({});
  const [loading, setLoading] = useState(true);
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [expandedContract, setExpandedContract] = useState<string | null>(null);
  const [showAddPayment, setShowAddPayment] = useState<string | null>(null);
  const [newPayment, setNewPayment] = useState({
    amount: 0,
    milestone_name: '',
    due_date: '',
  });

  useEffect(() => {
    loadContracts();
  }, []);

  const loadContracts = async () => {
    try {
      const res = await api.deals.listAgencyContracts();
      setContracts(res);
    } catch (err) {
      console.error('Failed to load contracts:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadPayments = async (contractId: string) => {
    if (payments[contractId]) return;
    try {
      const res = await api.deals.listPayments(contractId);
      setPayments(prev => ({ ...prev, [contractId]: res }));
    } catch (err) {
      console.error('Failed to load payments:', err);
    }
  };

  const toggleContract = (contractId: string) => {
    if (expandedContract === contractId) {
      setExpandedContract(null);
    } else {
      setExpandedContract(contractId);
      loadPayments(contractId);
    }
  };

  const updateContractStatus = async (contractId: string, status: ContractStatus) => {
    try {
      await api.deals.updateContractStatus(contractId, { status });
      loadContracts();
    } catch (err) {
      console.error('Failed to update status:', err);
    }
  };

  const addPayment = async (contractId: string) => {
    if (!newPayment.amount) return;
    try {
      await api.deals.addPayment(contractId, newPayment);
      setShowAddPayment(null);
      setNewPayment({ amount: 0, milestone_name: '', due_date: '' });
      setPayments(prev => ({ ...prev, [contractId]: undefined as any }));
      loadPayments(contractId);
      loadContracts();
    } catch (err) {
      console.error('Failed to add payment:', err);
    }
  };

  const updatePaymentStatus = async (paymentId: string, status: PaymentStatus, contractId: string) => {
    try {
      await api.deals.updatePayment(paymentId, {
        status,
        paid_date: status === 'paid' ? new Date().toISOString().split('T')[0] : undefined,
      });
      setPayments(prev => ({ ...prev, [contractId]: undefined as any }));
      loadPayments(contractId);
      loadContracts();
    } catch (err) {
      console.error('Failed to update payment:', err);
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const getStatusConfig = (status: ContractStatus) => {
    switch (status) {
      case 'pending':
        return { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Pending' };
      case 'active':
        return { icon: CheckCircle2, color: 'text-emerald-500', bg: 'bg-emerald-500/10', label: 'Active' };
      case 'completed':
        return { icon: CheckCircle2, color: 'text-blue-500', bg: 'bg-blue-500/10', label: 'Completed' };
      case 'cancelled':
        return { icon: XCircle, color: 'text-zinc-500', bg: 'bg-zinc-500/10', label: 'Cancelled' };
      case 'disputed':
        return { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: 'Disputed' };
      default:
        return { icon: Clock, color: 'text-zinc-500', bg: 'bg-zinc-500/10', label: status };
    }
  };

  const getPaymentStatusConfig = (status: PaymentStatus) => {
    switch (status) {
      case 'pending': return { color: 'text-amber-400', bg: 'bg-amber-500/10' };
      case 'invoiced': return { color: 'text-blue-400', bg: 'bg-blue-500/10' };
      case 'paid': return { color: 'text-emerald-400', bg: 'bg-emerald-500/10' };
      case 'overdue': return { color: 'text-red-400', bg: 'bg-red-500/10' };
      case 'cancelled': return { color: 'text-zinc-400', bg: 'bg-zinc-500/10' };
      default: return { color: 'text-zinc-400', bg: 'bg-zinc-500/10' };
    }
  };

  const statuses: ContractStatus[] = ['pending', 'active', 'completed', 'cancelled', 'disputed'];

  // Filter contracts
  const filteredContracts = selectedStatus === 'all'
    ? contracts
    : contracts.filter(c => c.status === selectedStatus);

  // Stats
  const stats = {
    total: contracts.length,
    active: contracts.filter(c => c.status === 'active').length,
    totalValue: contracts.filter(c => ['active', 'completed'].includes(c.status)).reduce((sum, c) => sum + c.agreed_rate, 0),
    totalPaid: contracts.reduce((sum, c) => sum + c.total_paid, 0),
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
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Contract Management
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Contracts
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
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Active</div>
          <div className="text-2xl font-light text-emerald-400">{stats.active}</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Total Value</div>
          <div className="text-2xl font-light text-white">{formatCurrency(stats.totalValue)}</div>
        </div>
        <div className="bg-zinc-950 p-6">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">Total Paid</div>
          <div className="text-2xl font-light text-emerald-400">{formatCurrency(stats.totalPaid)}</div>
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
          All ({contracts.length})
        </button>
        {statuses.map((status) => {
          const count = contracts.filter(c => c.status === status).length;
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

      {/* Results */}
      <div className="flex items-center gap-2 text-zinc-500">
        <Filter className="w-4 h-4" />
        <span className="text-xs">{filteredContracts.length} contracts</span>
      </div>

      {/* Contracts List */}
      {filteredContracts.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <FileCheck className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No contracts found</p>
          <p className="text-xs text-zinc-600">
            Contracts are created when you accept creator applications
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredContracts.map((contract) => {
            const statusConfig = getStatusConfig(contract.status);
            const StatusIcon = statusConfig.icon;
            const isExpanded = expandedContract === contract.id;
            const contractPayments = payments[contract.id] || [];

            return (
              <div
                key={contract.id}
                className="border border-white/10 bg-zinc-900/30 overflow-hidden"
              >
                {/* Contract Header */}
                <div
                  onClick={() => toggleContract(contract.id)}
                  className="p-6 hover:bg-white/5 transition-colors cursor-pointer"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-lg font-medium text-white">
                          {contract.creator_name} - {contract.deal_title}
                        </h3>
                        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-[10px] uppercase tracking-widest ${statusConfig.bg} ${statusConfig.color}`}>
                          <StatusIcon className="w-3 h-3" />
                          {statusConfig.label}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-6 text-xs">
                        <div className="flex items-center gap-2">
                          <DollarSign className="w-4 h-4 text-emerald-500" />
                          <span className="text-emerald-400 font-medium">
                            {formatCurrency(contract.agreed_rate)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-500">
                          <CheckCircle2 className="w-4 h-4" />
                          <span>Paid: {formatCurrency(contract.total_paid)}</span>
                        </div>
                        <div className="flex items-center gap-2 text-zinc-500">
                          <span>
                            Remaining: {formatCurrency(contract.agreed_rate - contract.total_paid)}
                          </span>
                        </div>
                        {contract.start_date && (
                          <div className="flex items-center gap-2 text-zinc-500">
                            <Calendar className="w-4 h-4" />
                            <span>{formatDate(contract.start_date)} - {formatDate(contract.end_date)}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <ArrowUpRight className={`w-5 h-5 text-zinc-600 transition-transform ${isExpanded ? 'rotate-45' : ''}`} />
                  </div>
                </div>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="border-t border-white/10">
                    {/* Deliverables */}
                    {contract.agreed_deliverables.length > 0 && (
                      <div className="p-6 border-b border-white/5">
                        <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-3">Deliverables</h4>
                        <div className="flex flex-wrap gap-2">
                          {contract.agreed_deliverables.map((d, i) => (
                            <span key={i} className="px-3 py-1.5 bg-white/5 text-sm text-zinc-300 rounded">
                              {d.quantity && `${d.quantity}x `}{d.type}
                              {d.platform && ` (${d.platform})`}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Terms */}
                    {contract.terms && (
                      <div className="p-6 border-b border-white/5">
                        <h4 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-3">Terms</h4>
                        <p className="text-sm text-zinc-400">{contract.terms}</p>
                      </div>
                    )}

                    {/* Payments */}
                    <div className="p-6 border-b border-white/5">
                      <div className="flex items-center justify-between mb-4">
                        <h4 className="text-[10px] uppercase tracking-widest text-zinc-500">Payments</h4>
                        {['pending', 'active'].includes(contract.status) && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setShowAddPayment(contract.id);
                            }}
                            className="text-[10px] text-emerald-400 hover:text-emerald-300 flex items-center gap-1"
                          >
                            <Plus className="w-3 h-3" /> Add Payment
                          </button>
                        )}
                      </div>

                      {contractPayments.length === 0 ? (
                        <p className="text-sm text-zinc-600">No payments scheduled yet</p>
                      ) : (
                        <div className="space-y-2">
                          {contractPayments.map((payment) => {
                            const paymentConfig = getPaymentStatusConfig(payment.status);
                            return (
                              <div
                                key={payment.id}
                                className="flex items-center justify-between p-3 bg-white/5 rounded"
                              >
                                <div>
                                  <div className="text-sm text-zinc-300">
                                    {payment.milestone_name || 'Payment'}
                                  </div>
                                  {payment.due_date && (
                                    <div className="text-[10px] text-zinc-500">
                                      Due: {formatDate(payment.due_date)}
                                    </div>
                                  )}
                                </div>
                                <div className="flex items-center gap-4">
                                  <div className="text-right">
                                    <div className={`text-sm font-medium ${paymentConfig.color}`}>
                                      {formatCurrency(payment.amount)}
                                    </div>
                                    <div className={`text-[10px] uppercase ${paymentConfig.color}`}>
                                      {payment.status}
                                    </div>
                                  </div>
                                  {['pending', 'invoiced'].includes(payment.status) && (
                                    <button
                                      onClick={() => updatePaymentStatus(payment.id, 'paid', contract.id)}
                                      className="px-3 py-1 bg-emerald-500/10 text-emerald-400 text-[10px] uppercase hover:bg-emerald-500/20"
                                    >
                                      Mark Paid
                                    </button>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Add Payment Form */}
                      {showAddPayment === contract.id && (
                        <div className="mt-4 p-4 bg-zinc-800 border border-white/10 space-y-3">
                          <input
                            type="number"
                            value={newPayment.amount || ''}
                            onChange={(e) => setNewPayment({ ...newPayment, amount: parseFloat(e.target.value) || 0 })}
                            placeholder="Amount"
                            className="w-full px-3 py-2 bg-zinc-900 border border-white/10 text-white text-sm placeholder:text-zinc-600"
                          />
                          <input
                            type="text"
                            value={newPayment.milestone_name}
                            onChange={(e) => setNewPayment({ ...newPayment, milestone_name: e.target.value })}
                            placeholder="Milestone name (e.g., First video)"
                            className="w-full px-3 py-2 bg-zinc-900 border border-white/10 text-white text-sm placeholder:text-zinc-600"
                          />
                          <input
                            type="date"
                            value={newPayment.due_date}
                            onChange={(e) => setNewPayment({ ...newPayment, due_date: e.target.value })}
                            className="w-full px-3 py-2 bg-zinc-900 border border-white/10 text-white text-sm"
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => setShowAddPayment(null)}
                              className="px-4 py-2 border border-white/20 text-xs"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => addPayment(contract.id)}
                              className="px-4 py-2 bg-white text-black text-xs font-bold"
                            >
                              Add
                            </button>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Status Actions */}
                    {['pending', 'active'].includes(contract.status) && (
                      <div className="p-6 flex flex-wrap gap-2">
                        {contract.status === 'pending' && (
                          <button
                            onClick={() => updateContractStatus(contract.id, 'active')}
                            className="px-4 py-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono uppercase tracking-widest hover:bg-emerald-500/20"
                          >
                            Activate Contract
                          </button>
                        )}
                        {contract.status === 'active' && (
                          <button
                            onClick={() => updateContractStatus(contract.id, 'completed')}
                            className="px-4 py-2 bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono uppercase tracking-widest hover:bg-blue-500/20"
                          >
                            Mark Completed
                          </button>
                        )}
                        <button
                          onClick={() => updateContractStatus(contract.id, 'cancelled')}
                          className="px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-mono uppercase tracking-widest hover:bg-red-500/20"
                        >
                          Cancel
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

export default ContractManager;
