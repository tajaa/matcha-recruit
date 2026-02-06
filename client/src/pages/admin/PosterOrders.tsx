import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import type { PosterTemplate, PosterOrder, PosterOrderStatus } from '../../types';
import { Package, Truck, CheckCircle, Clock, XCircle, ChevronDown, ChevronUp, FileText, Download, RefreshCw, MapPin, Calendar, Hash } from 'lucide-react';

const STATUS_CONFIG: Record<PosterOrderStatus, { color: string; icon: React.ReactNode }> = {
  requested: { color: 'bg-blue-500/10 text-blue-400 border border-blue-500/20', icon: <Clock size={10} /> },
  quoted: { color: 'bg-amber-500/10 text-amber-400 border border-amber-500/20', icon: <Package size={10} /> },
  processing: { color: 'bg-purple-500/10 text-purple-400 border border-purple-500/20', icon: <Package size={10} /> },
  shipped: { color: 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20', icon: <Truck size={10} /> },
  delivered: { color: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20', icon: <CheckCircle size={10} /> },
  cancelled: { color: 'bg-zinc-500/10 text-zinc-500 border border-zinc-500/20', icon: <XCircle size={10} /> },
};

const TEMPLATE_STATUS_CONFIG: Record<string, string> = {
  generated: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
  pending: 'bg-amber-500/10 text-amber-400 border border-amber-500/20',
  failed: 'bg-red-500/10 text-red-400 border border-red-500/20',
};

const ALL_STATUSES: PosterOrderStatus[] = ['requested', 'quoted', 'processing', 'shipped', 'delivered', 'cancelled'];

const CATEGORY_LABELS: Record<string, string> = {
  posting_requirements: 'Posting',
  minimum_wage: 'Min Wage',
  overtime: 'Overtime',
  sick_leave: 'Sick Leave',
  workers_comp: 'Workers Comp',
};

type Tab = 'templates' | 'orders';

export function PosterOrders() {
  const [tab, setTab] = useState<Tab>('templates');

  const [templates, setTemplates] = useState<PosterTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [generatingAll, setGeneratingAll] = useState(false);

  const [orders, setOrders] = useState<PosterOrder[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<PosterOrderStatus | 'all'>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editStatus, setEditStatus] = useState<PosterOrderStatus | ''>('');
  const [editNotes, setEditNotes] = useState('');
  const [editQuote, setEditQuote] = useState('');
  const [editTracking, setEditTracking] = useState('');
  const [saving, setSaving] = useState(false);

  const fetchTemplates = useCallback(async () => {
    try {
      setTemplatesLoading(true);
      const data = await api.adminPosters.listTemplates();
      setTemplates(data.templates);
    } catch (err) {
      console.error('Failed to fetch templates:', err);
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  const fetchOrders = useCallback(async () => {
    try {
      setOrdersLoading(true);
      setError(null);
      const data = await api.adminPosters.listOrders(
        statusFilter === 'all' ? undefined : statusFilter
      );
      setOrders(data.orders);
    } catch (err) {
      console.error('Failed to fetch poster orders:', err);
      setError('Failed to load poster orders');
    } finally {
      setOrdersLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchTemplates();
    fetchOrders();
  }, []);

  useEffect(() => {
    if (tab === 'orders') fetchOrders();
  }, [statusFilter]);

  const handleGenerateAll = async () => {
    setGeneratingAll(true);
    try {
      const result = await api.adminPosters.generateAll();
      if (result.generated > 0 || result.failed > 0) {
        await fetchTemplates();
      }
      if (result.total_missing === 0) {
        setError('All jurisdictions already have poster templates.');
      }
    } catch (err) {
      console.error('Failed to generate all posters:', err);
      setError('Failed to generate posters');
    } finally {
      setGeneratingAll(false);
    }
  };

  const handleRegenerate = async (jurisdictionId: string) => {
    setGeneratingId(jurisdictionId);
    try {
      await api.adminPosters.generateTemplate(jurisdictionId);
      await fetchTemplates();
    } catch (err) {
      console.error('Failed to generate poster:', err);
      setError('Failed to generate poster');
    } finally {
      setGeneratingId(null);
    }
  };

  const downloadPdf = async (url: string, name: string) => {
    try {
      const res = await fetch(url);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${name.replace(/[^a-zA-Z0-9]+/g, '_')}_poster.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(blobUrl);
    } catch {
      window.open(url, '_blank');
    }
  };

  const toggleExpand = (order: PosterOrder) => {
    if (expandedId === order.id) {
      setExpandedId(null);
    } else {
      setExpandedId(order.id);
      setEditStatus(order.status);
      setEditNotes(order.admin_notes || '');
      setEditQuote(order.quote_amount != null ? String(order.quote_amount) : '');
      setEditTracking(order.tracking_number || '');
    }
  };

  const handleSave = async (orderId: string) => {
    try {
      setSaving(true);
      const updates: Record<string, unknown> = {};
      const current = orders.find(o => o.id === orderId);
      if (!current) return;

      if (editStatus && editStatus !== current.status) updates.status = editStatus;
      if (editNotes !== (current.admin_notes || '')) updates.admin_notes = editNotes;
      if (editQuote !== (current.quote_amount != null ? String(current.quote_amount) : '')) {
        updates.quote_amount = editQuote ? parseFloat(editQuote) : null;
      }
      if (editTracking !== (current.tracking_number || '')) updates.tracking_number = editTracking;

      if (Object.keys(updates).length === 0) return;

      await api.adminPosters.updateOrder(orderId, updates as any);
      await fetchOrders();
    } catch (err) {
      console.error('Failed to update order:', err);
      setError('Failed to update order');
    } finally {
      setSaving(false);
    }
  };

  const generatedCount = templates.filter(t => t.status === 'generated').length;

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-end justify-between border-b border-white/10 pb-8">
        <div>
          <h1 className="text-4xl font-bold tracking-tighter text-white uppercase">Compliance Posters</h1>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Generated poster PDFs and print order management
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900 border border-zinc-800">
            <FileText size={14} className="text-zinc-400" />
            <span className="text-xs font-mono text-zinc-400">{generatedCount} posters</span>
          </div>
          {tab === 'templates' && (
            <button
              onClick={handleGenerateAll}
              disabled={generatingAll}
              className="flex items-center gap-2 px-4 py-2 text-[10px] font-bold uppercase tracking-wider bg-white text-black border border-white hover:bg-zinc-200 disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={12} className={generatingAll ? 'animate-spin' : ''} />
              {generatingAll ? 'Generating...' : 'Generate Missing'}
            </button>
          )}
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-zinc-900/50 border border-white/10 p-4">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-2">Templates</div>
          <div className="text-2xl font-bold font-mono text-white">{templates.length}</div>
        </div>
        <div className="bg-zinc-900/50 border border-white/10 p-4">
          <div className="text-[10px] text-emerald-500 uppercase tracking-widest font-mono font-bold mb-2">Generated</div>
          <div className="text-2xl font-bold font-mono text-emerald-400">{generatedCount}</div>
        </div>
        <div className="bg-zinc-900/50 border border-white/10 p-4">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-2">Orders</div>
          <div className="text-2xl font-bold font-mono text-white">{orders.length}</div>
        </div>
        <div className="bg-zinc-900/50 border border-white/10 p-4">
          <div className="text-[10px] text-amber-500 uppercase tracking-widest font-mono font-bold mb-2">Pending</div>
          <div className="text-2xl font-bold font-mono text-amber-400">
            {orders.filter(o => o.status === 'requested' || o.status === 'quoted').length}
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-0 border-b border-white/5">
        <button
          onClick={() => setTab('templates')}
          className={`px-4 py-2.5 text-[10px] uppercase tracking-[0.15em] font-mono font-bold transition-colors border-b-2 -mb-px ${
            tab === 'templates'
              ? 'border-white text-white'
              : 'border-transparent text-zinc-600 hover:text-zinc-400'
          }`}
        >
          Poster Templates
        </button>
        <button
          onClick={() => setTab('orders')}
          className={`px-4 py-2.5 text-[10px] uppercase tracking-[0.15em] font-mono font-bold transition-colors border-b-2 -mb-px ${
            tab === 'orders'
              ? 'border-white text-white'
              : 'border-transparent text-zinc-600 hover:text-zinc-400'
          }`}
        >
          Print Orders
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-mono">
          {error}
          <button onClick={() => setError(null)} className="ml-3 text-red-500 hover:text-red-300 underline text-xs uppercase tracking-wider">dismiss</button>
        </div>
      )}

      {/* Templates tab */}
      {tab === 'templates' && (
        templatesLoading ? (
          <div className="flex items-center justify-center py-24">
            <span className="text-zinc-600 font-mono text-sm uppercase tracking-wider animate-pulse">Loading templates...</span>
          </div>
        ) : templates.length === 0 ? (
          <div className="text-center py-24 text-zinc-500 font-mono text-sm uppercase tracking-wider">
            No poster templates yet
          </div>
        ) : (
          <div className="border border-white/10 bg-zinc-900/30">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_120px_80px_160px_100px_80px] border-b border-white/10 bg-zinc-950">
              <div className="px-6 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Jurisdiction</div>
              <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Categories</div>
              <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest text-center">Reqs</div>
              <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Generated</div>
              <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest text-center">Status</div>
              <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest text-center">Actions</div>
            </div>
            {/* Rows */}
            {templates.map(tpl => (
              <div key={tpl.id} className="grid grid-cols-[1fr_120px_80px_160px_100px_80px] border-b border-white/5 hover:bg-white/5 transition-colors bg-zinc-950 items-center">
                {/* Jurisdiction */}
                <div className="px-6 py-3 flex items-center gap-3">
                  <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0">
                    <MapPin size={14} className="text-zinc-400" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-white truncate">
                      {tpl.jurisdiction_name || tpl.title}
                    </div>
                    <div className="text-[10px] text-zinc-500 font-mono">
                      v{tpl.version}
                    </div>
                  </div>
                </div>
                {/* Categories */}
                <div className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {tpl.categories_included?.map(cat => (
                      <span key={cat} className="text-[8px] px-1.5 py-0.5 bg-zinc-800 border border-zinc-700 text-zinc-400 uppercase tracking-wider font-mono">
                        {CATEGORY_LABELS[cat] || cat}
                      </span>
                    ))}
                  </div>
                </div>
                {/* Req count */}
                <div className="px-4 py-3 text-center">
                  <span className="text-sm font-mono text-white">{tpl.requirement_count}</span>
                </div>
                {/* Generated date */}
                <div className="px-4 py-3">
                  {tpl.pdf_generated_at && (
                    <div className="flex items-center gap-1 text-xs text-zinc-400 font-mono">
                      <Calendar size={10} />
                      {new Date(tpl.pdf_generated_at).toLocaleDateString()}
                    </div>
                  )}
                </div>
                {/* Status */}
                <div className="px-4 py-3 text-center">
                  <span className={`inline-flex items-center px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold ${TEMPLATE_STATUS_CONFIG[tpl.status] || 'bg-zinc-500/10 text-zinc-500 border border-zinc-500/20'}`}>
                    {tpl.status}
                  </span>
                </div>
                {/* Actions */}
                <div className="px-4 py-3 flex items-center justify-center gap-1">
                  {tpl.pdf_url && (
                    <button
                      onClick={() => downloadPdf(tpl.pdf_url!, tpl.jurisdiction_name || tpl.title)}
                      className="p-1.5 text-zinc-500 hover:text-white transition-colors"
                      title="Download PDF"
                    >
                      <Download size={14} />
                    </button>
                  )}
                  <button
                    onClick={() => handleRegenerate(tpl.jurisdiction_id)}
                    disabled={generatingId === tpl.jurisdiction_id}
                    className="p-1.5 text-zinc-500 hover:text-white transition-colors disabled:opacity-50"
                    title="Regenerate"
                  >
                    <RefreshCw size={14} className={generatingId === tpl.jurisdiction_id ? 'animate-spin' : ''} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* Orders tab */}
      {tab === 'orders' && (
        <>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-4 py-2 text-xs uppercase tracking-wider font-bold border transition-colors ${
                statusFilter === 'all'
                  ? 'bg-white text-black border-white'
                  : 'bg-transparent text-zinc-500 border-zinc-800 hover:border-zinc-600 hover:text-zinc-300'
              }`}
            >
              All
            </button>
            {ALL_STATUSES.map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-4 py-2 text-xs uppercase tracking-wider font-bold border transition-colors ${
                  statusFilter === s
                    ? 'bg-white text-black border-white'
                    : 'bg-transparent text-zinc-500 border-zinc-800 hover:border-zinc-600 hover:text-zinc-300'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {ordersLoading ? (
            <div className="flex items-center justify-center py-24">
              <span className="text-zinc-600 font-mono text-sm uppercase tracking-wider animate-pulse">Loading orders...</span>
            </div>
          ) : orders.length === 0 ? (
            <div className="text-center py-24 text-zinc-500 font-mono text-sm uppercase tracking-wider">
              No poster orders yet
            </div>
          ) : (
            <div className="border border-white/10 bg-zinc-900/30">
              {/* Table header */}
              <div className="grid grid-cols-[100px_1fr_120px_80px_100px_120px_40px] border-b border-white/10 bg-zinc-950">
                <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Status</div>
                <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Company / Location</div>
                <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Requested By</div>
                <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest text-center">Items</div>
                <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest text-right">Quote</div>
                <div className="px-4 py-4 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Date</div>
                <div className="px-4 py-4"></div>
              </div>
              {orders.map(order => (
                <div key={order.id}>
                  <button
                    onClick={() => toggleExpand(order)}
                    className="w-full grid grid-cols-[100px_1fr_120px_80px_100px_120px_40px] border-b border-white/5 hover:bg-white/5 transition-colors bg-zinc-950 items-center text-left"
                  >
                    <div className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold ${STATUS_CONFIG[order.status].color}`}>
                        {STATUS_CONFIG[order.status].icon}
                        {order.status}
                      </span>
                    </div>
                    <div className="px-4 py-3 min-w-0">
                      <div className="text-sm font-medium text-white truncate">{order.company_name}</div>
                      <div className="text-[10px] text-zinc-500 font-mono truncate">
                        {order.location_city}, {order.location_state}
                        {order.location_name && ` \u2014 ${order.location_name}`}
                      </div>
                    </div>
                    <div className="px-4 py-3">
                      <span className="text-xs text-zinc-400 font-mono truncate block">{order.requested_by_email || '\u2014'}</span>
                    </div>
                    <div className="px-4 py-3 text-center">
                      <span className="text-sm font-mono text-white">{order.items.length}</span>
                    </div>
                    <div className="px-4 py-3 text-right">
                      <span className="text-sm font-mono text-white">
                        {order.quote_amount != null ? `$${order.quote_amount.toFixed(2)}` : '\u2014'}
                      </span>
                    </div>
                    <div className="px-4 py-3">
                      <span className="text-xs text-zinc-400 font-mono">
                        {order.created_at ? new Date(order.created_at).toLocaleDateString() : ''}
                      </span>
                    </div>
                    <div className="px-4 py-3 flex justify-center">
                      {expandedId === order.id
                        ? <ChevronUp size={14} className="text-zinc-500" />
                        : <ChevronDown size={14} className="text-zinc-500" />
                      }
                    </div>
                  </button>

                  {expandedId === order.id && (
                    <div className="border-t border-white/5 bg-zinc-950/50 px-6 py-5 space-y-5">
                      {/* Items */}
                      <div>
                        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-2">Order Items</div>
                        <div className="space-y-1">
                          {order.items.map(item => (
                            <div key={item.id} className="flex justify-between text-sm py-1 border-b border-white/5 last:border-0">
                              <span className="text-zinc-300 font-mono">{item.template_title || item.jurisdiction_name}</span>
                              <span className="text-zinc-500 font-mono flex items-center gap-1"><Hash size={10} />{item.quantity}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Details grid */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-1">Ship To</div>
                          <div className="text-sm text-zinc-300 font-mono">{order.shipping_address || '\u2014'}</div>
                        </div>
                        {order.tracking_number && (
                          <div>
                            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-1">Tracking</div>
                            <div className="text-sm text-zinc-300 font-mono">{order.tracking_number}</div>
                          </div>
                        )}
                        {order.shipped_at && (
                          <div>
                            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-1">Shipped</div>
                            <div className="text-sm text-zinc-300 font-mono">{new Date(order.shipped_at).toLocaleDateString()}</div>
                          </div>
                        )}
                        {order.delivered_at && (
                          <div>
                            <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-1">Delivered</div>
                            <div className="text-sm text-zinc-300 font-mono">{new Date(order.delivered_at).toLocaleDateString()}</div>
                          </div>
                        )}
                      </div>

                      {/* Edit form */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-white/5">
                        <div>
                          <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-2">Status</label>
                          <select
                            value={editStatus}
                            onChange={e => setEditStatus(e.target.value as PosterOrderStatus)}
                            className="w-full text-sm bg-zinc-950 border border-zinc-800 text-white px-3 py-2 font-mono focus:outline-none focus:border-zinc-600"
                          >
                            {ALL_STATUSES.map(s => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-2">Quote ($)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={editQuote}
                            onChange={e => setEditQuote(e.target.value)}
                            placeholder="0.00"
                            className="w-full text-sm bg-zinc-950 border border-zinc-800 text-white px-3 py-2 font-mono focus:outline-none focus:border-zinc-600"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-2">Tracking Number</label>
                          <input
                            type="text"
                            value={editTracking}
                            onChange={e => setEditTracking(e.target.value)}
                            placeholder="e.g. 1Z999AA..."
                            className="w-full text-sm bg-zinc-950 border border-zinc-800 text-white px-3 py-2 font-mono focus:outline-none focus:border-zinc-600"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-zinc-500 uppercase tracking-widest font-mono font-bold mb-2">Admin Notes</label>
                          <input
                            type="text"
                            value={editNotes}
                            onChange={e => setEditNotes(e.target.value)}
                            placeholder="Internal notes..."
                            className="w-full text-sm bg-zinc-950 border border-zinc-800 text-white px-3 py-2 font-mono focus:outline-none focus:border-zinc-600"
                          />
                        </div>
                      </div>

                      <div className="flex justify-end">
                        <button
                          onClick={() => handleSave(order.id)}
                          disabled={saving}
                          className="px-5 py-2 text-[10px] font-bold uppercase tracking-wider bg-white text-black border border-white hover:bg-zinc-200 disabled:opacity-50 transition-colors"
                        >
                          {saving ? 'Saving...' : 'Save Changes'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default PosterOrders;
