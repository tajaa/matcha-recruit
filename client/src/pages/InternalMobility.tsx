import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  internalMobilityAdmin,
  type InternalMobilityApplicationAdmin,
  type InternalMobilityApplicationStatus,
  type InternalMobilityOpportunity,
  type InternalMobilityOpportunityStatus,
  type InternalMobilityOpportunityType,
} from '../api/client';
import { FeatureGuideTrigger } from '../features/feature-guides';

const OPPORTUNITY_STATUSES: InternalMobilityOpportunityStatus[] = ['draft', 'active', 'closed'];
const OPPORTUNITY_TYPES: InternalMobilityOpportunityType[] = ['role', 'project'];
const APPLICATION_STATUSES: InternalMobilityApplicationStatus[] = [
  'new',
  'in_review',
  'shortlisted',
  'aligned',
  'closed',
];

type OpportunityFormState = {
  type: InternalMobilityOpportunityType;
  title: string;
  department: string;
  description: string;
  requiredSkills: string;
  preferredSkills: string;
  durationWeeks: string;
  status: InternalMobilityOpportunityStatus;
};

const INITIAL_FORM: OpportunityFormState = {
  type: 'role',
  title: '',
  department: '',
  description: '',
  requiredSkills: '',
  preferredSkills: '',
  durationWeeks: '',
  status: 'draft',
};

function parseListInput(value: string): string[] {
  const seen = new Set<string>();
  const parsed: string[] = [];
  for (const raw of value.split(',')) {
    const item = raw.trim();
    if (!item) continue;
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    parsed.push(item);
  }
  return parsed;
}

function formatStatus(status: string): string {
  return status.replace('_', ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function statusPillClass(status: string): string {
  switch (status) {
    case 'active':
    case 'aligned':
      return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300';
    case 'draft':
    case 'in_review':
      return 'bg-amber-500/10 border-amber-500/30 text-amber-300';
    case 'closed':
    case 'dismissed':
      return 'bg-zinc-500/10 border-zinc-500/30 text-zinc-300';
    default:
      return 'bg-blue-500/10 border-blue-500/30 text-blue-300';
  }
}

export default function InternalMobility() {
  const [form, setForm] = useState<OpportunityFormState>(INITIAL_FORM);
  const [opportunities, setOpportunities] = useState<InternalMobilityOpportunity[]>([]);
  const [applications, setApplications] = useState<InternalMobilityApplicationAdmin[]>([]);
  const [opportunityStatusFilter, setOpportunityStatusFilter] = useState<string>('');
  const [opportunityTypeFilter, setOpportunityTypeFilter] = useState<string>('');
  const [applicationStatusFilter, setApplicationStatusFilter] = useState<string>('');
  const [loadingOpportunities, setLoadingOpportunities] = useState(true);
  const [loadingApplications, setLoadingApplications] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const opportunitiesByStatus = useMemo(() => {
    return opportunities.reduce<Record<string, number>>((acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      return acc;
    }, {});
  }, [opportunities]);

  const applicationsByStatus = useMemo(() => {
    return applications.reduce<Record<string, number>>((acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      return acc;
    }, {});
  }, [applications]);

  const loadOpportunities = useCallback(async () => {
    setLoadingOpportunities(true);
    try {
      const data = await internalMobilityAdmin.listOpportunities({
        status: (opportunityStatusFilter || undefined) as InternalMobilityOpportunityStatus | undefined,
        type: (opportunityTypeFilter || undefined) as InternalMobilityOpportunityType | undefined,
      });
      setOpportunities(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load opportunities');
    } finally {
      setLoadingOpportunities(false);
    }
  }, [opportunityStatusFilter, opportunityTypeFilter]);

  const loadApplications = useCallback(async () => {
    setLoadingApplications(true);
    try {
      const data = await internalMobilityAdmin.listApplications({
        status: (applicationStatusFilter || undefined) as InternalMobilityApplicationStatus | undefined,
      });
      setApplications(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load applications');
    } finally {
      setLoadingApplications(false);
    }
  }, [applicationStatusFilter]);

  useEffect(() => {
    void loadOpportunities();
  }, [loadOpportunities]);

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const handleCreateOpportunity = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setNotice(null);
    setError(null);
    const trimmedTitle = form.title.trim();
    if (!trimmedTitle) {
      setError('Title is required.');
      return;
    }

    let durationWeeks: number | null = null;
    if (form.durationWeeks.trim()) {
      const parsed = Number(form.durationWeeks);
      if (!Number.isInteger(parsed) || parsed <= 0) {
        setError('Duration must be a positive whole number.');
        return;
      }
      durationWeeks = parsed;
    }

    setSubmitting(true);
    try {
      await internalMobilityAdmin.createOpportunity({
        type: form.type,
        title: trimmedTitle,
        department: form.department.trim() || null,
        description: form.description.trim() || null,
        required_skills: parseListInput(form.requiredSkills),
        preferred_skills: parseListInput(form.preferredSkills),
        duration_weeks: durationWeeks,
        status: form.status,
      });
      setForm(INITIAL_FORM);
      setNotice('Opportunity created.');
      await loadOpportunities();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create opportunity');
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpportunityStatusUpdate = async (
    opportunity: InternalMobilityOpportunity,
    nextStatus: InternalMobilityOpportunityStatus,
  ) => {
    if (opportunity.status === nextStatus) return;
    setBusyKey(`opp:${opportunity.id}`);
    setError(null);
    setNotice(null);
    try {
      const updated = await internalMobilityAdmin.updateOpportunity(opportunity.id, { status: nextStatus });
      setOpportunities((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setNotice(`Opportunity "${updated.title}" updated to ${formatStatus(updated.status)}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update opportunity');
    } finally {
      setBusyKey(null);
    }
  };

  const handleApplicationStatusUpdate = async (
    application: InternalMobilityApplicationAdmin,
    nextStatus: InternalMobilityApplicationStatus,
  ) => {
    if (application.status === nextStatus) return;
    setBusyKey(`app-status:${application.id}`);
    setError(null);
    setNotice(null);
    try {
      const updated = await internalMobilityAdmin.updateApplication(application.id, { status: nextStatus });
      setApplications((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setNotice(`Application moved to ${formatStatus(updated.status)}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update application');
    } finally {
      setBusyKey(null);
    }
  };

  const handleManagerNotifiedUpdate = async (application: InternalMobilityApplicationAdmin, notify: boolean) => {
    setBusyKey(`app-manager:${application.id}`);
    setError(null);
    setNotice(null);
    try {
      const updated = await internalMobilityAdmin.updateApplication(application.id, {
        manager_notified: notify,
      });
      setApplications((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setNotice(notify ? 'Manager notification recorded.' : 'Manager notification reset.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update manager notification');
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      <div className="border-b border-white/10 pb-6 md:pb-8">
        <div className="flex items-center gap-3" data-tour="internal-mobility-guide">
          <h1 className="text-2xl md:text-4xl font-bold tracking-tighter text-white uppercase">
            Internal Mobility
          </h1>
          <FeatureGuideTrigger guideId="internal-mobility" />
        </div>
        <p className="text-xs text-zinc-500 mt-2 font-mono tracking-wide uppercase">
          Launch opportunities and review employee applications
        </p>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-300 text-sm">
          {error}
        </div>
      )}
      {notice && (
        <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-sm">
          {notice}
        </div>
      )}

      <section className="border border-white/10 bg-zinc-900/40 p-5 md:p-6" data-tour="internal-mobility-create-form">
        <h2 className="text-sm font-bold text-white uppercase tracking-wider">Create Opportunity</h2>
        <form className="mt-5 space-y-4" onSubmit={handleCreateOpportunity}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="space-y-1">
              <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Type</span>
              <select
                value={form.type}
                onChange={(event) =>
                  setForm((current) => ({ ...current, type: event.target.value as InternalMobilityOpportunityType }))
                }
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500"
              >
                {OPPORTUNITY_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {formatStatus(value)}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 md:col-span-2">
              <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Title</span>
              <input
                type="text"
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                placeholder="Senior Analyst, 8-week Product Analytics Project..."
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500"
              />
            </label>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="space-y-1">
              <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Department</span>
              <input
                type="text"
                value={form.department}
                onChange={(event) => setForm((current) => ({ ...current, department: event.target.value }))}
                placeholder="Product, Finance, Operations"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">
                Duration (weeks)
              </span>
              <input
                type="number"
                min={1}
                value={form.durationWeeks}
                onChange={(event) => setForm((current) => ({ ...current, durationWeeks: event.target.value }))}
                placeholder="Optional"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Initial Status</span>
              <select
                value={form.status}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    status: event.target.value as InternalMobilityOpportunityStatus,
                  }))
                }
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500"
              >
                {OPPORTUNITY_STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {formatStatus(value)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="block space-y-1">
            <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">Description</span>
            <textarea
              rows={3}
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="Describe scope, outcomes, and team context."
              className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500 resize-y"
            />
          </label>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="block space-y-1">
              <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">
                Required Skills (comma-separated)
              </span>
              <input
                type="text"
                value={form.requiredSkills}
                onChange={(event) => setForm((current) => ({ ...current, requiredSkills: event.target.value }))}
                placeholder="SQL, Python, Stakeholder Communication"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">
                Preferred Skills (comma-separated)
              </span>
              <input
                type="text"
                value={form.preferredSkills}
                onChange={(event) => setForm((current) => ({ ...current, preferredSkills: event.target.value }))}
                placeholder="Looker, Experimentation, GTM"
                className="w-full bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-sm outline-none focus:border-zinc-500"
              />
            </label>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="px-6 py-2 bg-white text-black border border-white text-[10px] uppercase tracking-widest font-bold disabled:opacity-50"
          >
            {submitting ? 'Creating...' : 'Create Opportunity'}
          </button>
        </form>
      </section>

      <section className="border border-white/10 bg-zinc-900/30 p-5 md:p-6 space-y-4">
        <div className="flex flex-wrap items-end gap-3" data-tour="internal-mobility-opportunities-filters">
          <h2 className="text-sm font-bold text-white uppercase tracking-wider mr-4">Opportunities</h2>
          <label className="space-y-1">
            <span className="block text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Status</span>
            <select
              value={opportunityStatusFilter}
              onChange={(event) => setOpportunityStatusFilter(event.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-xs outline-none focus:border-zinc-500"
            >
              <option value="">All</option>
              {OPPORTUNITY_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {formatStatus(value)}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Type</span>
            <select
              value={opportunityTypeFilter}
              onChange={(event) => setOpportunityTypeFilter(event.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-xs outline-none focus:border-zinc-500"
            >
              <option value="">All</option>
              {OPPORTUNITY_TYPES.map((value) => (
                <option key={value} value={value}>
                  {formatStatus(value)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void loadOpportunities()}
            className="px-4 py-2 border border-zinc-700 text-zinc-200 text-[10px] uppercase tracking-widest"
          >
            Refresh
          </button>
        </div>

        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono">
          Draft: {opportunitiesByStatus.draft || 0} | Active: {opportunitiesByStatus.active || 0} | Closed:{' '}
          {opportunitiesByStatus.closed || 0}
        </div>

        {loadingOpportunities ? (
          <div className="text-xs text-zinc-500 uppercase tracking-wider py-8">Loading opportunities...</div>
        ) : opportunities.length === 0 ? (
          <div className="text-sm text-zinc-500 py-8">No opportunities match current filters.</div>
        ) : (
          <div className="space-y-3" data-tour="internal-mobility-opportunities-list">
            {opportunities.map((opportunity) => (
              <article key={opportunity.id} className="border border-white/10 bg-zinc-950/70 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-white truncate">{opportunity.title}</h3>
                      <span
                        className={`px-2 py-0.5 text-[9px] uppercase tracking-widest border ${statusPillClass(
                          opportunity.status,
                        )}`}
                      >
                        {formatStatus(opportunity.status)}
                      </span>
                      <span className="px-2 py-0.5 text-[9px] uppercase tracking-widest border border-blue-500/30 bg-blue-500/10 text-blue-300">
                        {formatStatus(opportunity.type)}
                      </span>
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">
                      {opportunity.department || 'No department'} | Created {formatDate(opportunity.created_at)}
                    </div>
                  </div>
                  <label className="space-y-1">
                    <span className="block text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Status</span>
                    <select
                      value={opportunity.status}
                      onChange={(event) =>
                        void handleOpportunityStatusUpdate(
                          opportunity,
                          event.target.value as InternalMobilityOpportunityStatus,
                        )
                      }
                      disabled={busyKey === `opp:${opportunity.id}`}
                      className="bg-zinc-950 border border-zinc-800 text-white px-2 py-1.5 text-xs outline-none focus:border-zinc-500 disabled:opacity-50"
                    >
                      {OPPORTUNITY_STATUSES.map((value) => (
                        <option key={value} value={value}>
                          {formatStatus(value)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {opportunity.description && (
                  <p className="text-sm text-zinc-300 mt-3 whitespace-pre-wrap">{opportunity.description}</p>
                )}
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-zinc-500 uppercase tracking-wider">Required:</span>{' '}
                    <span className="text-zinc-200">
                      {opportunity.required_skills.length > 0
                        ? opportunity.required_skills.join(', ')
                        : 'Not specified'}
                    </span>
                  </div>
                  <div>
                    <span className="text-zinc-500 uppercase tracking-wider">Preferred:</span>{' '}
                    <span className="text-zinc-200">
                      {opportunity.preferred_skills.length > 0
                        ? opportunity.preferred_skills.join(', ')
                        : 'Not specified'}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section
        className="border border-white/10 bg-zinc-900/30 p-5 md:p-6 space-y-4"
        data-tour="internal-mobility-applications-list"
      >
        <div className="flex flex-wrap items-end gap-3">
          <h2 className="text-sm font-bold text-white uppercase tracking-wider mr-4">Applications</h2>
          <label className="space-y-1">
            <span className="block text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Status</span>
            <select
              value={applicationStatusFilter}
              onChange={(event) => setApplicationStatusFilter(event.target.value)}
              className="bg-zinc-950 border border-zinc-800 text-white px-3 py-2 text-xs outline-none focus:border-zinc-500"
            >
              <option value="">All</option>
              {APPLICATION_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {formatStatus(value)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void loadApplications()}
            className="px-4 py-2 border border-zinc-700 text-zinc-200 text-[10px] uppercase tracking-widest"
          >
            Refresh
          </button>
        </div>

        <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono">
          New: {applicationsByStatus.new || 0} | In Review: {applicationsByStatus.in_review || 0} | Shortlisted:{' '}
          {applicationsByStatus.shortlisted || 0} | Aligned: {applicationsByStatus.aligned || 0} | Closed:{' '}
          {applicationsByStatus.closed || 0}
        </div>

        {loadingApplications ? (
          <div className="text-xs text-zinc-500 uppercase tracking-wider py-8">Loading applications...</div>
        ) : applications.length === 0 ? (
          <div className="text-sm text-zinc-500 py-8">No applications match current filters.</div>
        ) : (
          <div className="space-y-3">
            {applications.map((application) => {
              const managerNotified = Boolean(application.manager_notified_at);
              return (
                <article key={application.id} className="border border-white/10 bg-zinc-950/70 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-sm font-semibold text-white truncate">{application.employee_name}</h3>
                        <span className="text-xs text-zinc-500">{application.employee_email}</span>
                      </div>
                      <div className="text-sm text-zinc-300 mt-1">
                        {application.opportunity_title} ({formatStatus(application.opportunity_type)})
                      </div>
                      <div className="text-xs text-zinc-500 mt-1">
                        Submitted {formatDate(application.submitted_at)}
                      </div>
                      {application.employee_notes && (
                        <p className="text-sm text-zinc-300 mt-2 whitespace-pre-wrap">{application.employee_notes}</p>
                      )}
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <label className="space-y-1">
                        <span className="block text-[9px] uppercase tracking-widest text-zinc-500 font-bold">
                          Status
                        </span>
                        <select
                          data-tour="internal-mobility-application-status"
                          value={application.status}
                          onChange={(event) =>
                            void handleApplicationStatusUpdate(
                              application,
                              event.target.value as InternalMobilityApplicationStatus,
                            )
                          }
                          disabled={busyKey === `app-status:${application.id}`}
                          className="bg-zinc-950 border border-zinc-800 text-white px-2 py-1.5 text-xs outline-none focus:border-zinc-500 disabled:opacity-50"
                        >
                          {APPLICATION_STATUSES.map((value) => (
                            <option key={value} value={value}>
                              {formatStatus(value)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        type="button"
                        onClick={() => void handleManagerNotifiedUpdate(application, !managerNotified)}
                        disabled={busyKey === `app-manager:${application.id}`}
                        className="self-end px-3 py-1.5 border border-zinc-700 text-xs text-zinc-200 disabled:opacity-50"
                      >
                        {managerNotified ? 'Mark Not Notified' : 'Mark Manager Notified'}
                      </button>
                    </div>
                  </div>
                  <div className="mt-2">
                    <span
                      className={`inline-flex px-2 py-0.5 text-[9px] uppercase tracking-widest border ${statusPillClass(
                        application.status,
                      )}`}
                    >
                      {formatStatus(application.status)}
                    </span>
                    {managerNotified && (
                      <span className="ml-2 text-[10px] text-emerald-400 uppercase tracking-wider">
                        Manager notified {application.manager_notified_at ? formatDate(application.manager_notified_at) : ''}
                      </span>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
