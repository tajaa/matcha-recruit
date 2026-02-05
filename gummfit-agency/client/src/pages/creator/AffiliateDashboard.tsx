import { useEffect, useState } from 'react';
import {
  Link2,
  ExternalLink,
  DollarSign,
  MousePointer,
  ShoppingCart,
  TrendingUp,
  Copy,
  Check,
  BarChart3,
} from 'lucide-react';
import { api } from '../../api/client';
import type { AffiliateLink, AffiliateStats } from '../../types/campaigns';

export function AffiliateDashboard() {
  const [links, setLinks] = useState<AffiliateLink[]>([]);
  const [selectedLink, setSelectedLink] = useState<AffiliateLink | null>(null);
  const [_stats, setStats] = useState<AffiliateStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    loadLinks();
  }, []);

  useEffect(() => {
    if (selectedLink) {
      loadStats(selectedLink.id);
    }
  }, [selectedLink]);

  const loadLinks = async () => {
    try {
      const res = await api.campaigns.listAffiliateLinks();
      setLinks(res);
      if (res.length > 0) {
        setSelectedLink(res[0]);
      }
    } catch (err) {
      console.error('Failed to load affiliate links:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async (linkId: string) => {
    try {
      const res = await api.campaigns.getAffiliateLinkStats(linkId);
      setStats(res);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const copyToClipboard = async (link: AffiliateLink) => {
    const fullUrl = `${window.location.origin}/api/r/${link.short_code}`;
    await navigator.clipboard.writeText(fullUrl);
    setCopiedId(link.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const formatCurrency = (amount: number | null) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const formatPercent = (value: number) => {
    return `${(value * 100).toFixed(1)}%`;
  };

  // Calculate totals
  const totalClicks = links.reduce((sum, l) => sum + l.click_count, 0);
  const totalConversions = links.reduce((sum, l) => sum + l.conversion_count, 0);
  const totalCommission = links.reduce((sum, l) => sum + l.total_commission, 0);
  const overallConversionRate = totalClicks > 0 ? totalConversions / totalClicks : 0;

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
              Affiliate Program
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Affiliate Links
          </h1>
          <p className="text-zinc-500 mt-2 text-sm">
            Track your affiliate performance and earnings.
          </p>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <Link2 className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Links</span>
          </div>
          <div className="text-2xl font-bold text-white">{links.length}</div>
        </div>
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <MousePointer className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Clicks</span>
          </div>
          <div className="text-2xl font-bold text-blue-400">{totalClicks.toLocaleString()}</div>
        </div>
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <ShoppingCart className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Conversions</span>
          </div>
          <div className="text-2xl font-bold text-purple-400">{totalConversions.toLocaleString()}</div>
        </div>
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <TrendingUp className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Conv. Rate</span>
          </div>
          <div className="text-2xl font-bold text-amber-400">{formatPercent(overallConversionRate)}</div>
        </div>
        <div className="border border-white/10 bg-zinc-900/30 p-4">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <DollarSign className="w-4 h-4" />
            <span className="text-[10px] uppercase tracking-widest">Commission</span>
          </div>
          <div className="text-2xl font-bold text-emerald-400">{formatCurrency(totalCommission)}</div>
        </div>
      </div>

      {links.length === 0 ? (
        <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
          <Link2 className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
          <p className="text-zinc-400 mb-2">No affiliate links yet</p>
          <p className="text-xs text-zinc-600">
            Agencies will create tracking links for your campaigns.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Links List */}
          <div className="lg:col-span-2 border border-white/10 bg-zinc-900/30">
            <div className="p-4 border-b border-white/10">
              <h2 className="text-xs font-bold text-white uppercase tracking-widest">Your Links</h2>
            </div>
            <div className="divide-y divide-white/5">
              {links.map((link) => (
                <div
                  key={link.id}
                  onClick={() => setSelectedLink(link)}
                  className={`p-4 cursor-pointer transition-colors ${
                    selectedLink?.id === link.id ? 'bg-white/5' : 'hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-white truncate">
                          {link.product_name || 'Unnamed Link'}
                        </h3>
                        {!link.is_active && (
                          <span className="px-1.5 py-0.5 bg-red-500/10 text-red-400 text-[9px] uppercase">
                            Inactive
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-500 truncate mb-2">{link.destination_url}</p>
                      <div className="flex items-center gap-4 text-xs">
                        <span className="text-zinc-400">
                          <span className="text-blue-400">{link.click_count}</span> clicks
                        </span>
                        <span className="text-zinc-400">
                          <span className="text-purple-400">{link.conversion_count}</span> conversions
                        </span>
                        <span className="text-zinc-400">
                          <span className="text-emerald-400">{formatCurrency(link.total_commission)}</span> earned
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          copyToClipboard(link);
                        }}
                        className="p-2 hover:bg-white/10 transition-colors"
                        title="Copy link"
                      >
                        {copiedId === link.id ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <Copy className="w-4 h-4 text-zinc-500" />
                        )}
                      </button>
                      <a
                        href={link.destination_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="p-2 hover:bg-white/10 transition-colors"
                        title="Open destination"
                      >
                        <ExternalLink className="w-4 h-4 text-zinc-500" />
                      </a>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Selected Link Details */}
          {selectedLink && (
            <div className="space-y-6">
              {/* Link Info */}
              <div className="border border-white/10 bg-zinc-900/30 p-6">
                <h2 className="text-xs font-bold text-white uppercase tracking-widest mb-4">Link Details</h2>
                <div className="space-y-4">
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-zinc-600 mb-1">Product</div>
                    <div className="text-sm text-white">{selectedLink.product_name || 'Not specified'}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-zinc-600 mb-1">Your Tracking URL</div>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 text-xs text-blue-400 bg-zinc-800 p-2 truncate">
                        {window.location.origin}/api/r/{selectedLink.short_code}
                      </code>
                      <button
                        onClick={() => copyToClipboard(selectedLink)}
                        className="p-2 hover:bg-white/10 transition-colors"
                      >
                        {copiedId === selectedLink.id ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <Copy className="w-4 h-4 text-zinc-500" />
                        )}
                      </button>
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-zinc-600 mb-1">Commission Rate</div>
                    <div className="text-sm text-emerald-400">{selectedLink.commission_percent}%</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-widest text-zinc-600 mb-1">Agency</div>
                    <div className="text-sm text-zinc-300">{selectedLink.agency_name}</div>
                  </div>
                </div>
              </div>

              {/* Link Stats */}
              <div className="border border-white/10 bg-zinc-900/30 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xs font-bold text-white uppercase tracking-widest">Performance</h2>
                  <BarChart3 className="w-4 h-4 text-zinc-500" />
                </div>
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-400">Clicks</span>
                    <span className="text-sm font-mono text-blue-400">{selectedLink.click_count.toLocaleString()}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-400">Conversions</span>
                    <span className="text-sm font-mono text-purple-400">{selectedLink.conversion_count.toLocaleString()}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-400">Conversion Rate</span>
                    <span className="text-sm font-mono text-amber-400">
                      {selectedLink.click_count > 0
                        ? formatPercent(selectedLink.conversion_count / selectedLink.click_count)
                        : '0%'}
                    </span>
                  </div>
                  <div className="border-t border-white/10 pt-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-zinc-400">Total Sales</span>
                      <span className="text-sm font-mono text-white">{formatCurrency(selectedLink.total_sales)}</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-400">Your Commission</span>
                    <span className="text-lg font-bold text-emerald-400">{formatCurrency(selectedLink.total_commission)}</span>
                  </div>
                </div>
              </div>

              {/* Quick Actions */}
              <div className="border border-white/10 bg-zinc-900/30 p-6">
                <h2 className="text-xs font-bold text-white uppercase tracking-widest mb-4">Share</h2>
                <div className="space-y-2">
                  <button
                    onClick={() => copyToClipboard(selectedLink)}
                    className="w-full py-2 bg-white/10 text-white text-xs uppercase tracking-widest hover:bg-white/20 transition-colors flex items-center justify-center gap-2"
                  >
                    <Copy className="w-4 h-4" />
                    {copiedId === selectedLink.id ? 'Copied!' : 'Copy Link'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default AffiliateDashboard;
