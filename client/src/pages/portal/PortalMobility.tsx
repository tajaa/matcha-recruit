import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Bookmark, CheckCircle2, CircleDashed, Sparkles, XCircle } from 'lucide-react';
import { portalApi } from '../../api/portal';

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

const FEED_FILTERS = ['active', 'draft', 'closed'] as const;
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
      return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    case 'saved':
      return 'bg-blue-100 text-blue-700 border-blue-200';
    case 'dismissed':
      return 'bg-zinc-100 text-zinc-700 border-zinc-200';
    default:
      return 'bg-amber-100 text-amber-700 border-amber-200';
  }
}

function statusIcon(status: FeedStatus) {
  switch (status) {
    case 'applied':
      return <CheckCircle2 className="w-4 h-4" />;
    case 'saved':
      return <Bookmark className="w-4 h-4" />;
    case 'dismissed':
      return <XCircle className="w-4 h-4" />;
    default:
      return <CircleDashed className="w-4 h-4" />;
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
          <div className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse" />
          <span className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Loading</span>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-mono font-medium text-zinc-900">Internal Mobility</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Set your growth goals and explore internal opportunities privately.
          </p>
        </div>
        <button
          onClick={() => void handleSaveProfile()}
          disabled={savingProfile}
          className="inline-flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-medium rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-60"
        >
          <Sparkles className="w-4 h-4" />
          {savingProfile ? 'Saving...' : 'Save Mobility Profile'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-500" />
          <span className="text-red-700">{error}</span>
        </div>
      )}
      {notice && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          <span className="text-emerald-700">{notice}</span>
        </div>
      )}

      <section className="bg-white border border-zinc-200 rounded-lg p-5 md:p-6 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Career Interests</h2>
          <div className="text-xs text-zinc-500">
            Visibility: <span className="font-medium text-zinc-700">{profile?.visibility || 'private'}</span>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">Target Roles</span>
            <input
              type="text"
              value={targetRolesInput}
              onChange={(event) => setTargetRolesInput(event.target.value)}
              placeholder="Product Manager, Operations Lead"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
            />
          </label>
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">Target Departments</span>
            <input
              type="text"
              value={targetDepartmentsInput}
              onChange={(event) => setTargetDepartmentsInput(event.target.value)}
              placeholder="Data, Product, Operations"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900"
            />
          </label>
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">Skills</span>
            <textarea
              rows={3}
              value={skillsInput}
              onChange={(event) => setSkillsInput(event.target.value)}
              placeholder="SQL, Python, stakeholder communication"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900 resize-y"
            />
          </label>
          <label className="space-y-2">
            <span className="text-sm font-medium text-zinc-700">Interests</span>
            <textarea
              rows={3}
              value={interestsInput}
              onChange={(event) => setInterestsInput(event.target.value)}
              placeholder="Forecasting, experimentation, team leadership"
              className="w-full px-4 py-3 border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-zinc-900 resize-y"
            />
          </label>
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-zinc-700">
          <input
            type="checkbox"
            checked={mobilityOptIn}
            onChange={(event) => setMobilityOptIn(event.target.checked)}
            className="w-4 h-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900"
          />
          Receive proactive internal mobility recommendations
        </label>
      </section>

      <section className="bg-white border border-zinc-200 rounded-lg p-5 md:p-6 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-mono uppercase tracking-wider text-zinc-500">Opportunity Feed</h2>
            <p className="text-xs text-zinc-500 mt-1">
              Suggested: {statusCounts.suggested} | Saved: {statusCounts.saved} | Applied: {statusCounts.applied} |
              Dismissed: {statusCounts.dismissed}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-zinc-600">Role Status</label>
            <select
              value={feedFilter}
              onChange={(event) => setFeedFilter(event.target.value as FeedFilter)}
              className="px-3 py-2 border border-zinc-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900"
            >
              {FEED_FILTERS.map((value) => (
                <option key={value} value={value}>
                  {value[0].toUpperCase() + value.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {loadingFeed ? (
          <div className="text-xs text-zinc-500 font-mono uppercase tracking-wider py-6">Loading opportunities...</div>
        ) : feed.length === 0 ? (
          <div className="text-sm text-zinc-500 py-6">No opportunities are currently available for this filter.</div>
        ) : (
          <div className="space-y-4">
            {feed.map((item) => (
              <article key={item.opportunity_id} className="border border-zinc-200 rounded-lg p-4 md:p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-base font-medium text-zinc-900 truncate">{item.title}</h3>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] border rounded ${statusClass(
                          item.status,
                        )}`}
                      >
                        {statusIcon(item.status)}
                        {item.status}
                      </span>
                    </div>
                    <div className="text-sm text-zinc-500 mt-1">
                      {(item.department || 'No department')} | {item.type}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-zinc-500 font-mono uppercase tracking-wider">Match Score</div>
                    <div className="text-lg font-semibold text-zinc-900">{formatScore(item.match_score)}</div>
                  </div>
                </div>

                {item.description && (
                  <p className="text-sm text-zinc-700 mt-3 whitespace-pre-wrap">{item.description}</p>
                )}

                {(item.reasons?.matched_skills?.length || item.reasons?.missing_skills?.length) && (
                  <div className="mt-3 text-xs text-zinc-600 space-y-1">
                    {item.reasons?.matched_skills && item.reasons.matched_skills.length > 0 && (
                      <div>
                        <span className="font-medium text-zinc-700">Matched skills:</span>{' '}
                        {item.reasons.matched_skills.join(', ')}
                      </div>
                    )}
                    {item.reasons?.missing_skills && item.reasons.missing_skills.length > 0 && (
                      <div>
                        <span className="font-medium text-zinc-700">Missing skills:</span>{' '}
                        {item.reasons.missing_skills.join(', ')}
                      </div>
                    )}
                  </div>
                )}

                <div className="mt-4 flex flex-wrap gap-2">
                  {item.status === 'saved' ? (
                    <button
                      type="button"
                      onClick={() => void handleFeedAction(item, 'unsave')}
                      disabled={actionKey === `unsave:${item.opportunity_id}`}
                      className="px-3 py-2 border border-zinc-300 rounded text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-60"
                    >
                      {actionKey === `unsave:${item.opportunity_id}` ? 'Updating...' : 'Unsave'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void handleFeedAction(item, 'save')}
                      disabled={actionKey === `save:${item.opportunity_id}` || item.status === 'applied'}
                      className="px-3 py-2 border border-zinc-300 rounded text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-60"
                    >
                      {actionKey === `save:${item.opportunity_id}` ? 'Saving...' : 'Save'}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleFeedAction(item, 'dismiss')}
                    disabled={actionKey === `dismiss:${item.opportunity_id}` || item.status === 'applied'}
                    className="px-3 py-2 border border-zinc-300 rounded text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-60"
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
                    className="px-3 py-2 bg-zinc-900 text-white rounded text-sm hover:bg-zinc-800 disabled:opacity-60"
                  >
                    {item.status === 'applied'
                      ? 'Applied'
                      : activeApplyId === item.opportunity_id
                        ? 'Close'
                        : 'Apply'}
                  </button>
                </div>

                {activeApplyId === item.opportunity_id && item.status !== 'applied' && (
                  <div className="mt-3 p-3 border border-zinc-200 rounded-lg bg-zinc-50 space-y-3">
                    <label className="block space-y-1">
                      <span className="text-xs text-zinc-600">
                        Optional note for recruiter/hiring manager
                      </span>
                      <textarea
                        rows={3}
                        value={applyDrafts[item.opportunity_id] || ''}
                        onChange={(event) =>
                          setApplyDrafts((current) => ({
                            ...current,
                            [item.opportunity_id]: event.target.value,
                          }))
                        }
                        placeholder="Why this role or project fits your growth goals."
                        maxLength={APPLY_NOTE_MAX_LENGTH}
                        className="w-full px-3 py-2 border border-zinc-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 resize-y bg-white"
                      />
                      <div
                        className={`text-[11px] text-right ${
                          (applyDrafts[item.opportunity_id] || '').length >= APPLY_NOTE_MAX_LENGTH
                            ? 'text-red-600'
                            : 'text-zinc-500'
                        }`}
                      >
                        {(applyDrafts[item.opportunity_id] || '').length}/{APPLY_NOTE_MAX_LENGTH}
                      </div>
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setActiveApplyId(null)}
                        className="px-3 py-2 border border-zinc-300 rounded text-sm text-zinc-700 hover:bg-zinc-100"
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
                        className="px-3 py-2 bg-zinc-900 text-white rounded text-sm hover:bg-zinc-800 disabled:opacity-60"
                      >
                        {actionKey === `apply:${item.opportunity_id}` ? 'Submitting...' : 'Submit Application'}
                      </button>
                    </div>
                  </div>
                )}

                {actionErrors[item.opportunity_id] && (
                  <div className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
                    {actionErrors[item.opportunity_id]}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
