import { useEffect, useState } from 'react';
import {
  Link2,
  Youtube,
  Music,
  Instagram,
  Twitter,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Clock,
  ExternalLink,
  Trash2
} from 'lucide-react';
import { api } from '../../api/client';
import type { PlatformConnection, Platform } from '../../types/creator';

export function PlatformConnections() {
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);

  useEffect(() => {
    loadConnections();
  }, []);

  const loadConnections = async () => {
    try {
      const res = await api.creators.listPlatformConnections();
      setConnections(res);
    } catch (err) {
      console.error('Failed to load connections:', err);
    } finally {
      setLoading(false);
    }
  };

  const syncPlatform = async (connectionId: string) => {
    setSyncing(connectionId);
    try {
      // TODO: Implement platform sync endpoint
      console.log('Syncing platform:', connectionId);
      await new Promise(resolve => setTimeout(resolve, 1000));
      await loadConnections();
    } catch (err) {
      console.error('Failed to sync:', err);
    } finally {
      setSyncing(null);
    }
  };

  const disconnectPlatform = async (connectionId: string) => {
    if (!confirm('Disconnect this platform? Historical data will be preserved.')) return;
    try {
      await api.creators.disconnectPlatform(connectionId);
      await loadConnections();
    } catch (err) {
      console.error('Failed to disconnect:', err);
    }
  };

  const getPlatformIcon = (platform: Platform) => {
    switch (platform) {
      case 'youtube': return Youtube;
      case 'spotify':
      case 'patreon': return Music;
      case 'instagram': return Instagram;
      case 'twitter': return Twitter;
      case 'tiktok': return Music;
      case 'twitch': return Music;
      default: return Link2;
    }
  };

  const getPlatformColor = (platform: Platform) => {
    switch (platform) {
      case 'youtube': return 'text-red-500 bg-red-500/10';
      case 'patreon': return 'text-orange-500 bg-orange-500/10';
      case 'tiktok': return 'text-pink-500 bg-pink-500/10';
      case 'instagram': return 'text-purple-500 bg-purple-500/10';
      case 'twitch': return 'text-violet-500 bg-violet-500/10';
      case 'twitter': return 'text-sky-500 bg-sky-500/10';
      case 'spotify': return 'text-green-500 bg-green-500/10';
      default: return 'text-zinc-500 bg-zinc-500/10';
    }
  };

  const getSyncStatusIcon = (status: string) => {
    switch (status) {
      case 'synced': return { icon: CheckCircle2, color: 'text-emerald-500' };
      case 'syncing': return { icon: RefreshCw, color: 'text-blue-500' };
      case 'failed': return { icon: AlertCircle, color: 'text-red-500' };
      case 'pending': return { icon: Clock, color: 'text-amber-500' };
      default: return { icon: Clock, color: 'text-zinc-500' };
    }
  };

  const availablePlatforms: { platform: Platform; name: string; description: string }[] = [
    { platform: 'youtube', name: 'YouTube', description: 'Channel stats, analytics, AdSense revenue' },
    { platform: 'patreon', name: 'Patreon', description: 'Patron count, earnings, pledge history' },
    { platform: 'tiktok', name: 'TikTok', description: 'Follower count, video performance' },
    { platform: 'instagram', name: 'Instagram', description: 'Followers, engagement rate' },
    { platform: 'twitch', name: 'Twitch', description: 'Subscribers, bits, ad revenue' },
    { platform: 'twitter', name: 'Twitter/X', description: 'Followers, engagement metrics' },
    { platform: 'spotify', name: 'Spotify', description: 'Listener stats, royalties' },
  ];

  const connectedPlatforms = connections.map(c => c.platform);
  const unconnectedPlatforms = availablePlatforms.filter(p => !connectedPlatforms.includes(p.platform));

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
            <div className="px-2 py-1 border border-blue-500/20 bg-blue-900/10 text-blue-400 text-[9px] uppercase tracking-widest font-mono rounded">
              Platform Integrations
            </div>
          </div>
          <h1 className="text-5xl font-bold tracking-tighter text-white uppercase">
            Connections
          </h1>
        </div>
      </div>

      {/* Connected Platforms */}
      <div>
        <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-6">
          Connected Platforms
        </h2>

        {connections.length === 0 ? (
          <div className="border border-white/10 bg-zinc-900/30 p-12 text-center">
            <Link2 className="w-12 h-12 mx-auto mb-4 text-zinc-600" />
            <p className="text-zinc-400 mb-2">No platforms connected yet</p>
            <p className="text-xs text-zinc-600">
              Connect your creator accounts to automatically import analytics and revenue data
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {connections.map((conn) => {
              const Icon = getPlatformIcon(conn.platform);
              const colorClass = getPlatformColor(conn.platform);
              const status = getSyncStatusIcon(conn.sync_status);
              const StatusIcon = status.icon;

              return (
                <div
                  key={conn.id}
                  className="border border-white/10 bg-zinc-900/30 p-6 hover:border-white/20 transition-colors group"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-4">
                      <div className={`p-3 rounded ${colorClass}`}>
                        <Icon className="w-6 h-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-medium text-white capitalize">{conn.platform}</h3>
                        {conn.platform_username && (
                          <p className="text-sm text-zinc-500">@{conn.platform_username}</p>
                        )}
                      </div>
                    </div>
                    <div className={`flex items-center gap-2 ${status.color}`}>
                      <StatusIcon className={`w-4 h-4 ${conn.sync_status === 'syncing' ? 'animate-spin' : ''}`} />
                      <span className="text-xs capitalize">{conn.sync_status}</span>
                    </div>
                  </div>

                  {conn.sync_error && (
                    <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 text-xs text-red-400">
                      {conn.sync_error}
                    </div>
                  )}

                  {conn.last_synced_at && (
                    <p className="text-[10px] text-zinc-600 mb-4">
                      Last synced: {new Date(conn.last_synced_at).toLocaleString()}
                    </p>
                  )}

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => syncPlatform(conn.id)}
                      disabled={syncing === conn.id}
                      className="flex-1 px-4 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white/5 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                    >
                      <RefreshCw className={`w-3 h-3 ${syncing === conn.id ? 'animate-spin' : ''}`} />
                      Sync Now
                    </button>
                    <button
                      onClick={() => disconnectPlatform(conn.id)}
                      className="p-2 border border-white/20 hover:bg-red-500/10 hover:border-red-500/30 text-zinc-400 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Available Platforms */}
      {unconnectedPlatforms.length > 0 && (
        <div>
          <h2 className="text-xs font-bold text-white uppercase tracking-[0.2em] mb-6">
            Available Platforms
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {unconnectedPlatforms.map((p) => {
              const Icon = getPlatformIcon(p.platform);
              const colorClass = getPlatformColor(p.platform);

              return (
                <button
                  key={p.platform}
                  onClick={() => {
                    // TODO: Implement OAuth flow
                    alert(`OAuth flow for ${p.name} coming soon!`);
                  }}
                  className="border border-white/10 bg-zinc-900/30 p-6 hover:border-white/30 hover:bg-zinc-800/50 transition-all text-left group"
                >
                  <div className="flex items-center gap-4 mb-3">
                    <div className={`p-3 rounded ${colorClass} group-hover:scale-110 transition-transform`}>
                      <Icon className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-medium text-white">{p.name}</h3>
                    </div>
                  </div>
                  <p className="text-xs text-zinc-500 mb-4">{p.description}</p>
                  <div className="flex items-center gap-2 text-xs text-blue-400 group-hover:text-blue-300">
                    <ExternalLink className="w-3 h-3" />
                    Connect
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Info Section */}
      <div className="border border-white/10 bg-zinc-900/30 p-6">
        <h3 className="text-sm font-bold text-white mb-3">About Platform Connections</h3>
        <div className="text-xs text-zinc-500 space-y-2">
          <p>
            Connecting your platforms allows automatic import of analytics, follower counts,
            and revenue data. This helps provide accurate metrics for brand deal matching.
          </p>
          <p>
            Your credentials are securely encrypted and we only request read-only access
            to your analytics data. You can disconnect any platform at any time.
          </p>
        </div>
      </div>
    </div>
  );
}

export default PlatformConnections;
