import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api/client';
import type { PosterTemplate, PosterOrder, PosterOrderStatus } from '../../types';
import { Package, Truck, CheckCircle, Clock, XCircle, ChevronDown, ChevronUp, FileText, Download, RefreshCw } from 'lucide-react';

const STATUS_COLORS: Record<PosterOrderStatus, string> = {
  requested: 'bg-blue-100 text-blue-700',
  quoted: 'bg-amber-100 text-amber-700',
  processing: 'bg-purple-100 text-purple-700',
  shipped: 'bg-cyan-100 text-cyan-700',
  delivered: 'bg-green-100 text-green-700',
  cancelled: 'bg-zinc-100 text-zinc-500',
};

const STATUS_ICONS: Record<PosterOrderStatus, React.ReactNode> = {
  requested: <Clock className="w-3.5 h-3.5" />,
  quoted: <Package className="w-3.5 h-3.5" />,
  processing: <Package className="w-3.5 h-3.5" />,
  shipped: <Truck className="w-3.5 h-3.5" />,
  delivered: <CheckCircle className="w-3.5 h-3.5" />,
  cancelled: <XCircle className="w-3.5 h-3.5" />,
};

const TEMPLATE_STATUS_COLORS: Record<string, string> = {
  generated: 'bg-green-100 text-green-700',
  pending: 'bg-amber-100 text-amber-700',
  failed: 'bg-red-100 text-red-700',
};

const ALL_STATUSES: PosterOrderStatus[] = ['requested', 'quoted', 'processing', 'shipped', 'delivered', 'cancelled'];

type Tab = 'templates' | 'orders';

export function PosterOrders() {
  const [tab, setTab] = useState<Tab>('templates');

  // Templates state
  const [templates, setTemplates] = useState<PosterTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [generatingAll, setGeneratingAll] = useState(false);

  // Orders state
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

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Compliance Posters</h1>
          <p className="text-sm text-zinc-500 mt-1">Generated poster PDFs and print order management</p>
        </div>
        {tab === 'templates' && (
          <button
            onClick={handleGenerateAll}
            disabled={generatingAll}
            className="px-4 py-2 text-sm font-medium bg-matcha-600 text-white rounded-lg hover:bg-matcha-700 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${generatingAll ? 'animate-spin' : ''}`} />
            {generatingAll ? 'Generating...' : 'Generate All Missing'}
          </button>
        )}
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 mb-5 border-b border-zinc-200">
        <button
          onClick={() => setTab('templates')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            tab === 'templates'
              ? 'border-zinc-900 text-zinc-900'
              : 'border-transparent text-zinc-500 hover:text-zinc-700'
          }`}
        >
          Poster Templates ({templates.length})
        </button>
        <button
          onClick={() => setTab('orders')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            tab === 'orders'
              ? 'border-zinc-900 text-zinc-900'
              : 'border-transparent text-zinc-500 hover:text-zinc-700'
          }`}
        >
          Print Orders ({orders.length})
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">dismiss</button>
        </div>
      )}

      {/* Templates tab */}
      {tab === 'templates' && (
        templatesLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
          </div>
        ) : templates.length === 0 ? (
          <div className="text-center py-12 text-zinc-400 text-sm">
            No poster templates yet. Templates are generated automatically when jurisdictions have requirement data.
          </div>
        ) : (
          <div className="space-y-2">
            {templates.map(tpl => (
              <div key={tpl.id} className="border border-zinc-200 rounded-lg bg-white px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded bg-zinc-100 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-zinc-500" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-zinc-900 truncate">
                      {tpl.jurisdiction_name || tpl.title}
                    </div>
                    <div className="text-xs text-zinc-500">
                      v{tpl.version} &middot; {tpl.requirement_count} requirements
                      {tpl.categories_included && (
                        <span className="text-zinc-400 ml-1">
                          ({tpl.categories_included.join(', ')})
                        </span>
                      )}
                      {tpl.pdf_generated_at && (
                        <span className="text-zinc-400 ml-2">
                          Generated {new Date(tpl.pdf_generated_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${TEMPLATE_STATUS_COLORS[tpl.status] || 'bg-zinc-100 text-zinc-500'}`}>
                    {tpl.status}
                  </span>
                  {tpl.pdf_url && (
                    <button
                      onClick={async () => {
                        try {
                          const res = await fetch(tpl.pdf_url!);
                          const blob = await res.blob();
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = `${(tpl.jurisdiction_name || tpl.title).replace(/[^a-zA-Z0-9]+/g, '_')}_poster.pdf`;
                          document.body.appendChild(a);
                          a.click();
                          a.remove();
                          URL.revokeObjectURL(url);
                        } catch {
                          window.open(tpl.pdf_url!, '_blank');
                        }
                      }}
                      className="p-1.5 text-zinc-400 hover:text-zinc-700 transition-colors"
                      title="Download PDF"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => handleRegenerate(tpl.jurisdiction_id)}
                    disabled={generatingId === tpl.jurisdiction_id}
                    className="p-1.5 text-zinc-400 hover:text-zinc-700 transition-colors disabled:opacity-50"
                    title="Regenerate"
                  >
                    <RefreshCw className={`w-4 h-4 ${generatingId === tpl.jurisdiction_id ? 'animate-spin' : ''}`} />
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
          <div className="flex gap-2 mb-4 flex-wrap">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                statusFilter === 'all'
                  ? 'bg-zinc-900 text-white'
                  : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'
              }`}
            >
              All
            </button>
            {ALL_STATUSES.map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors capitalize ${
                  statusFilter === s
                    ? 'bg-zinc-900 text-white'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {ordersLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-2 h-2 rounded-full bg-matcha-500 animate-pulse" />
            </div>
          ) : orders.length === 0 ? (
            <div className="text-center py-12 text-zinc-400 text-sm">
              No poster orders yet
            </div>
          ) : (
            <div className="space-y-2">
              {orders.map(order => (
                <div key={order.id} className="border border-zinc-200 rounded-lg bg-white">
                  <button
                    onClick={() => toggleExpand(order)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-zinc-50 transition-colors"
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_COLORS[order.status]}`}>
                        {STATUS_ICONS[order.status]}
                        {order.status}
                      </span>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-zinc-900 truncate">
                          {order.company_name}
                        </div>
                        <div className="text-xs text-zinc-500 truncate">
                          {order.location_city}, {order.location_state}
                          {order.location_name && ` (${order.location_name})`}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 shrink-0">
                      <div className="text-right">
                        <div className="text-xs text-zinc-500">
                          {order.items.length} item{order.items.length !== 1 ? 's' : ''}
                        </div>
                        {order.quote_amount != null && (
                          <div className="text-xs font-medium text-zinc-700">
                            ${order.quote_amount.toFixed(2)}
                          </div>
                        )}
                      </div>
                      <div className="text-xs text-zinc-400">
                        {order.created_at ? new Date(order.created_at).toLocaleDateString() : ''}
                      </div>
                      {expandedId === order.id ? (
                        <ChevronUp className="w-4 h-4 text-zinc-400" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-zinc-400" />
                      )}
                    </div>
                  </button>

                  {expandedId === order.id && (
                    <div className="px-4 pb-4 border-t border-zinc-100 pt-3 space-y-4">
                      <div>
                        <div className="text-xs font-medium text-zinc-500 mb-1">Items</div>
                        <div className="space-y-1">
                          {order.items.map(item => (
                            <div key={item.id} className="flex justify-between text-sm">
                              <span className="text-zinc-700">{item.template_title || item.jurisdiction_name}</span>
                              <span className="text-zinc-500">x{item.quantity}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                        <div>
                          <span className="text-zinc-500">Requested by</span>
                          <div className="text-zinc-800 font-medium">{order.requested_by_email || '\u2014'}</div>
                        </div>
                        <div>
                          <span className="text-zinc-500">Ship to</span>
                          <div className="text-zinc-800 font-medium">{order.shipping_address || '\u2014'}</div>
                        </div>
                        {order.tracking_number && (
                          <div>
                            <span className="text-zinc-500">Tracking</span>
                            <div className="text-zinc-800 font-medium">{order.tracking_number}</div>
                          </div>
                        )}
                        {order.shipped_at && (
                          <div>
                            <span className="text-zinc-500">Shipped</span>
                            <div className="text-zinc-800 font-medium">{new Date(order.shipped_at).toLocaleDateString()}</div>
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-zinc-500 mb-1">Status</label>
                          <select
                            value={editStatus}
                            onChange={e => setEditStatus(e.target.value as PosterOrderStatus)}
                            className="w-full text-sm border border-zinc-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-matcha-500"
                          >
                            {ALL_STATUSES.map(s => (
                              <option key={s} value={s}>{s}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-zinc-500 mb-1">Quote ($)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={editQuote}
                            onChange={e => setEditQuote(e.target.value)}
                            placeholder="0.00"
                            className="w-full text-sm border border-zinc-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-matcha-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-zinc-500 mb-1">Tracking Number</label>
                          <input
                            type="text"
                            value={editTracking}
                            onChange={e => setEditTracking(e.target.value)}
                            placeholder="e.g. 1Z999AA..."
                            className="w-full text-sm border border-zinc-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-matcha-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-zinc-500 mb-1">Admin Notes</label>
                          <input
                            type="text"
                            value={editNotes}
                            onChange={e => setEditNotes(e.target.value)}
                            placeholder="Internal notes..."
                            className="w-full text-sm border border-zinc-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-matcha-500"
                          />
                        </div>
                      </div>

                      <div className="flex justify-end">
                        <button
                          onClick={() => handleSave(order.id)}
                          disabled={saving}
                          className="px-4 py-1.5 text-sm font-medium bg-matcha-600 text-white rounded hover:bg-matcha-700 disabled:opacity-50 transition-colors"
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
