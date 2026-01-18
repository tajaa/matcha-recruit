import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  DollarSign,
  Plus,
  Filter,
  ChevronDown,
  TrendingUp,
  Calendar,
  Tag
} from 'lucide-react';
import { api } from '../../api/client';
import type { RevenueStream, RevenueEntry, RevenueSummary } from '../../types/creator';

export function RevenueDashboard() {
  const navigate = useNavigate();
  const [streams, setStreams] = useState<RevenueStream[]>([]);
  const [entries, setEntries] = useState<RevenueEntry[]>([]);
  const [summary, setSummary] = useState<RevenueSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedStream, setSelectedStream] = useState<string>('all');
  const [showNewStream, setShowNewStream] = useState(false);
  const [newStreamName, setNewStreamName] = useState('');
  const [newStreamCategory, setNewStreamCategory] = useState<string>('sponsorship');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [streamsRes, entriesRes, dashboardRes] = await Promise.all([
        api.creators.listRevenueStreams(),
        api.creators.listRevenueEntries({ limit: 50 }),
        api.creators.getDashboard(),
      ]);
      setStreams(streamsRes);
      setEntries(entriesRes);
      setSummary(dashboardRes.current_month);
    } catch (err) {
      console.error('Failed to load revenue data:', err);
    } finally {
      setLoading(false);
    }
  };

  const createStream = async () => {
    if (!newStreamName.trim()) return;
    try {
      await api.creators.createRevenueStream({
        name: newStreamName,
        category: newStreamCategory as any,
      });
      setNewStreamName('');
      setShowNewStream(false);
      loadData();
    } catch (err) {
      console.error('Failed to create stream:', err);
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

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const filteredEntries = selectedStream === 'all'
    ? entries
    : entries.filter(e => e.stream_id === selectedStream);

  const categories = [
    { value: 'adsense', label: 'AdSense' },
    { value: 'sponsorship', label: 'Sponsorship' },
    { value: 'affiliate', label: 'Affiliate' },
    { value: 'merch', label: 'Merchandise' },
    { value: 'subscription', label: 'Subscriptions' },
    { value: 'tips', label: 'Tips/Donations' },
    { value: 'licensing', label: 'Licensing' },
    { value: 'services', label: 'Services' },
    { value: 'other', label: 'Other' },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/10 pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="px-2 py-1 border border-emerald-500/20 bg-emerald-900/10 text-emerald-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Revenue Tracking
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Revenue
          </h1>
        </div>
        <div className="flex gap-4">
          <button
            onClick={() => setShowNewStream(true)}
            className="px-6 py-3 border border-white/20 hover:bg-white hover:text-black text-xs font-mono uppercase tracking-widest transition-all flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            New Stream
          </button>
          <button
            onClick={() => navigate('/app/creator/revenue/new')}
            className="px-6 py-3 bg-white text-black hover:bg-zinc-200 text-xs font-mono uppercase tracking-widest transition-all font-bold"
          >
            Log Revenue
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-white/10 border border-white/10">
          <div className="bg-zinc-950 p-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded bg-emerald-500/10 text-emerald-500">
                <DollarSign className="w-4 h-4" />
              </div>
              <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">
                Monthly Revenue
              </span>
            </div>
            <div className="text-3xl font-light text-white">
              {formatCurrency(summary.total_revenue)}
            </div>
          </div>

          <div className="bg-zinc-950 p-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded bg-amber-500/10 text-amber-500">
                <TrendingUp className="w-4 h-4" />
              </div>
              <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">
                Net Income
              </span>
            </div>
            <div className={`text-3xl font-light ${summary.net_income >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatCurrency(summary.net_income)}
            </div>
          </div>

          <div className="bg-zinc-950 p-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded bg-blue-500/10 text-blue-500">
                <Tag className="w-4 h-4" />
              </div>
              <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-bold">
                Revenue Streams
              </span>
            </div>
            <div className="text-3xl font-light text-white">
              {streams.filter(s => s.is_active).length}
            </div>
          </div>
        </div>
      )}

      {/* Revenue by Category */}
      {summary && Object.keys(summary.revenue_by_category).length > 0 && (
        <div className="border border-white/10 bg-zinc-900/30 p-6">
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-6">
            Revenue by Category
          </h2>
          <div className="space-y-4">
            {Object.entries(summary.revenue_by_category)
              .sort(([, a], [, b]) => b - a)
              .map(([category, amount]) => {
                const total = summary.total_revenue || 1;
                const percent = (amount / total) * 100;
                return (
                  <div key={category}>
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-zinc-400 capitalize">{category.replace('_', ' ')}</span>
                      <span className="text-white">{formatCurrency(amount)}</span>
                    </div>
                    <div className="w-full bg-zinc-800 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-emerald-500 h-full transition-all duration-500"
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Streams & Entries Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        {/* Revenue Streams Sidebar */}
        <div className="border border-white/10 bg-zinc-900/30">
          <div className="p-4 border-b border-white/10">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">Revenue Streams</h2>
          </div>
          <div className="divide-y divide-white/5">
            <button
              onClick={() => setSelectedStream('all')}
              className={`w-full p-4 flex items-center justify-between hover:bg-white/5 transition-colors text-left ${
                selectedStream === 'all' ? 'bg-white/10' : ''
              }`}
            >
              <span className="text-sm text-zinc-300">All Streams</span>
              <span className="text-xs text-zinc-500">{entries.length}</span>
            </button>
            {streams.map((stream) => (
              <button
                key={stream.id}
                onClick={() => setSelectedStream(stream.id)}
                className={`w-full p-4 flex items-center justify-between hover:bg-white/5 transition-colors text-left ${
                  selectedStream === stream.id ? 'bg-white/10' : ''
                }`}
              >
                <div>
                  <span className="text-sm text-zinc-300">{stream.name}</span>
                  <div className="text-[10px] text-zinc-500 capitalize">{stream.category}</div>
                </div>
                <span className="text-xs text-zinc-500">
                  {entries.filter(e => e.stream_id === stream.id).length}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Revenue Entries */}
        <div className="lg:col-span-3 border border-white/10 bg-zinc-900/30">
          <div className="p-4 border-b border-white/10 flex justify-between items-center">
            <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em]">
              Revenue Entries
            </h2>
            <div className="flex items-center gap-2 text-zinc-500">
              <Filter className="w-4 h-4" />
              <span className="text-[10px]">{filteredEntries.length} entries</span>
            </div>
          </div>
          <div className="divide-y divide-white/5">
            {filteredEntries.length === 0 ? (
              <div className="p-12 text-center text-zinc-500">
                <DollarSign className="w-8 h-8 mx-auto mb-3 opacity-50" />
                <p className="text-sm mb-4">No revenue entries yet</p>
                <button
                  onClick={() => navigate('/app/creator/revenue/new')}
                  className="text-xs text-emerald-400 hover:text-emerald-300"
                >
                  Log your first revenue →
                </button>
              </div>
            ) : (
              filteredEntries.map((entry) => (
                <div
                  key={entry.id}
                  className="p-4 flex items-center justify-between hover:bg-white/5 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-2 rounded bg-emerald-500/10 text-emerald-500">
                      <DollarSign className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-sm text-zinc-300">
                        {entry.description || entry.stream_name || 'Revenue'}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <Calendar className="w-3 h-3 text-zinc-600" />
                        <span className="text-[10px] text-zinc-500">{formatDate(entry.date)}</span>
                        {entry.stream_name && (
                          <>
                            <span className="text-zinc-700">•</span>
                            <span className="text-[10px] text-zinc-500">{entry.stream_name}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-light text-emerald-400">
                      +{formatCurrency(entry.amount)}
                    </div>
                    {entry.is_recurring && (
                      <span className="text-[9px] text-zinc-500 uppercase">Recurring</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* New Stream Modal */}
      {showNewStream && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-zinc-900 border border-white/10 max-w-md w-full">
            <div className="p-6 border-b border-white/10">
              <h2 className="text-lg font-bold text-white">New Revenue Stream</h2>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Stream Name
                </label>
                <input
                  type="text"
                  value={newStreamName}
                  onChange={(e) => setNewStreamName(e.target.value)}
                  placeholder="e.g., YouTube AdSense"
                  className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white placeholder:text-zinc-600 focus:outline-none focus:border-white/30"
                />
              </div>
              <div>
                <label className="block text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
                  Category
                </label>
                <div className="relative">
                  <select
                    value={newStreamCategory}
                    onChange={(e) => setNewStreamCategory(e.target.value)}
                    className="w-full px-4 py-3 bg-zinc-800 border border-white/10 text-white appearance-none focus:outline-none focus:border-white/30"
                  >
                    {categories.map((cat) => (
                      <option key={cat.value} value={cat.value}>{cat.label}</option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
                </div>
              </div>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end gap-4">
              <button
                onClick={() => setShowNewStream(false)}
                className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                onClick={createStream}
                className="px-6 py-2 bg-white text-black text-xs font-mono uppercase tracking-widest hover:bg-zinc-200 font-bold"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default RevenueDashboard;
