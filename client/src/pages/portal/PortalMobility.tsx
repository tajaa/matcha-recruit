import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Bookmark, CheckCircle2, CircleDashed, Sparkles, XCircle } from 'lucide-react';
import { portalApi } from '../../api/portal';
import { FeatureGuideTrigger } from '../../features/feature-guides';

type ProfileVisibility = 'private' | 'hr_only' | 'manager_visible';
type FeedStatus = 'suggested' | 'saved' | 'dismissed' | 'applied';
type FeedType = 'role' | 'project';

type CareerProfile = {
  id: string;
  employee_id: string;
  org_id: string;
  target_roles: string[];
  target_departments: string[];
  skills: string[];
  interests: string[];
  mobility_opt_in: boolean;
  visibility: ProfileVisibility;
  created_at: string;
  updated_at: string;
};

type FeedItem = {
  opportunity_id: string;
  type: FeedType;
  title: string;
  department: string | null;
  description: string | null;
  match_score: number | null;
  status: FeedStatus;
  reasons?: {
    matched_skills?: string[];
    missing_skills?: string[];
    preferred_matched_skills?: string[];
    alignment_signals?: string[];
    component_scores?: Record<string, number>;
  } | null;
};

type FeedResponse = {
  items: FeedItem[];
  total: number;
};

const FEED_FILTERS = ['active'] as const;
type FeedFilter = (typeof FEED_FILTERS)[number];
const APPLY_NOTE_MAX_LENGTH = 500;

function parseCommaSeparated(value: string): string[] {
  const seen = new Set<string>();
  const parsed: string[] = [];
  for (const token of value.split(',')) {
    const trimmed = token.trim();
    if (!trimmed) continue;
    const key = trimmed.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    parsed.push(trimmed);
  }
  return parsed;
}

function formatScore(value: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'N/A';
  return `${value.toFixed(1)}%`;
}

function statusClass(status: FeedStatus): string {
  switch (status) {
    case 'applied':
      return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    case 'saved':
      return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    case 'dismissed':
      return 'bg-zinc-500/10 text-zinc-500 border-zinc-500/20';
    default:
      return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
  }
}

function statusIcon(status: FeedStatus) {
  switch (status) {
    case 'applied':
      return <CheckCircle2 className="w-3 h-3" />;
    case 'saved':
      return <Bookmark className="w-3 h-3" />;
    case 'dismissed':
      return <XCircle className="w-3 h-3" />;
    default:
      return <CircleDashed className="w-3 h-3" />;
  }
}

export default function PortalMobility() {
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [feedFilter, setFeedFilter] = useState<FeedFilter>('active');
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [loadingFeed, setLoadingFeed] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [activeApplyId, setActiveApplyId] = useState<string | null>(null);
  const [applyDrafts, setApplyDrafts] = useState<Record<string, string>>({});
  const [actionErrors, setActionErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [targetRolesInput, setTargetRolesInput] = useState('');
  const [targetDepartmentsInput, setTargetDepartmentsInput] = useState('');
  const [skillsInput, setSkillsInput] = useState('');
  const [interestsInput, setInterestsInput] = useState('');
  const [mobilityOptIn, setMobilityOptIn] = useState(true);

  const refreshProfile = useCallback(async () => {
    setLoadingProfile(true);
    try {
      const data = (await portalApi.getMobilityProfile()) as CareerProfile;
      setProfile(data);
      setTargetRolesInput(data.target_roles.join(', '));
      setTargetDepartmentsInput(data.target_departments.join(', '));
      setSkillsInput(data.skills.join(', '));
      setInterestsInput(data.interests.join(', '));
      setMobilityOptIn(data.mobility_opt_in);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load mobility profile');
    } finally {
      setLoadingProfile(false);
    }
  }, []);

  const refreshFeed = useCallback(async () => {
    setLoadingFeed(true);
    try {
      const data = (await portalApi.getMobilityFeed(feedFilter)) as FeedResponse;
      setFeed(data.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load mobility opportunities');
    } finally {
      setLoadingFeed(false);
    }
  }, [feedFilter]);

  useEffect(() => {
    void refreshProfile();
  }, [refreshProfile]);

  useEffect(() => {
    void refreshFeed();
  }, [refreshFeed]);

  const statusCounts = useMemo(() => {
    return feed.reduce<Record<FeedStatus, number>>(
      (acc, item) => {
        acc[item.status] += 1;
        return acc;
      },
      {
        suggested: 0,
        saved: 0,
        dismissed: 0,
        applied: 0,
      },
    );
  }, [feed]);

  const handleSaveProfile = async () => {
    setSavingProfile(true);
    setError(null);
    setNotice(null);
    try {
      const updated = (await portalApi.updateMobilityProfile({
        target_roles: parseCommaSeparated(targetRolesInput),
        target_departments: parseCommaSeparated(targetDepartmentsInput),
        skills: parseCommaSeparated(skillsInput),
        interests: parseCommaSeparated(interestsInput),
        mobility_opt_in: mobilityOptIn,
      })) as CareerProfile;
      setProfile(updated);
      setTargetRolesInput(updated.target_roles.join(', '));
      setTargetDepartmentsInput(updated.target_departments.join(', '));
      setSkillsInput(updated.skills.join(', '));
      setInterestsInput(updated.interests.join(', '));
      setMobilityOptIn(updated.mobility_opt_in);
      setNotice('Mobility profile updated.');
      await refreshFeed();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update profile');
    } finally {
      setSavingProfile(false);
    }
  };

  const setFeedItemStatus = useCallback((opportunityId: string, status: FeedStatus) => {
    setFeed((current) =>
      current.map((entry) =>
        entry.opportunity_id === opportunityId
          ? {
              ...entry,
              status,
            }
          : entry,
      ),
    );
  }, []);

  const clearActionError = useCallback((opportunityId: string) => {
    setActionErrors((current) => {
      if (!(opportunityId in current)) return current;
      const next = { ...current };
      delete next[opportunityId];
      return next;
    });
  }, []);

  const handleFeedAction = async (
    item: FeedItem,
    action: 'save' | 'unsave' | 'dismiss' | 'apply',
    employeeNotes?: string,
  ) => {
    setActionKey(`${action}:${item.opportunity_id}`);
    clearActionError(item.opportunity_id);
    setNotice(null);

    if (action === 'apply' && employeeNotes && employeeNotes.length > APPLY_NOTE_MAX_LENGTH) {
      setActionErrors((current) => ({
        ...current,
        [item.opportunity_id]: `Notes must be ${APPLY_NOTE_MAX_LENGTH} characters or fewer.`,
      }));
      setActionKey(null);
      return;
    }

    const previousFeed = feed;
    const optimisticStatus: FeedStatus =
      action === 'save' ? 'saved' : action === 'unsave' ? 'suggested' : action === 'dismiss' ? 'dismissed' : 'applied';

    setFeedItemStatus(item.opportunity_id, optimisticStatus);
    if (action === 'apply') {
      setActiveApplyId(null);
    }

    try {
      if (action === 'save') {
        const response = (await portalApi.saveMobilityOpportunity(item.opportunity_id)) as {
          status?: FeedStatus;
        };
        if (response.status) {
          setFeedItemStatus(item.opportunity_id, response.status);
        }
        setNotice('Opportunity saved.');
      } else if (action === 'unsave') {
        const response = (await portalApi.unsaveMobilityOpportunity(item.opportunity_id)) as {
          status?: FeedStatus;
        };
        if (response.status) {
          setFeedItemStatus(item.opportunity_id, response.status);
        }
        setNotice('Opportunity moved back to suggested.');
      } else if (action === 'dismiss') {
        const response = (await portalApi.dismissMobilityOpportunity(item.opportunity_id)) as {
          status?: FeedStatus;
        };
        if (response.status) {
          setFeedItemStatus(item.opportunity_id, response.status);
        }
        setNotice('Opportunity dismissed.');
      } else {
        await portalApi.applyMobilityOpportunity(item.opportunity_id, employeeNotes || undefined);
        setFeedItemStatus(item.opportunity_id, 'applied');
        setApplyDrafts((current) => ({
          ...current,
          [item.opportunity_id]: '',
        }));
        setNotice('Application submitted.');
      }
    } catch (err) {
      setFeed(previousFeed);
      setActionErrors((current) => ({
        ...current,
        [item.opportunity_id]: err instanceof Error ? err.message : 'Failed to update opportunity',
      }));
    } finally {
      setActionKey(null);
    }
  };

  if (loadingProfile && !profile) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-zinc-600 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4 flex-wrap border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-3" data-tour="portal-mobility-guide">
            <h1 className="text-2xl font-bold tracking-tight text-white uppercase">Internal Mobility</h1>
            <FeatureGuideTrigger guideId="portal-mobility" variant="light" />
          </div>
          <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
            Set your growth goals and explore internal opportunities privately.
          </p>
        </div>
        <button
          onClick={() => void handleSaveProfile()}
          disabled={savingProfile}
          className="inline-flex items-center gap-2 px-6 py-2 bg-white text-black text-[10px] uppercase tracking-widest font-bold border border-white hover:bg-zinc-200 transition-colors disabled:opacity-60"
        >
          <Sparkles className="w-4 h-4" />
          {savingProfile ? 'Saving...' : 'Save Mobility Profile'}
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <span className="text-red-400 font-mono text-sm uppercase">{error}</span>
        </div>
      )}
      {notice && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 p-4 flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
          <span className="text-emerald-400 font-mono text-sm uppercase">{notice}</span>
        </div>
      )}

      <section className="bg-zinc-900/30 border border-white/10" data-tour="portal-mobility-profile">
        <div className="px-6 py-4 border-b border-white/10 bg-white/5 flex items-center justify-between">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Career Interests</h2>
          <div className="text-[9px] text-zinc-500 font-mono uppercase tracking-widest">
            Visibility: <span className="text-white font-bold">{profile?.visibility || 'private'}</span>
          </div>
        </div>
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-8">
          <label className="space-y-2">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest ml-1">Target Roles</span>
            <input
              type="text"
              value={targetRolesInput}
              onChange={(event) => setTargetRolesInput(event.target.value)}
              placeholder="Product Manager, Operations Lead"
              className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
            />
          </label>
          <label className="space-y-2">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest ml-1">Target Departments</span>
            <input
              type="text"
              value={targetDepartmentsInput}
              onChange={(event) => setTargetDepartmentsInput(event.target.value)}
              placeholder="Data, Product, Operations"
              className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none font-mono"
            />
          </label>
          <label className="space-y-2">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest ml-1">Skills</span>
            <textarea
              rows={3}
              value={skillsInput}
              onChange={(event) => setSkillsInput(event.target.value)}
              placeholder="SQL, Python, stakeholder communication"
              className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none font-mono leading-relaxed"
            />
          </label>
          <label className="space-y-2">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest ml-1">Interests</span>
            <textarea
              rows={3}
              value={interestsInput}
              onChange={(event) => setInterestsInput(event.target.value)}
              placeholder="Forecasting, experimentation, team leadership"
              className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none font-mono leading-relaxed"
            />
          </label>
        </div>
        <div className="px-6 py-4 border-t border-white/5 bg-white/5">
            <label className="inline-flex items-center gap-3 text-[10px] font-bold text-zinc-400 uppercase tracking-widest cursor-pointer group">
            <input
                type="checkbox"
                checked={mobilityOptIn}
                onChange={(event) => setMobilityOptIn(event.target.checked)}
                className="w-4 h-4 rounded-none border-zinc-700 bg-zinc-900 text-white focus:ring-0 focus:ring-offset-0"
            />
            <span className="group-hover:text-white transition-colors">Receive proactive internal mobility recommendations</span>
            </label>
        </div>
      </section>

      <section className="bg-zinc-900/30 border border-white/10">
        <div className="px-6 py-4 border-b border-white/10 bg-white/5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Opportunity Feed</h2>
            <p className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest mt-1">
              Suggested: {statusCounts.suggested} &bull; Saved: {statusCounts.saved} &bull; Applied: {statusCounts.applied} &bull;
              Dismissed: {statusCounts.dismissed}
            </p>
          </div>
          <div className="flex items-center gap-3" data-tour="portal-mobility-feed-filter">
            <label className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">Filter Status</label>
            <select
              value={feedFilter}
              onChange={(event) => setFeedFilter(event.target.value as FeedFilter)}
              className="bg-zinc-950 border border-zinc-800 text-white px-4 py-2 text-[10px] font-bold uppercase tracking-widest outline-none focus:border-white transition-colors appearance-none"
            >
              {FEED_FILTERS.map((value) => (
                <option key={value} value={value}>
                  {value.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="p-6">
            {loadingFeed ? (
            <div className="text-xs text-zinc-500 font-mono uppercase tracking-widest py-12 text-center animate-pulse">Scanning opportunities...</div>
            ) : !mobilityOptIn ? (
            <div className="text-sm text-zinc-600 font-mono uppercase tracking-widest py-12 text-center max-w-lg mx-auto leading-relaxed">
                Mobility recommendations are paused. Turn the setting back on and save your profile to resume suggestions.
            </div>
            ) : feed.length === 0 ? (
            <div className="text-sm text-zinc-600 font-mono uppercase tracking-widest py-12 text-center">No active opportunities matching your profile at this time.</div>
            ) : (
            <div className="space-y-6">
                {feed.map((item) => (
                <article
                    key={item.opportunity_id}
                    className="bg-zinc-950/50 border border-white/10 p-6 hover:border-white/20 transition-all group"
                    data-tour="portal-mobility-card"
                >
                    <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                        <h3 className="text-base font-bold text-white tracking-tight">{item.title}</h3>
                        <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[9px] uppercase tracking-widest font-bold border ${statusClass(
                            item.status,
                            )}`}
                        >
                            {statusIcon(item.status)}
                            {item.status}
                        </span>
                        </div>
                        <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mt-2 flex items-center gap-2">
                        <span className="text-zinc-400">{(item.department || 'No department')}</span>
                        <span className="w-1 h-1 bg-zinc-800 rounded-full" />
                        <span>{item.type}</span>
                        </div>
                    </div>
                    <div className="text-right">
                        <div className="text-[9px] text-zinc-600 font-mono uppercase tracking-widest">Match Score</div>
                        <div className="text-2xl font-bold text-emerald-400 tabular-nums">{formatScore(item.match_score)}</div>
                    </div>
                    </div>

                    {item.description && (
                    <p className="text-[11px] text-zinc-400 mt-4 leading-relaxed font-mono uppercase tracking-wide line-clamp-3">{item.description}</p>
                    )}

                    {(item.reasons?.matched_skills?.length || item.reasons?.missing_skills?.length) && (
                    <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-[10px] font-mono uppercase tracking-widest">
                        {item.reasons?.matched_skills && item.reasons.matched_skills.length > 0 && (
                        <div className="p-3 bg-emerald-500/5 border border-emerald-500/10">
                            <span className="text-emerald-500 font-bold block mb-1">Matched Skills</span>
                            <span className="text-zinc-500 leading-relaxed">{item.reasons.matched_skills.join(', ')}</span>
                        </div>
                        )}
                        {item.reasons?.missing_skills && item.reasons.missing_skills.length > 0 && (
                        <div className="p-3 bg-amber-500/5 border border-amber-500/10">
                            <span className="text-amber-500 font-bold block mb-1">Missing Skills</span>
                            <span className="text-zinc-500 leading-relaxed">{item.reasons.missing_skills.join(', ')}</span>
                        </div>
                        )}
                    </div>
                    )}

                    <div className="mt-6 flex flex-wrap gap-3 border-t border-white/5 pt-6" data-tour="portal-mobility-actions">
                    {item.status === 'saved' ? (
                        <button
                        type="button"
                        onClick={() => void handleFeedAction(item, 'unsave')}
                        disabled={actionKey === `unsave:${item.opportunity_id}`}
                        className="px-6 py-2 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white hover:border-white transition-colors disabled:opacity-60"
                        >
                        {actionKey === `unsave:${item.opportunity_id}` ? 'Updating...' : 'Unsave'}
                        </button>
                    ) : (
                        <button
                        type="button"
                        onClick={() => void handleFeedAction(item, 'save')}
                        disabled={actionKey === `save:${item.opportunity_id}` || item.status === 'applied'}
                        className="px-6 py-2 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white hover:border-white transition-colors disabled:opacity-60"
                        >
                        {actionKey === `save:${item.opportunity_id}` ? 'Saving...' : 'Save'}
                        </button>
                    )}
                    <button
                        type="button"
                        onClick={() => void handleFeedAction(item, 'dismiss')}
                        disabled={actionKey === `dismiss:${item.opportunity_id}` || item.status === 'applied'}
                        className="px-6 py-2 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white hover:border-white transition-colors disabled:opacity-60"
                    >
                        {actionKey === `dismiss:${item.opportunity_id}` ? 'Updating...' : 'Dismiss'}
                    </button>
                    <button
                        type="button"
                        onClick={() => {
                        setActiveApplyId((current) =>
                            current === item.opportunity_id ? null : item.opportunity_id,
                        );
                        }}
                        disabled={actionKey === `apply:${item.opportunity_id}` || item.status === 'applied'}
                        className={`px-8 py-2 text-[10px] font-bold uppercase tracking-widest border transition-colors disabled:opacity-60 ${
                            item.status === 'applied' 
                                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 cursor-default' 
                                : activeApplyId === item.opportunity_id
                                    ? 'bg-zinc-800 border-zinc-700 text-white'
                                    : 'bg-white border-white text-black hover:bg-zinc-200'
                        }`}
                    >
                        {item.status === 'applied'
                        ? 'Application Active'
                        : activeApplyId === item.opportunity_id
                            ? 'Close Panel'
                            : 'Apply Now'}
                    </button>
                    </div>

                    {activeApplyId === item.opportunity_id && item.status !== 'applied' && (
                    <div
                        className="mt-6 p-6 bg-zinc-900 border border-dashed border-white/10 space-y-6 animate-in slide-in-from-top-2 duration-200"
                        data-tour="portal-mobility-apply"
                    >
                        <div className="space-y-4">
                        <label className="block space-y-2">
                            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest ml-1">
                                Growth Statement / Application Note (Optional)
                            </span>
                            <textarea
                                rows={4}
                                value={applyDrafts[item.opportunity_id] || ''}
                                onChange={(event) =>
                                setApplyDrafts((current) => ({
                                    ...current,
                                    [item.opportunity_id]: event.target.value,
                                }))
                                }
                                placeholder="Briefly describe why this role or project aligns with your growth goals within the organization."
                                maxLength={APPLY_NOTE_MAX_LENGTH}
                                className="w-full bg-zinc-950 border border-zinc-800 text-white px-4 py-3 text-sm focus:border-white transition-colors outline-none resize-none font-mono leading-relaxed"
                            />
                            <div
                                className={`text-[9px] font-mono uppercase text-right tracking-widest ${
                                (applyDrafts[item.opportunity_id] || '').length >= APPLY_NOTE_MAX_LENGTH
                                    ? 'text-red-500'
                                    : 'text-zinc-600'
                                }`}
                            >
                                {(applyDrafts[item.opportunity_id] || '').length} / {APPLY_NOTE_MAX_LENGTH}
                            </div>
                        </label>
                        </div>
                        <div className="flex flex-wrap gap-4 pt-4 border-t border-white/5">
                        <button
                            type="button"
                            onClick={() => setActiveApplyId(null)}
                            className="px-6 py-3 border border-white/10 text-[10px] font-bold uppercase tracking-widest text-zinc-500 hover:text-white transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={() =>
                            void handleFeedAction(
                                item,
                                'apply',
                                (applyDrafts[item.opportunity_id] || '').trim() || undefined,
                            )
                        }
                            disabled={actionKey === `apply:${item.opportunity_id}`}
                            className="px-8 py-3 bg-white text-black text-[10px] font-bold uppercase tracking-widest border border-white hover:bg-zinc-200 transition-colors disabled:opacity-60"
                        >
                            {actionKey === `apply:${item.opportunity_id}` ? 'Processing...' : 'Submit Internal Application'}
                        </button>
                        </div>
                    </div>
                    )}

                    {actionErrors[item.opportunity_id] && (
                    <div className="mt-4 p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-mono uppercase tracking-widest">
                        Error: {actionErrors[item.opportunity_id]}
                    </div>
                    )}
                </article>
                ))}
            </div>
            )}
        </div>
      </section>
    </div>
  );
}
