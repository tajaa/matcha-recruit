import { useState, type ReactNode } from 'react'
import {
  Bookmark, BookmarkCheck, Box, Building2, Check, CheckCircle2, EyeOff, ExternalLink, Loader2, Quote, ListPlus,
  Sparkles, Tag, X, OctagonX, BadgeCheck,
} from 'lucide-react'
import type {
  AgentTaskAction, AgentTaskColumn, AgentTaskField, AgentTaskImage, AgentTaskItemDetail, AgentTaskUnit,
} from '../../types'
import {
  HOMES_SHOWN, columnLabel, dollars, doneLine, factOrder, hiddenReason, homesLine, homesOrder, isFinishedRun,
  isVerified, layoutLine, linkLabel, originLabel, unconfirmed, unitTerms, webUrl,
} from '../../components/tasks/tasksLogic'
import { ActionIcon } from './ActionModal'

/**
 * One finding, as on the Mac (`TaskItemDetailView`): its photos and page,
 * every fact with the words and page it came from, an apartment building's
 * homes one by one, why it fits (or why it's hidden), the person's notes, and
 * what to do with it.
 */
export default function ItemPane({
  item, columns, canFollowUp, busy, onClose, onSetState, onSaveNotes, onMoreLikeThis, onAskEspresso, onAction,
}: {
  item: AgentTaskItemDetail | null
  columns: AgentTaskColumn[]
  /** The task can take "More like this" (it finished and isn't a job search). */
  canFollowUp: boolean
  busy: boolean
  onClose: () => void
  onSetState: (state: string, itemId: string) => void
  onSaveNotes: (notes: string, itemId: string) => void
  onMoreLikeThis: (itemId: string) => void
  onAskEspresso: (itemId: string) => void
  onAction: (item: AgentTaskItemDetail, action: AgentTaskAction) => void
}) {
  return (
    <aside className="fixed inset-0 z-40 flex flex-col bg-w-surface xl:static xl:z-auto xl:w-[420px] xl:shrink-0 xl:border-l xl:border-w-line">
      <div className="flex justify-end px-3 pt-2">
        <button type="button" onClick={onClose} aria-label="Close the finding" className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text">
          <X size={14} />
        </button>
      </div>
      {item ? (
        <ItemBody
          key={item.id}
          item={item}
          columns={columns}
          canFollowUp={canFollowUp}
          busy={busy}
          onSetState={onSetState}
          onSaveNotes={onSaveNotes}
          onMoreLikeThis={onMoreLikeThis}
          onAskEspresso={onAskEspresso}
          onAction={onAction}
        />
      ) : (
        <div className="flex flex-1 items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
      )}
    </aside>
  )
}

function ItemBody({
  item, columns, canFollowUp, busy, onSetState, onSaveNotes, onMoreLikeThis, onAskEspresso, onAction,
}: {
  item: AgentTaskItemDetail
  columns: AgentTaskColumn[]
  canFollowUp: boolean
  busy: boolean
  onSetState: (state: string, itemId: string) => void
  onSaveNotes: (notes: string, itemId: string) => void
  onMoreLikeThis: (itemId: string) => void
  onAskEspresso: (itemId: string) => void
  onAction: (item: AgentTaskItemDetail, action: AgentTaskAction) => void
}) {
  // Keyed by the finding, so a different one starts from its own notes.
  const [notes, setNotes] = useState(item.notes ?? '')
  const page = webUrl(item.url)
  const reason = hiddenReason(item)
  const actions = item.actions ?? []
  const done = (item.action_history ?? []).filter(isFinishedRun)
  const fields = item.fields ?? {}
  const order = factOrder(item, columns)
  const missing = unconfirmed(item)
  const photos = [...(item.images ?? []).map((i) => ({ image: i, page: false })), ...(item.screenshots ?? []).map((i) => ({ image: i, page: true }))]

  return (
    <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 pb-8">
      <div className="space-y-2">
        <h2 className="select-text text-base font-semibold text-w-text">{item.title}</h2>
        {item.subtitle && <p className="text-xs text-w-dim">{item.subtitle}</p>}
        {page && (
          <a href={page} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-w-accent hover:underline">
            <ExternalLink size={11} /> {linkLabel(page)}
          </a>
        )}
        {reason && <p className="text-[11px] font-medium text-amber-500">{reason}</p>}
        <div className="flex flex-wrap gap-1.5 pt-1">
          <StateButton label="Save" state="saved" icon={<Bookmark size={12} />} onIcon={<BookmarkCheck size={12} />} item={item} busy={busy} onSetState={onSetState} />
          <StateButton label="Choose" state="chosen" icon={<BadgeCheck size={12} />} onIcon={<BadgeCheck size={12} />} item={item} busy={busy} onSetState={onSetState} />
          <StateButton label="Dismiss" state="dismissed" icon={<EyeOff size={12} />} onIcon={<EyeOff size={12} />} item={item} busy={busy} onSetState={onSetState} />
        </div>
        {actions.length > 0 && (
          <div className="space-y-1 pt-1">
            <div className="flex flex-wrap gap-1.5">
              {actions.map((action) => (
                <button
                  key={action.key}
                  type="button"
                  disabled={!action.available}
                  title={action.available ? action.description ?? '' : action.reason ?? ''}
                  onClick={() => onAction(item, action)}
                  className="inline-flex items-center gap-1.5 rounded-md bg-w-accent px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-w-accent-hi disabled:opacity-50"
                >
                  <ActionIcon icon={action.icon} /> {action.label}
                </button>
              ))}
            </div>
            {actions.filter((a) => !a.available && a.reason).map((a) => (
              <p key={a.key} className="text-[10px] text-w-dim">{a.label}: {a.reason}</p>
            ))}
          </div>
        )}
      </div>

      {photos.length > 0 && (
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          {photos.map(({ image, page: isPage }) => <Picture key={image.url} image={image} page={isPage} />)}
        </div>
      )}

      {done.length > 0 && (
        <Section title="Done">
          {done.map((run) => {
            const url = run.status === 'done' ? webUrl(run.result?.url) : null
            return (
              <p key={run.id} className="flex items-center gap-1.5 text-[11px] text-w-text">
                {run.status === 'done'
                  ? <CheckCircle2 size={12} className="shrink-0 text-emerald-500" />
                  : <OctagonX size={12} className="shrink-0 text-amber-500" />}
                <span className="line-clamp-2 flex-1">{doneLine(run)}</span>
                {url && <a href={url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-w-accent hover:underline">Open</a>}
              </p>
            )
          })}
        </Section>
      )}

      <Section title="What it found">
        {order.length === 0 && <p className="text-[11px] text-w-dim">No facts could be confirmed from its page.</p>}
        {order.map((key) => (fields[key] ? <FactRow key={key} label={columnLabel(key, columns)} field={fields[key]} /> : null))}
        {missing.length > 0 && (
          <p className="text-[10px] text-w-dim">
            Couldn't confirm on its own page: {missing.map((k) => columnLabel(k, columns)).join(', ')}.
          </p>
        )}
      </Section>

      <Homes item={item} />

      {((item.fit_reasons ?? []).length > 0 || (item.violations ?? []).length > 0) && (
        <Section title="How it fits">
          {item.fit_score != null && <p className="text-[11px] font-semibold text-w-text">Fit {item.fit_score}/5</p>}
          {(item.fit_reasons ?? []).map((r) => (
            <p key={r} className="flex items-start gap-1.5 text-[11px] text-w-text"><Check size={12} className="mt-0.5 shrink-0" /> {r}</p>
          ))}
          {(item.violations ?? []).map((v, i) => (
            <p key={`${v.rule}-${i}`} className="flex items-start gap-1.5 text-[11px] text-amber-500">
              <X size={12} className="mt-0.5 shrink-0" /> Breaks “{v.rule ?? ''}”{v.value ? `: ${v.value}` : ''}
            </p>
          ))}
        </Section>
      )}

      <Section title="Your notes">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={4}
          className="w-full resize-y rounded-md border border-w-line bg-w-surface2/40 px-2 py-1.5 text-xs text-w-text focus:border-w-accent focus:outline-none"
        />
        {notes !== (item.notes ?? '') && (
          <button type="button" disabled={busy} onClick={() => onSaveNotes(notes, item.id)} className="rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-50">
            Save notes
          </button>
        )}
      </Section>

      <div className="flex flex-wrap gap-2">
        {canFollowUp && (
          <button
            type="button"
            disabled={busy}
            title="Search for more like this one. Uses 1 unit."
            onClick={() => onMoreLikeThis(item.id)}
            className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2 disabled:opacity-50"
          >
            <ListPlus size={12} /> More like this
          </button>
        )}
        <button
          type="button"
          onClick={() => onAskEspresso(item.id)}
          className="inline-flex items-center gap-1.5 rounded-md border border-w-line px-2.5 py-1 text-[11px] text-w-text hover:bg-w-surface2"
        >
          <Sparkles size={12} /> Ask Espresso
        </button>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-[9px] font-semibold uppercase tracking-wider text-w-dim">{title}</h3>
      {children}
    </section>
  )
}

/** Pressing the state it's already in puts it back to new. */
function StateButton({ label, state, icon, onIcon, item, busy, onSetState }: {
  label: string
  state: string
  icon: ReactNode
  onIcon: ReactNode
  item: AgentTaskItemDetail
  busy: boolean
  onSetState: (state: string, itemId: string) => void
}) {
  const on = item.user_state === state
  return (
    <button
      type="button"
      disabled={busy}
      aria-pressed={on}
      onClick={() => onSetState(on ? 'new' : state, item.id)}
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] disabled:opacity-50 ${
        on ? 'border-w-accent bg-w-accent/15 text-w-text' : 'border-w-line text-w-text hover:bg-w-surface2'
      }`}
    >
      {on ? onIcon : icon} {label}
    </button>
  )
}

/** Its photos, then its page as the browser drew it (marked as such). */
function Picture({ image, page }: { image: AgentTaskImage; page: boolean }) {
  const url = webUrl(image.url)
  if (!url) return null
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="relative block shrink-0" title={image.alt ?? ''}>
      <img src={url} alt={image.alt ?? ''} loading="lazy" className="h-[110px] w-[150px] rounded-lg bg-w-surface2 object-cover" />
      {page && (
        <span className="absolute bottom-1.5 left-1.5 rounded-full bg-black/55 px-1.5 py-0.5 text-[9px] font-semibold text-white">Its page</span>
      )}
    </a>
  )
}

/** A fact, and on a click what it rests on. */
function FactRow({ label, field }: { label: string; field: AgentTaskField }) {
  const [open, setOpen] = useState(false)
  const verified = isVerified(field)
  const evidence = field.evidence
  const source = webUrl(evidence?.url)
  const origin = originLabel(evidence?.origin)
  const hasEvidence = !!(evidence?.quote || evidence?.url)
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="w-24 shrink-0 text-[11px] text-w-dim">{label}</span>
        <span className="min-w-0 flex-1 select-text text-xs font-medium text-w-text">{field.display}</span>
        <span className={`shrink-0 rounded-full px-1.5 py-px text-[9px] font-semibold ${verified ? 'bg-emerald-500/15 text-emerald-500' : 'bg-amber-500/15 text-amber-500'}`}>
          {verified ? 'Verified' : 'Unconfirmed'}
        </span>
        {hasEvidence && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={`Where ${label} came from`}
            title="Where this came from"
            className="shrink-0 rounded p-0.5 text-w-dim hover:bg-w-surface2 hover:text-w-text"
          >
            <Quote size={11} />
          </button>
        )}
      </div>
      {open && (
        <div className="ml-[104px] mt-1.5 space-y-1.5 rounded-lg bg-w-surface2/60 p-2.5">
          {origin && <p className="text-[10px] font-semibold text-w-dim">{origin}</p>}
          {evidence?.quote && <p className="select-text text-xs italic leading-5 text-w-text">“{evidence.quote}”</p>}
          {source && (
            <a href={source} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-w-accent hover:underline">
              <ExternalLink size={11} /> {linkLabel(source)}
            </a>
          )}
          {!verified && (
            <p className="text-[10px] leading-4 text-w-dim">
              This was stated on another page, not the finding's own, so it isn't used to rule anything in or out.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Homes({ item }: { item: AgentTaskItemDetail }) {
  const [all, setAll] = useState(false)
  const units = item.units ?? []
  if (!units.length) return null
  const ordered = homesOrder(units)
  const shown = all ? ordered : ordered.slice(0, HOMES_SHOWN)
  return (
    <Section title="Homes to let">
      <p className="flex items-center gap-1.5 text-[11px] font-medium text-w-text">
        <Building2 size={12} /> {item.homes ? homesLine(item.homes) : `${ordered.length} homes listed`}
      </p>
      <div className="space-y-1.5">
        {shown.map((unit, i) => <UnitRow key={unit.id ?? `${unit.number}-${i}`} unit={unit} buildingUrl={item.url} />)}
      </div>
      {ordered.length > HOMES_SHOWN && (
        <button type="button" onClick={() => setAll((v) => !v)} className="text-[11px] text-w-accent hover:underline">
          {all ? 'Show fewer' : `Show all ${ordered.length}`}
        </button>
      )}
      <p className="text-[10px] leading-4 text-w-dim">
        From the building's leasing system. Net rent spreads a special's free weeks over the lease.
      </p>
    </Section>
  )
}

/** One home to let: its layout, rent (and net rent), move-in date, special, floor plan and tour. */
function UnitRow({ unit, buildingUrl }: { unit: AgentTaskUnit; buildingUrl?: string | null }) {
  const [planOpen, setPlanOpen] = useState(false)
  const plan = webUrl(unit.plan_image)
  const tour = webUrl(unit.tour_url)
  const ownPage = unit.url !== buildingUrl ? webUrl(unit.url) : null
  const terms = unitTerms(unit)
  return (
    <div className={`flex gap-2.5 rounded-lg p-2 ${unit.fits === true ? 'bg-emerald-500/5' : 'bg-w-surface2/40'}`}>
      {plan ? (
        <button type="button" onClick={() => setPlanOpen((v) => !v)} title="Floor plan" aria-label="Floor plan" className="shrink-0">
          <img src={plan} alt="Floor plan" loading="lazy" className="h-14 w-14 rounded-md bg-white object-contain" />
        </button>
      ) : (
        <span title="No floor plan" className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-w-surface2 text-w-faint"><Box size={16} /></span>
      )}
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="flex items-center gap-1.5">
          <span className="truncate text-[11px] font-semibold text-w-text">{layoutLine(unit)}</span>
          {unit.fits === true && (
            <span title="Meets every limit you set" className="shrink-0 rounded-full bg-emerald-500/15 px-1.5 py-px text-[9px] font-semibold text-emerald-500">Fits</span>
          )}
        </p>
        <p className="flex items-baseline gap-1.5">
          {unit.rent != null && <span className="text-xs font-medium text-w-text">{dollars(unit.rent)}/mo</span>}
          {unit.net_rent != null && (
            <span title={unit.net_note ?? ''} className="text-[11px] font-medium text-emerald-500">{dollars(unit.net_rent)}/mo net</span>
          )}
        </p>
        {terms && <p className="truncate text-[10px] text-w-dim">{terms}</p>}
        {unit.special && <p className="flex items-start gap-1 text-[10px] text-amber-500"><Tag size={10} className="mt-0.5 shrink-0" /> <span className="line-clamp-2">{unit.special}</span></p>}
        {(tour || ownPage) && (
          <p className="flex gap-3 text-[10px]">
            {tour && <a href={tour} target="_blank" rel="noopener noreferrer" className="text-w-accent hover:underline">3D tour</a>}
            {ownPage && <a href={ownPage} target="_blank" rel="noopener noreferrer" className="text-w-accent hover:underline">Its page</a>}
          </p>
        )}
        {planOpen && plan && <img src={plan} alt="Floor plan" className="mt-1.5 w-full rounded-md bg-white object-contain" />}
      </div>
    </div>
  )
}
