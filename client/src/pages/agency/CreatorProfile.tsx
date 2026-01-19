import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  User,
  Users,
  TrendingUp,
  ExternalLink,
  Instagram,
  Youtube,
  Twitter,
  Music2,
  Tv,
  CheckCircle,
  Send,
} from 'lucide-react';
import { api } from '../../api/client';
import type { CreatorPublic } from '../../types/creator';

// Platform icon mapping
const platformIcons: Record<string, React.ReactNode> = {
  instagram: <Instagram className="w-4 h-4" />,
  youtube: <Youtube className="w-4 h-4" />,
  twitter: <Twitter className="w-4 h-4" />,
  tiktok: <Music2 className="w-4 h-4" />,
  twitch: <Tv className="w-4 h-4" />,
  spotify: <Music2 className="w-4 h-4" />,
  patreon: <Users className="w-4 h-4" />,
};

const platformColors: Record<string, string> = {
  instagram: 'text-pink-400',
  youtube: 'text-red-400',
  twitter: 'text-blue-400',
  tiktok: 'text-cyan-400',
  twitch: 'text-purple-400',
  spotify: 'text-green-400',
  patreon: 'text-orange-400',
};

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}

export function CreatorProfile() {
  const { creatorId } = useParams();
  const navigate = useNavigate();
  const [creator, setCreator] = useState<CreatorPublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (creatorId) {
      loadCreator();
    }
  }, [creatorId]);

  const loadCreator = async () => {
    try {
      const res = await api.creators.getPublicProfile(creatorId!);
      setCreator(res);
    } catch (err) {
      setError('Creator not found');
      console.error('Failed to load creator:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
      </div>
    );
  }

  if (error || !creator) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <p className="text-zinc-400">{error || 'Creator not found'}</p>
        <button
          onClick={() => navigate('/app/agency/creators')}
          className="text-sm text-blue-400 hover:text-blue-300"
        >
          Back to Creator Discovery
        </button>
      </div>
    );
  }

  const metrics = (creator.metrics || {}) as {
    total_followers?: number;
    avg_engagement_rate?: number;
    platforms?: Record<string, any>;
  };
  const platforms = metrics.platforms || {};
  const totalFollowers = metrics.total_followers || 0;
  const avgEngagement = metrics.avg_engagement_rate || 0;

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/app/agency/creators')}
          className="p-2 hover:bg-white/10 transition-colors"
        >
          <ArrowLeft className="w-5 h-5 text-zinc-400" />
        </button>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
            Creator Profile
          </div>
          <h1 className="text-2xl font-bold text-white">{creator.display_name}</h1>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Profile Card */}
        <div className="lg:col-span-2 space-y-6">
          {/* Profile Header */}
          <div className="border border-white/10 bg-zinc-900/30 p-6">
            <div className="flex items-start gap-6">
              {/* Profile Image */}
              <div className="flex-shrink-0">
                {creator.profile_image_url ? (
                  <img
                    src={creator.profile_image_url}
                    alt={creator.display_name}
                    className="w-24 h-24 rounded-full object-cover border-2 border-white/10"
                  />
                ) : (
                  <div className="w-24 h-24 rounded-full bg-zinc-800 flex items-center justify-center border-2 border-white/10">
                    <User className="w-10 h-10 text-zinc-600" />
                  </div>
                )}
              </div>

              {/* Profile Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-2">
                  <h2 className="text-xl font-bold text-white">{creator.display_name}</h2>
                  {creator.is_verified && (
                    <span className="flex items-center gap-1 px-2 py-0.5 bg-blue-500/10 text-blue-400 text-[10px] uppercase tracking-widest">
                      <CheckCircle className="w-3 h-3" />
                      Verified
                    </span>
                  )}
                </div>

                {creator.bio && (
                  <p className="text-sm text-zinc-400 mb-4 line-clamp-3">{creator.bio}</p>
                )}

                {/* Niches */}
                {creator.niches && creator.niches.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {creator.niches.map((niche) => (
                      <span
                        key={niche}
                        className="px-2 py-1 bg-white/5 text-zinc-300 text-xs"
                      >
                        {niche}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Stats Overview */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="border border-white/10 bg-zinc-900/30 p-4">
              <div className="flex items-center gap-2 text-zinc-500 mb-2">
                <Users className="w-4 h-4" />
                <span className="text-[10px] uppercase tracking-widest">Total Reach</span>
              </div>
              <div className="text-2xl font-bold text-white">{formatNumber(totalFollowers)}</div>
            </div>
            <div className="border border-white/10 bg-zinc-900/30 p-4">
              <div className="flex items-center gap-2 text-zinc-500 mb-2">
                <TrendingUp className="w-4 h-4" />
                <span className="text-[10px] uppercase tracking-widest">Engagement</span>
              </div>
              <div className="text-2xl font-bold text-emerald-400">{avgEngagement}%</div>
            </div>
            <div className="border border-white/10 bg-zinc-900/30 p-4">
              <div className="flex items-center gap-2 text-zinc-500 mb-2">
                <ExternalLink className="w-4 h-4" />
                <span className="text-[10px] uppercase tracking-widest">Platforms</span>
              </div>
              <div className="text-2xl font-bold text-blue-400">{Object.keys(platforms).length}</div>
            </div>
            <div className="border border-white/10 bg-zinc-900/30 p-4">
              <div className="flex items-center gap-2 text-zinc-500 mb-2">
                <CheckCircle className="w-4 h-4" />
                <span className="text-[10px] uppercase tracking-widest">Status</span>
              </div>
              <div className="text-lg font-bold text-white">
                {creator.is_verified ? 'Verified' : 'Active'}
              </div>
            </div>
          </div>

          {/* Platform Breakdown */}
          {Object.keys(platforms).length > 0 && (
            <div className="border border-white/10 bg-zinc-900/30">
              <div className="p-4 border-b border-white/10">
                <h3 className="text-xs font-bold text-white uppercase tracking-widest">
                  Platform Breakdown
                </h3>
              </div>
              <div className="divide-y divide-white/5">
                {Object.entries(platforms).map(([platform, data]: [string, any]) => (
                  <div key={platform} className="p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={platformColors[platform] || 'text-zinc-400'}>
                        {platformIcons[platform] || <ExternalLink className="w-4 h-4" />}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-white capitalize">{platform}</div>
                        {data.username && (
                          <div className="text-xs text-zinc-500">@{data.username}</div>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-white">
                        {formatNumber(data.followers || 0)}
                      </div>
                      <div className="text-xs text-zinc-500">followers</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Demographics */}
          {creator.audience_demographics && Object.keys(creator.audience_demographics).length > 0 && (
            <div className="border border-white/10 bg-zinc-900/30">
              <div className="p-4 border-b border-white/10">
                <h3 className="text-xs font-bold text-white uppercase tracking-widest">
                  Audience Demographics
                </h3>
              </div>
              <div className="p-4">
                <pre className="text-xs text-zinc-400 whitespace-pre-wrap">
                  {JSON.stringify(creator.audience_demographics, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar - Actions */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <div className="border border-white/10 bg-zinc-900/30 p-6">
            <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-4">
              Actions
            </h3>
            <div className="space-y-3">
              <button
                onClick={() => navigate(`/app/agency/campaigns?invite=${creator.id}`)}
                className="w-full py-3 bg-white text-black text-xs uppercase tracking-widest font-bold hover:bg-zinc-200 transition-colors flex items-center justify-center gap-2"
              >
                <Send className="w-4 h-4" />
                Invite to Campaign
              </button>
              <button
                onClick={() => navigate(`/app/agency/deals?invite=${creator.id}`)}
                className="w-full py-3 bg-white/10 text-white text-xs uppercase tracking-widest hover:bg-white/20 transition-colors"
              >
                Send Deal Offer
              </button>
            </div>
          </div>

          {/* Contact Info - Placeholder */}
          <div className="border border-white/10 bg-zinc-900/30 p-6">
            <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-4">
              Estimated Value
            </h3>
            <div className="text-center py-4">
              <div className="text-3xl font-bold text-emerald-400 mb-1">
                ${totalFollowers > 0 ? Math.round(totalFollowers * 0.01).toLocaleString() : '—'}
              </div>
              <div className="text-xs text-zinc-500">per sponsored post</div>
              <div className="text-[10px] text-zinc-600 mt-2">
                Based on {formatNumber(totalFollowers)} total followers
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CreatorProfile;
