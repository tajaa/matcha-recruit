import { useState } from 'react'
import { Link, useInRouterContext } from 'react-router-dom'
import { BadgeCheck, Briefcase, Download, ExternalLink, Globe, MapPin, Phone, Star } from 'lucide-react'
import type { AgentJobPosting, AgentPlace, AgentSavedJob } from '../../types'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import { checkedText, csvFilename, downloadCsv, jobPostingsCsv, placesCsv } from './agentListCsv'

/**
 * The lists in an Espresso assistant answer: businesses from Google Maps
 * (`places`), open job postings (`job_postings`) and jobs from a saved search
 * (`jobs`). Every row is the server's, rebuilt from what the run's tools
 * returned; links are http(s) only and open in a new tab without referrer.
 * Long lists show their first rows and fold the rest; places and postings
 * download as CSV.
 */

const EXTERNAL = { target: '_blank', rel: 'noopener noreferrer nofollow' } as const
const FOLDED = 8

function httpUrl(url?: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

function ListHeader({ title, count, found, onDownload }: {
  title: string; count: number; found?: number; onDownload?: () => void
}) {
  return (
    <div className="flex items-center gap-2">
      <p className="min-w-0 flex-1 truncate text-xs font-semibold text-w-text">
        {title} <span className="font-normal text-w-dim">· {count}{found && found > count ? ` of ${found}` : ''}</span>
      </p>
      {onDownload && (
        <button
          type="button"
          onClick={onDownload}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-w-line px-2 py-1 text-[11px] font-semibold text-w-text hover:bg-w-surface2"
        >
          <Download size={11} /> CSV
        </button>
      )}
    </div>
  )
}

function Fold({ total, open, onToggle }: { total: number; open: boolean; onToggle: () => void }) {
  if (total <= FOLDED) return null
  return (
    <button type="button" onClick={onToggle} className="text-[11px] text-w-dim hover:text-w-text">
      {open ? 'Show fewer' : `Show all ${total}`}
    </button>
  )
}

export function PlacesList({ title, places, found }: { title?: string; places: AgentPlace[]; found?: number }) {
  const [open, setOpen] = useState(false)
  if (!places.length) return null
  const shown = open ? places : places.slice(0, FOLDED)
  return (
    <div className="space-y-1.5 border-t border-w-line pt-2">
      <ListHeader
        title={title || 'Places'}
        count={places.length}
        found={found}
        onDownload={() => downloadCsv(placesCsv(places), csvFilename(title, 'places'))}
      />
      <ul className="divide-y divide-w-line/60">
        {shown.map((place) => {
          const site = httpUrl(place.website)
          const maps = httpUrl(place.maps_url)
          return (
            <li key={place.id} className="space-y-0.5 py-1.5">
              <div className="flex items-center gap-1.5">
                {site ? (
                  <a href={site} {...EXTERNAL} className="min-w-0 truncate text-xs font-semibold text-w-text hover:underline">
                    {place.name}
                  </a>
                ) : (
                  <span className="min-w-0 truncate text-xs font-semibold text-w-text">{place.name}</span>
                )}
                {place.rating != null && (
                  <span className="inline-flex shrink-0 items-center gap-0.5 text-[11px]">
                    <Star size={10} className="fill-yellow-400 text-yellow-400" />
                    <span className="text-w-text">{place.rating.toFixed(1)}</span>
                    {place.reviews != null && <span className="text-w-dim">({place.reviews.toLocaleString()})</span>}
                  </span>
                )}
                {place.price && <span className="shrink-0 text-[11px] text-w-dim">{place.price}</span>}
                <span className="ml-auto flex shrink-0 items-center gap-2 text-w-dim">
                  {site && (
                    <a href={site} {...EXTERNAL} title={host(site)} aria-label={`${place.name} website`} className="hover:text-w-text">
                      <Globe size={12} />
                    </a>
                  )}
                  {maps && (
                    <a href={maps} {...EXTERNAL} title="Google Maps" aria-label={`${place.name} on Google Maps`} className="hover:text-w-text">
                      <MapPin size={12} />
                    </a>
                  )}
                </span>
              </div>
              <p className="truncate text-[11px] text-w-dim">
                {[place.category, place.address].filter(Boolean).join(' · ')}
              </p>
              {place.phone && (
                <a href={telHref(place.phone)} className="inline-flex items-center gap-1 text-[11px] text-w-dim hover:text-w-text">
                  <Phone size={10} /> {place.phone}
                </a>
              )}
            </li>
          )
        })}
      </ul>
      <Fold total={places.length} open={open} onToggle={() => setOpen((v) => !v)} />
      <p className="text-[10px] text-w-faint">From Google Maps. Ratings and hours change; check before you call.</p>
    </div>
  )
}

export function JobPostingsList({ jobs, found }: { jobs: AgentJobPosting[]; found?: number }) {
  const [open, setOpen] = useState(false)
  if (!jobs.length) return null
  const shown = open ? jobs : jobs.slice(0, FOLDED)
  return (
    <div className="space-y-1.5 border-t border-w-line pt-2">
      <ListHeader
        title="Open roles"
        count={jobs.length}
        found={found}
        onDownload={() => downloadCsv(jobPostingsCsv(jobs), 'jobs.csv')}
      />
      <ul className="space-y-1.5">
        {shown.map((job) => {
          const apply = httpUrl(job.apply_url)
          const where = job.location || (job.remote ? 'Remote' : '')
          return (
            <li key={job.id} className="space-y-1 rounded-xl bg-w-surface2/60 p-2">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-w-text">{job.title}</p>
                  <p className="truncate text-[11px] text-w-dim">
                    {[job.company, where, job.remote && job.location && !/remote/i.test(job.location) ? 'remote' : null]
                      .filter(Boolean).join(' · ')}
                  </p>
                </div>
                {apply && (
                  <a
                    href={apply}
                    {...EXTERNAL}
                    className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-w-accent px-2 py-1 text-[11px] font-semibold text-w-on-accent hover:opacity-90"
                  >
                    Apply <ExternalLink size={10} />
                  </a>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]">
                <span className={job.pay_status === 'posted' ? 'font-semibold text-w-text' : 'text-w-dim'}>
                  {job.pay || 'Pay not posted'}
                </span>
                {job.posted && <span className="text-w-faint">Posted {job.posted}</span>}
                {job.at_employer ? (
                  <span className="inline-flex items-center gap-0.5 text-emerald-400">
                    <BadgeCheck size={10} /> {checkedText(job)}
                  </span>
                ) : (
                  <span className={job.verified ? 'text-w-dim' : 'text-orange-300'}>{checkedText(job)}</span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      <Fold total={jobs.length} open={open} onToggle={() => setOpen((v) => !v)} />
    </div>
  )
}

const JOB_STATE: Record<string, string> = { saved: 'Saved', applied: 'Applied', dismissed: 'Dismissed' }

/** A link to the job in Job search (`/espresso/jobs/:searchId?job=`), which
 *  only the personal surface has. */
function JobLink({ searchId, jobId, children }: { searchId: string; jobId: string; children: React.ReactNode }) {
  const base = useWorkBase()
  const inRouter = useInRouterContext()
  if (base !== '/espresso') return <>{children}</>
  const to = `/espresso/jobs/${encodeURIComponent(searchId)}?job=${encodeURIComponent(jobId)}`
  const className = 'min-w-0 truncate text-xs font-semibold text-w-text hover:underline'
  return inRouter ? <Link to={to} className={className}>{children}</Link> : <a href={to} className={className}>{children}</a>
}

export function SavedJobsList({ searchId, jobs }: { searchId: string; jobs: AgentSavedJob[] }) {
  const [open, setOpen] = useState(false)
  if (!jobs.length) return null
  const shown = open ? jobs : jobs.slice(0, FOLDED)
  return (
    <div className="space-y-1.5 border-t border-w-line pt-2">
      <ListHeader title="From your job search" count={jobs.length} />
      <ul className="space-y-1.5">
        {shown.map((job) => {
          const apply = httpUrl(job.apply_url)
          return (
            <li key={job.id} className="flex items-start gap-2 rounded-xl bg-w-surface2/60 p-2">
              <Briefcase size={12} className="mt-0.5 shrink-0 text-w-dim" />
              <div className="min-w-0 flex-1 space-y-0.5">
                <div className="flex items-center gap-1.5">
                  {job.rank != null && <span className="text-[10px] font-bold text-w-accent">#{job.rank}</span>}
                  <JobLink searchId={searchId} jobId={job.id}>{job.title}</JobLink>
                </div>
                <p className="truncate text-[11px] text-w-dim">{[job.company, job.location].filter(Boolean).join(' · ')}</p>
                <p className="text-[11px]">
                  <span className={job.comp_status === 'posted' ? 'font-semibold text-w-text' : 'text-w-dim'}>
                    {job.comp_line || 'Pay not posted'}
                  </span>
                  {job.fit_score != null && <span className="text-w-faint"> · fit {job.fit_score}/5</span>}
                  {job.user_state && JOB_STATE[job.user_state] && (
                    <span className="text-w-faint"> · {JOB_STATE[job.user_state]}</span>
                  )}
                </p>
              </div>
              {apply && (
                <a href={apply} {...EXTERNAL} aria-label={`Apply to ${job.title}`} className="shrink-0 text-w-dim hover:text-w-text">
                  <ExternalLink size={12} />
                </a>
              )}
            </li>
          )
        })}
      </ul>
      <Fold total={jobs.length} open={open} onToggle={() => setOpen((v) => !v)} />
    </div>
  )
}
