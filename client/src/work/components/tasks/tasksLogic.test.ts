import { describe, expect, it } from 'vitest'
import { ApiError } from '../../../api/client'
import type { AgentTask, AgentTaskDetail, AgentTaskItem, AgentTaskUnit, IntakeFormField } from '../../types'
import {
  actionParams, actionStage, askEspressoPrompt, availableLabel, badge, buildFormValues, canFollowUp, cardFacts,
  documentJournalId, doneLine, factOrder, filterItems, firstTask, formErrorText, groupTasks, hiddenReason, homesLine,
  homesOrder, initialText, isJobSearch, latestSummary, layoutLine, linkLabel, parseField, planChips, rowFacts, rowMeta,
  statusChanged, statusLabel, taskCardBody, taskCardLead, taskForSearch, unconfirmed, unitTerms, usageLine, webUrl,
} from './tasksLogic'

function task(overrides: Partial<AgentTask> = {}): AgentTask {
  return { id: 't1', title: 'Lip balm', directive: 'best organic lip balm', status: 'done', ...overrides }
}

function detail(overrides: Partial<AgentTaskDetail> = {}): AgentTaskDetail {
  return { ...task(), fingerprint: 'f1', plan: null, rounds: [], items: [], ...overrides }
}

function item(overrides: Partial<AgentTaskItem> = {}): AgentTaskItem {
  return { id: 'i1', title: 'Balm', rank_band: 1, flags: [], user_state: 'new', ...overrides }
}

function field(overrides: Partial<IntakeFormField> = {}): IntakeFormField {
  return { key: 'k', label: 'Thing', type: 'text', ...overrides }
}

describe('tasks', () => {
  it('reads a running task by its phase, a job search by its own', () => {
    expect(statusLabel({ status: 'running', phase: 'enrich' })).toBe('Reading pages…')
    expect(statusLabel({ status: 'running', phase: 'approaching' })).toBe('Drafting approaches…')
    expect(statusLabel({ status: 'running', phase: null })).toBe('Working…')
    expect(statusLabel({ status: 'failed' })).toBe('Stopped')
    expect(statusLabel({ status: 'waiting' })).toBe('Needs you')
  })

  it('groups needs-you, running, then done, newest first in each', () => {
    const tasks = [
      task({ id: 'old', status: 'done', created_at: '2026-10-01T00:00:00Z' }),
      task({ id: 'new', status: 'failed', created_at: '2026-10-10T00:00:00Z' }),
      task({ id: 'run', status: 'queued', created_at: '2026-10-02T00:00:00Z' }),
      task({ id: 'wait', status: 'waiting', created_at: '2026-09-01T00:00:00Z' }),
    ]
    expect(groupTasks(tasks).map(([g, ts]) => [g, ts.map((t) => t.id)])).toEqual([
      ['Needs you', ['wait']], ['Running', ['run']], ['Done', ['new', 'old']],
    ])
    expect(firstTask(tasks)?.id).toBe('wait')
    expect(firstTask([])).toBeNull()
  })

  it('knows a job search only by its engine and search id', () => {
    expect(isJobSearch({ engine: 'job_search', job_search_id: 's1' })).toBe(true)
    expect(isJobSearch({ engine: 'job_search', job_search_id: null })).toBe(false)
    expect(isJobSearch({ engine: 'chain', job_search_id: 's1' })).toBe(false)
    const tasks = [task({ id: 'a' }), task({ id: 'b', engine: 'job_search', job_search_id: 's9' })]
    expect(taskForSearch('s9', tasks)?.id).toBe('b')
    expect(taskForSearch('nope', tasks)).toBeNull()
  })

  it('says a row kind and count like the Mac', () => {
    expect(rowMeta(task({ playbook_label: 'Apartments', shown_count: 12 }))).toEqual({ kind: 'Apartments', count: '12 found' })
    expect(rowMeta(task({ engine: 'job_search', job_search_id: 's', playbook_label: 'Job search', shown_count: 3 })))
      .toEqual({ kind: null, count: '3 jobs' })
    expect(rowMeta(task({ shown_count: 0 })).count).toBeNull()
  })

  it('reads the allowance and the sidebar badge', () => {
    expect(usageLine({ limit: 60, used: 5, remaining: 55 })).toBe('55 of 60 task units left this month')
    expect(usageLine({ limit: 0, used: 0, remaining: 0 })).toBeNull()
    expect(usageLine(null)).toBeNull()
    expect(badge({ running: 2, waiting: 0, unseen: 0 })).toEqual({ count: 2, attention: false })
    expect(badge({ running: 0, waiting: 0, unseen: 1 })).toEqual({ count: 0, attention: true })
    expect(badge(null)).toEqual({ count: 0, attention: false })
  })

  it('reloads only when the fingerprint or status moved', () => {
    const d = detail({ status: 'running', fingerprint: 'a' })
    expect(statusChanged(d, { id: 't1', status: 'running', fingerprint: 'a' })).toBe(false)
    expect(statusChanged(d, { id: 't1', status: 'running', fingerprint: 'b' })).toBe(true)
    expect(statusChanged(d, { id: 't1', status: 'done', fingerprint: 'a' })).toBe(true)
  })
})

describe('a task detail', () => {
  it("takes the newest round's summary that has a headline, never a document's", () => {
    const d = detail({
      rounds: [
        { id: 'r1', n: 1, kind: 'initial', status: 'done', summary: { headline: 'First' } },
        { id: 'r2', n: 2, kind: 'refine', status: 'done', summary: { headline: 'Refined' } },
        { id: 'r3', n: 3, kind: 'document', status: 'done', summary: { headline: 'Doc' }, document: { journal_id: 'j1' } },
      ],
    })
    expect(latestSummary(d)?.headline).toBe('Refined')
    expect(documentJournalId(d)).toBe('j1')
    expect(latestSummary(detail())).toBeNull()
    expect(documentJournalId(detail({ rounds: [{ id: 'r', n: 1, kind: 'initial', status: 'done' }] }))).toBeNull()
  })

  it('follows up only on a finished or waiting task that is not a job search', () => {
    expect(canFollowUp(detail({ status: 'done' }))).toBe(true)
    expect(canFollowUp(detail({ status: 'waiting' }))).toBe(true)
    expect(canFollowUp(detail({ status: 'running' }))).toBe(false)
    expect(canFollowUp(detail({ status: 'done', engine: 'job_search', job_search_id: 's' }))).toBe(false)
  })

  it('shows where, then each limit', () => {
    expect(planChips(detail({ plan: { location: 'San Francisco', constraints: [{ label: 'Rent ≤ $3,500' }, { label: null }] } })))
      .toEqual(['San Francisco', 'Rent ≤ $3,500'])
    expect(planChips(detail())).toEqual([])
  })
})

describe('findings', () => {
  const fits = item({ id: 'fits' })
  const saved = item({ id: 'saved', user_state: 'saved' })
  const chosenHidden = item({ id: 'chosen', user_state: 'chosen', rank_band: 9 })
  const hidden = item({ id: 'hidden', rank_band: 9 })
  const all = [fits, saved, chosenHidden, hidden]
  const ids = (list: AgentTaskItem[]) => list.map((i) => i.id)

  it('filters like the Mac: fits, the ones kept, the hidden', () => {
    expect(ids(filterItems(all, 'Fits'))).toEqual(['fits', 'saved'])
    expect(ids(filterItems(all, 'Saved'))).toEqual(['saved', 'chosen'])
    expect(ids(filterItems(all, 'Hidden'))).toEqual(['chosen', 'hidden'])
  })

  it('names what it could not confirm and why it is hidden', () => {
    expect(unconfirmed(item({ flags: ['unconfirmed:price', 'unavailable', 'unconfirmed:pets'] }))).toEqual(['price', 'pets'])
    expect(hiddenReason(item({ user_state: 'dismissed', flags: ['unavailable'] }))).toBe('Dismissed')
    expect(hiddenReason(item({ flags: ['unavailable'] }))).toBe('No longer available')
    expect(hiddenReason({ ...item({ flags: ['irrelevant'] }), violations: [{ rule: 'price ≤ 15' }] })).toBe('Breaks a limit: price ≤ 15')
    expect(hiddenReason(item({ flags: ['irrelevant'] }))).toBe('Not a fit')
    expect(hiddenReason(item())).toBeNull()
  })

  it("orders facts by the plan's columns, then the rest by name", () => {
    const columns = [{ key: 'price', label: 'Price' }, { key: 'rating', label: 'Rating' }, { key: 'missing', label: 'X' }]
    const it_ = item({
      fields: {
        zeta: { display: 'z', status: 'verified' },
        rating: { display: '4.5', status: 'claimed' },
        alpha: { display: 'a', status: 'verified' },
        price: { display: '$9', status: 'verified' },
      },
    })
    expect(factOrder(it_, columns)).toEqual(['price', 'rating', 'alpha', 'zeta'])
    expect(rowFacts(it_, columns).map((f) => f.label)).toEqual(['Price', 'Rating'])
    expect(factOrder(item(), null)).toEqual([])
  })
})

describe('homes', () => {
  const unit = (overrides: Partial<AgentTaskUnit> = {}): AgentTaskUnit => ({ id: 'u', rent: 3000, ...overrides })

  it('says how many fit', () => {
    expect(homesLine({ count: 18, fit: 3, from: 2949 })).toBe('3 of 18 homes fit · from $2,949/mo')
    expect(homesLine({ count: 18, fit: 0, from: null })).toBe('None of 18 homes fit')
    expect(homesLine({ count: 1, fit: null, from: 2100.4 })).toBe('1 home listed · from $2,100/mo')
    expect(homesLine({ count: 5, fit: null })).toBe('5 homes listed')
  })

  it('puts the homes that fit first, keeping the server order', () => {
    const units = [unit({ id: 'a', fits: false }), unit({ id: 'b', fits: true }), unit({ id: 'c', fits: null }), unit({ id: 'd', fits: true })]
    expect(homesOrder(units).map((u) => u.id)).toEqual(['b', 'd', 'a', 'c'])
  })

  it('reads a home layout', () => {
    expect(layoutLine(unit({ number: 'B201', floor: '2', beds: 2, baths: 1, sqft: 910 }))).toBe('#B201 · Floor 2 · 2 bd · 1 ba · 910 sq ft')
    expect(layoutLine(unit({ beds: 0, baths: 1.5, sqft: 1250 }))).toBe('A home · Studio · 1.5 ba · 1,250 sq ft')
  })

  it('says when it can be moved into, where the person is', () => {
    const today = new Date(2026, 9, 17) // Oct 17 2026, local
    expect(availableLabel({ available: '2026-10-17' }, today)).toBe('Now')
    expect(availableLabel({ available: '2026-09-01T00:00:00Z' }, today)).toBe('Now')
    expect(availableLabel({ available: '2026-11-04' }, today)).toBe('Nov 4')
    expect(availableLabel({ available: '2027-01-25' }, today)).toBe('Jan 25, 2027')
    expect(availableLabel({ available: 'soon' }, today)).toBeNull()
    expect(availableLabel({ available: null }, today)).toBeNull()
    expect(unitTerms(unit({ available: '2026-11-04', lease_months: 12, plan: 'A2' }), today))
      .toBe('Available Nov 4 · 12-month lease · A2')
  })
})

describe('actions', () => {
  it('moves from details to review to working to finished', () => {
    expect(actionStage(null)).toBe('details')
    expect(actionStage({ id: 'r', status: 'proposed' })).toBe('review')
    expect(actionStage({ id: 'r', status: 'running' })).toBe('working')
    expect(actionStage({ id: 'r', status: 'done' })).toBe('finished')
    expect(actionStage({ id: 'r', status: 'failed' })).toBe('finished')
    expect(actionStage({ id: 'r', status: 'cancelled' })).toBe('finished')
  })

  it('sends only the action fields that were filled in', () => {
    const fields = [field({ key: 'qty' }), field({ key: 'note' })]
    expect(actionParams({ qty: ' 2 ', note: '  ', other: 'x' }, fields)).toEqual({ qty: '2' })
  })

  it('says what came of it', () => {
    expect(doneLine({ id: 'r', status: 'done', label: 'Buy', result: { headline: 'Checkout opened at drbronner.com' } }))
      .toBe('Checkout opened at drbronner.com')
    expect(doneLine({ id: 'r', status: 'done', label: 'Buy' })).toBe('Buy')
    expect(doneLine({ id: 'r', status: 'failed', label: 'Apply', error: 'The page is gone' }))
      .toBe("Apply didn't go through: The page is gone")
    expect(doneLine({ id: 'r', status: 'failed', label: 'Apply' })).toBe("Apply didn't go through.")
  })
})

describe('forms', () => {
  it('reads money and numbers the way people type them', () => {
    const money = field({ type: 'money' })
    expect(parseField(money, '$3,500')).toBe(3500)
    expect(parseField(money, '3.5k')).toBe(3500)
    expect(parseField(money, '-5')).toBeUndefined()
    expect(parseField(money, 'lots')).toBeUndefined()
  })

  it('checks dates, times, choices and lists', () => {
    expect(parseField(field({ type: 'date' }), '2026-11-04')).toBe('2026-11-04')
    expect(parseField(field({ type: 'date' }), '2026-02-30')).toBeUndefined()
    expect(parseField(field({ type: 'time' }), '7:05')).toBe('07:05')
    expect(parseField(field({ type: 'time' }), '24:00')).toBeUndefined()
    expect(parseField(field({ type: 'boolean' }), 'Yes')).toBe(true)
    expect(parseField(field({ type: 'boolean' }), 'maybe')).toBeUndefined()
    expect(parseField(field({ type: 'select', options: ['Cats', 'Dogs'] }), 'Dogs')).toBe('Dogs')
    expect(parseField(field({ type: 'select', options: ['Cats'] }), 'Dogs')).toBeUndefined()
    expect(parseField(field({ type: 'list' }), 'COO, VP Ops,')).toEqual(['COO', 'VP Ops'])
    // Semicolons and new lines win, so a "City, ST" stays one place (as the server reads it).
    expect(parseField(field({ type: 'list' }), 'New York, NY; Remote')).toEqual(['New York, NY', 'Remote'])
    expect(parseField(field({ type: 'list' }), 'Austin, TX\nDenver, CO\n')).toEqual(['Austin, TX', 'Denver, CO'])
    expect(parseField(field({ type: 'list' }), ' ; ')).toBeUndefined()
    expect(parseField(field({ type: 'multi_select', options: ['Lunch, weekdays', 'Dinner'] }), 'Lunch, weekdays; Dinner'))
      .toEqual(['Lunch, weekdays', 'Dinner'])
    expect(parseField(field({ type: 'multi_select', options: ['a', 'b'] }), 'a, z')).toBeUndefined()
    expect(parseField(field({ type: 'location' }), 'The Mission')).toBe('The Mission')
  })

  it('builds the values and says what is missing or wrong', () => {
    const fields = [
      field({ key: 'where', label: 'Where', type: 'location', required: true }),
      field({ key: 'rent', label: 'Rent up to', type: 'money' }),
      field({ key: 'beds', label: 'Beds', type: 'number' }),
      field({ key: 'files', label: 'Files', type: 'file', required: true }),
      field({ key: 'ok', label: 'Agree', type: 'consent', required: true }),
    ]
    expect(buildFormValues(fields, { rent: 'cheap', beds: '' })).toEqual({
      values: {},
      problems: ['Where is needed.', "Rent up to doesn't look right.", 'Files is needed.'],
    })
    expect(buildFormValues(fields, { where: ' SF ', rent: '$3,500' }, { files: ['a.pdf'] })).toEqual({
      values: { where: 'SF', rent: 3500 },
      problems: [],
    })
  })

  it("starts a field from the server's value", () => {
    expect(initialText('SF')).toBe('SF')
    expect(initialText(3500)).toBe('3500')
    expect(initialText(true)).toBe('yes')
    expect(initialText(['a', 2])).toBe('a, 2')
    expect(initialText(null)).toBe('')
  })

  it("shows a refused form's reasons, else the server's words", () => {
    const refused = new ApiError('x', 422, { detail: { code: 'form_invalid', errors: { b: 'Beds is needed.', a: 'Where is needed.' } } })
    expect(formErrorText(refused, 'fallback')).toBe('Where is needed. Beds is needed.')
    expect(formErrorText(new ApiError('That form has closed. Ask Espresso again.', 409, { detail: 'That form has closed. Ask Espresso again.' }), 'fallback'))
      .toBe('That form has closed. Ask Espresso again.')
    expect(formErrorText(new Error('boom'), 'fallback')).toBe('fallback')
  })
})

describe('chat cards', () => {
  it('leads and says what it is doing', () => {
    expect(taskCardLead({ event: 'started', status: 'queued' })).toBe('Started a task')
    expect(taskCardLead({ event: 'update', status: 'done' })).toBe('Task done')
    expect(taskCardLead({ event: 'update', status: 'failed' })).toBe('Task stopped')
    expect(taskCardBody({ event: 'started' })).toMatch(/background/)
    expect(taskCardBody({ event: 'update', headline: '5 balms under $15', note: 'Done' })).toBe('5 balms under $15')
    expect(taskCardBody({ event: 'update', headline: null, note: '' })).toBeNull()
    expect(cardFacts({ b: '$9', a: '4.5 ★', c: null, d: 'In stock', e: 'Ships free', f: 'Vegan' })).toBe('$9 · 4.5 ★ · In stock · Ships free')
  })
})

describe('links', () => {
  it('opens only http(s) links', () => {
    expect(webUrl('https://drbronner.com/x')).toBe('https://drbronner.com/x')
    expect(webUrl('javascript:alert(1)')).toBeNull()
    expect(webUrl('not a url')).toBeNull()
    expect(webUrl(null)).toBeNull()
  })

  it('names a site, or the part of Google it is', () => {
    expect(linkLabel('https://www.drbronner.com/p/1')).toBe('drbronner.com')
    expect(linkLabel('https://www.google.com/maps/place/x')).toBe('Google Maps')
    expect(linkLabel('https://www.google.com/shopping/product/1')).toBe('Google Shopping')
    expect(linkLabel('https://www.google.com/search?q=x&ibp=oshop')).toBe('Google Shopping')
    expect(linkLabel('https://www.google.com/search?q=x')).toBe('google.com')
  })

  it('hands Espresso the same words as the Mac', () => {
    expect(askEspressoPrompt('t1')).toBe('Help me with my task t1. Read it first.\n\nMy instructions: ')
    expect(askEspressoPrompt('t1', 'i1')).toBe('Help me with the finding i1 in my task t1. Read the task first.\n\nMy instructions: ')
  })
})
