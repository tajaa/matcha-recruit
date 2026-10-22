import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IssuesPage from './issues/IssuesPage'
import IssueEditor from './issues/IssueEditor'
import { addStories, applyTemplate, docOf, fitMasthead, move, newLine, place, removeStory, round1, saveBody } from './issues/issueDoc'
import { MAX_LINES } from './issues/coverVocab'
import type {
  CappeMagazineIssue, CappeMagazineIssueOptions, CappeMagazineIssueSummary, CappePost, ContentsDesign, CoverDesign,
  CoverElement, CoverLine,
} from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postHtml: vi.fn(), upload: vi.fn(), patch: vi.fn() }))
vi.mock('../api', () => ({ cappeApi: api, cappeApiBase: '/api/cappe' }))

const el = (over: Partial<CoverElement> = {}): CoverElement => ({
  x: 4, y: 3, w: 92, size: 16, color: '#ffffff', align: 'center', weight: 'black', case: 'upper', italic: false,
  tracking: 'tight', font: 'heading', ...over,
})
const line = (over: Partial<CoverLine> = {}): CoverLine => ({
  ...el({ x: 6, y: 60, w: 60, size: 6, align: 'left', weight: 'bold', case: 'asis', tracking: 'normal' }),
  text: 'A line', sub: '', post_id: null, box: 'none', box_color: '#000000', ...over,
})
const cover = (over: Partial<CoverDesign> = {}): CoverDesign => ({
  v: 1, template: 'classic', background: '#1b1916',
  photo: { asset_id: null, focal: { x: 50, y: 50 }, zoom: 100, filter: 'none' },
  scrim: { kind: 'top', strength: 45 },
  masthead: el(),
  issue_line: { ...el({ y: 20, size: 2.4, weight: 'regular', tracking: 'wide', font: 'body' }), text: '', hidden: false },
  lines: [line({ text: 'Your cover line' })],
  credit: { corner: 'br', tone: 'light' },
  ...over,
})
const contents: ContentsDesign = {
  v: 1, layout: 'list', heading: 'In this issue', show_numbers: true, show_pictures: true, show_deks: true,
  show_bylines: false, accent: 'accent',
}

const issue = (over: Partial<CappeMagazineIssue> = {}): CappeMagazineIssue => ({
  id: 'i-1', number: 3, title: 'The tide issue', status: 'draft', released_at: null, cover: cover(), contents,
  stories: [{ post_id: 'p-1', section: 'Features', contents_line: null, title: 'Low tide', slug: 'low-tide',
    status: 'published', access: 'free', hidden: false, excerpt: 'Boats.', picture: null }],
  cover_picture: null, hidden: false, published: [], created_at: '2026-10-21T09:00:00Z', updated_at: '2026-10-21T09:00:00Z',
  ...over,
})

const options: CappeMagazineIssueOptions = {
  templates: [
    { key: 'classic', label: 'Classic', cover: cover({ lines: [line({ text: '', x: 5, y: 34 }), line({ text: '', x: 5, y: 54 })] }) },
    { key: 'headline', label: 'Headline', cover: cover({ template: 'headline', scrim: { kind: 'bottom', strength: 60 },
      lines: [line({ text: '', x: 5, y: 64, w: 90, size: 11 })] }) },
  ],
  max_lines: 8, max_stories: 40, next_number: 4,
  taken: [{ post_id: 'p-3', issue_id: 'i-2', number: 2 }, { post_id: 'p-1', issue_id: 'i-1', number: 3 }],
}

const post = (over: Partial<CappePost> = {}) => ({
  id: 'p-1', title: 'Low tide', status: 'published', access: 'free', hidden: false, excerpt: 'Boats.', cover_image_url: null,
  ...over,
}) as CappePost

function answer(routes: Record<string, unknown>) {
  api.get.mockImplementation((path: string) => {
    const hit = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => path.endsWith(k))
    return hit === undefined ? Promise.reject(new Error(`unexpected GET ${path}`)) : Promise.resolve(routes[hit])
  })
}

function mount(path: string, element: React.ReactElement, pattern: string) {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path={pattern} element={element} />
    <Route path="/cappe/sites/:siteId/issues" element={<p>the wall</p>} />
    <Route path="/cappe/sites/:siteId/issues/:issueId" element={<p>an issue</p>} />
  </Routes></MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
  api.postHtml.mockResolvedValue('<!doctype html><p>preview</p>')
})

describe('the issue document', () => {
  it('rounds like the server and keeps a box on the cover', () => {
    expect(round1(4.25)).toBe(4.3)
    expect(round1(4.24)).toBe(4.2)
    expect(place(el(), { w: 3 }).w).toBe(10)
    expect(place(el({ x: 50, w: 40 }), { w: 70 })).toMatchObject({ x: 30, w: 70 })
    expect(place(el(), { y: 140 }).y).toBe(100)
  })

  it('fits the masthead to the name as the server does', () => {
    expect(fitMasthead(cover(), 'Vogue').masthead.size).toBe(16)
    expect(fitMasthead(cover(), 'The Machine').masthead.size).toBe(11.6)
    expect(fitMasthead(cover(), 'x'.repeat(200)).masthead.size).toBe(1.5)
  })

  it('applies a template, keeping the photo and the words in its slots', () => {
    const mine = cover({ photo: { asset_id: 'a-1', focal: { x: 20, y: 30 }, zoom: 140, filter: 'bw' },
      issue_line: { ...cover().issue_line, text: 'Autumn', hidden: true },
      lines: [line({ text: 'One', post_id: 'p-1' }), line({ text: 'Two', sub: 'small', x: 70 })] })
    const next = applyTemplate(mine, options.templates[1], 'The Machine')
    expect(next.template).toBe('headline')
    expect(next.photo).toEqual(mine.photo)
    expect(next.scrim.kind).toBe('bottom')
    expect(next.issue_line).toMatchObject({ text: 'Autumn', hidden: true })
    expect(next.lines[0]).toMatchObject({ text: 'One', post_id: 'p-1', y: 64, size: 11 })
    expect(next.lines[1]).toMatchObject({ text: 'Two', sub: 'small', x: 70 })  // past the slots: its own place
    expect(next.masthead.size).toBe(11.6)
  })

  it('adds lines up to the limit, moves and removes stories', () => {
    expect(newLine(cover())).toMatchObject({ y: 72, text: 'New cover line', x: 6 })
    expect(newLine(cover({ lines: [] }))).toMatchObject({ y: 60 })
    expect(newLine(cover({ lines: Array.from({ length: MAX_LINES }, () => line()) }))).toBeNull()
    expect(move([1, 2, 3], 0, 2)).toEqual([2, 3, 1])
    expect(move([1, 2, 3], 0, -1)).toEqual([1, 2, 3])
    const doc = docOf(issue({ cover: cover({ lines: [line({ post_id: 'p-1' })] }) }))
    const without = removeStory(doc, 'p-1')
    expect(without.stories).toEqual([])
    expect(without.cover.lines[0].post_id).toBeNull()
    expect(addStories(doc, ['p-1', 'p-2']).stories.map((s) => s.post_id)).toEqual(['p-1', 'p-2'])
    expect(addStories(doc, ['p-1'])).toBe(doc)
    expect(saveBody({ ...doc, title: '  ', stories: [{ post_id: 'p-1', section: ' ', contents_line: ' Line ' }] }))
      .toMatchObject({ title: null, stories: [{ post_id: 'p-1', section: null, contents_line: 'Line' }] })
  })
})

describe('IssuesPage', () => {
  it('shows each issue and starts a new one', async () => {
    const summary: CappeMagazineIssueSummary = {
      id: 'i-1', number: 3, title: 'The tide issue', status: 'released', released_at: '2026-10-21T09:00:00Z', cover: cover(),
      cover_picture: { url: 'https://cdn.example.test/a.jpg', alt: 'Boats', credit: 'Photo: Ana' }, hidden: true,
      updated_at: '2026-10-21T09:00:00Z', story_count: 1,
    }
    answer({ '/magazine/issues': [summary, { ...summary, id: 'i-2', number: 2, title: null, status: 'draft', story_count: 4,
      cover_picture: null, hidden: false }] })
    api.post.mockResolvedValue(issue({ id: 'i-9' }))
    mount('/cappe/sites/s-1/issues', <IssuesPage />, '/cappe/sites/:siteId/issues')
    expect(await screen.findByText('The tide issue')).toBeInTheDocument()
    expect(screen.getByText(/1 story ·/)).toBeInTheDocument()
    expect(screen.getByText('4 stories')).toBeInTheDocument()
    expect(screen.getByText('hidden')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /No\. 2/ })).toHaveAttribute('href', '/cappe/sites/s-1/issues/i-2')
    fireEvent.click(screen.getByRole('button', { name: /New issue/ }))
    expect(await screen.findByText('an issue')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/magazine/issues', {})
  })

  it('says when there are none, and when one could not start', async () => {
    answer({ '/magazine/issues': [] })
    api.post.mockRejectedValue(new Error('This magazine has run out of issue numbers.'))
    mount('/cappe/sites/s-1/issues', <IssuesPage />, '/cappe/sites/:siteId/issues')
    expect(await screen.findByText(/No issues yet/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /New issue/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('run out')
  })
})

function editor(over: Partial<CappeMagazineIssue> = {}, posts: CappePost[] = [post()]) {
  answer({
    '/magazine/issues/i-1': issue(over),
    '/magazine/issues/options': options,
    '/posts': posts,
    '/assets': { assets: [{ id: 'a-1', url: 'https://cdn.example.test/a.jpg', alt: 'Boats', credit_line: 'Photo: Ana', kind: 'upload' }] },
    '/magazine': { name: 'The Machine' },
  })
  return mount('/cappe/sites/s-1/issues/i-1?view=outline', <IssueEditor />, '/cappe/sites/:siteId/issues/:issueId')
}

describe('IssueEditor', () => {
  it('adds stories, sets their sections, and saves the issue', async () => {
    editor({}, [post(), post({ id: 'p-2', title: 'Night market', status: 'draft' }), post({ id: 'p-3', title: 'Taken' }),
      post({ id: 'p-4', title: 'Old', status: 'archived' })])
    expect(await screen.findByText('Low tide')).toBeInTheDocument()
    await waitFor(() => expect(api.postHtml).toHaveBeenCalledWith('/sites/s-1/magazine/issues/preview',
      expect.objectContaining({ issue_id: 'i-1', number: 3 })))
    fireEvent.click(screen.getByRole('button', { name: /Add stories/ }))
    const picker = screen.getByRole('dialog', { name: 'Add stories' })
    expect(within(picker).getByText('In No. 2')).toBeInTheDocument()
    expect(within(picker).queryByText('Old')).not.toBeInTheDocument()
    const boxes = within(picker).getAllByRole('checkbox')
    expect(boxes[1]).toBeDisabled()  // in another issue
    fireEvent.click(boxes[0])
    fireEvent.click(within(picker).getByRole('button', { name: 'Add 1 story' }))
    expect(screen.getByText('Night market')).toBeInTheDocument()
    expect(screen.getByText(/it is published when you release the issue/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Section for Night market'), { target: { value: 'Food' } })
    fireEvent.click(screen.getByRole('button', { name: 'Move Night market up' }))
    api.put.mockImplementation((_path: string, body: Record<string, unknown>) => Promise.resolve(issue({
      stories: (body.stories as { post_id: string; section: string | null }[]).map((s) => ({ ...issue().stories[0], ...s })),
    })))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [path, body] = api.put.mock.calls[0]
    expect(path).toBe('/sites/s-1/magazine/issues/i-1')
    expect(body.stories).toEqual([{ post_id: 'p-2', section: 'Food', contents_line: null },
      { post_id: 'p-1', section: 'Features', contents_line: null }])
    await waitFor(() => expect(screen.queryByText('Unsaved')).not.toBeInTheDocument())
  })

  it('takes a story out with its cover link, and undoes it', async () => {
    editor({ cover: cover({ lines: [line({ text: 'Low tide', post_id: 'p-1' })] }) })
    fireEvent.click(await screen.findByRole('button', { name: 'Take Low tide out' }))
    expect(screen.queryByText('Low tide')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(screen.getByText('Low tide')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Cover' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Low tide' }))
    expect((screen.getByLabelText('Opens the story') as HTMLSelectElement).value).toBe('')
  })

  it('designs the cover: a template, the photo, words and their place', async () => {
    editor()
    fireEvent.click(await screen.findByRole('tab', { name: 'Cover' }))
    fireEvent.click(screen.getByRole('button', { name: 'Headline' }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose cover photo' }))
    expect(screen.getByRole('dialog', { name: 'Choose the cover photo' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close picker' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Your cover line' }))
    fireEvent.change(screen.getByLabelText('Cover line words'), { target: { value: 'Low tide' } })
    fireEvent.change(screen.getByLabelText('Opens the story'), { target: { value: 'p-1' } })
    fireEvent.change(screen.getByLabelText('Width'), { target: { value: '60' } })
    fireEvent.change(screen.getByLabelText('Across'), { target: { value: '12.34' } })
    fireEvent.change(screen.getByLabelText('Box behind it'), { target: { value: 'solid' } })
    fireEvent.click(screen.getAllByLabelText('Magazine accent')[1])
    fireEvent.click(screen.getByRole('button', { name: /Cover line/ }))
    expect(screen.getByLabelText('Cover line words')).toHaveValue('New cover line')
    fireEvent.click(screen.getByRole('button', { name: /Remove this line/ }))
    fireEvent.click(screen.getByRole('tab', { name: 'Issue line' }))
    fireEvent.change(screen.getByLabelText('Issue line words'), { target: { value: 'Autumn' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Hide it/ }))
    fireEvent.click(screen.getByRole('tab', { name: 'Masthead' }))
    expect(screen.getByText(/“The Machine”/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Size'), { target: { value: '9' } })
    fireEvent.change(screen.getByLabelText('Darken behind the words'), { target: { value: 'full' } })
    fireEvent.change(screen.getByLabelText('Corner'), { target: { value: 'tl' } })
    api.put.mockResolvedValue(issue())
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const sent = api.put.mock.calls[0][1].cover as CoverDesign
    expect(sent.template).toBe('headline')
    expect(sent.lines).toHaveLength(1)
    expect(sent.lines[0]).toMatchObject({ text: 'Low tide', post_id: 'p-1', x: 12.3, w: 60, box: 'solid', color: 'accent', size: 11 })
    expect(sent.issue_line).toMatchObject({ text: 'Autumn', hidden: true })
    expect(sent.masthead.size).toBe(9)
    expect(sent.scrim.kind).toBe('full')
    expect(sent.credit.corner).toBe('tl')
  })

  it('designs the contents', async () => {
    editor()
    fireEvent.click(await screen.findByRole('tab', { name: 'Contents' }))
    fireEvent.click(screen.getByRole('button', { name: /Grid of pictures/ }))
    fireEvent.change(screen.getByPlaceholderText('No heading'), { target: { value: 'Inside' } })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Bylines' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Magazine accent' }))
    api.put.mockResolvedValue(issue())
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1].contents).toMatchObject({ layout: 'grid', heading: 'Inside', show_bylines: true, accent: '#b45309' })
  })

  it('releases the issue, saving first, and says what it published', async () => {
    editor({}, [post({ status: 'draft' })])
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.change(await screen.findByLabelText('Issue title'), { target: { value: 'Autumn' } })
    api.put.mockResolvedValue(issue({ title: 'Autumn' }))
    api.post.mockResolvedValue(issue({ title: 'Autumn', status: 'released', released_at: '2026-10-21T10:00:00Z',
      published: ['Low tide'] }))
    fireEvent.click(screen.getByRole('button', { name: 'Release No. 3' }))
    expect(await screen.findByText('Published with the issue: Low tide.')).toBeInTheDocument()
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Its draft story will be published with it.'))
    expect(api.put).toHaveBeenCalled()
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/magazine/issues/i-1/release')
    expect(screen.getByRole('button', { name: 'Withdraw' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Delete issue/ })).not.toBeInTheDocument()
  })

  it('on a released issue, says a save publishes the drafts added, and withdraws', async () => {
    editor({ status: 'released', released_at: '2026-10-21T10:00:00Z' },
      [post(), post({ id: 'p-2', title: 'Night market', status: 'draft' })])
    fireEvent.click(await screen.findByRole('button', { name: /Add stories/ }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Add stories' })).getAllByRole('checkbox')[0])
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 story' }))
    expect(screen.getByRole('button', { name: 'Save and publish 1 draft' })).toBeEnabled()
    expect(screen.getByText(/saving publishes it with the issue/)).toBeInTheDocument()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.post.mockResolvedValue(issue())
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/magazine/issues/i-1/withdraw'))
  })

  it('shows what went wrong, and deletes a draft', async () => {
    editor()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    fireEvent.change(await screen.findByLabelText('Issue number'), { target: { value: '2' } })
    api.put.mockRejectedValue(new Error('No. 2 is already taken. Choose another number.'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already taken')
    api.delete.mockResolvedValue(undefined)
    fireEvent.click(screen.getByRole('button', { name: /Delete issue/ }))
    expect(await screen.findByText('the wall')).toBeInTheDocument()
  })

  it('cannot load an issue that is gone', async () => {
    api.get.mockRejectedValue(new Error('Issue not found'))
    mount('/cappe/sites/s-1/issues/i-1?view=outline', <IssueEditor />, '/cappe/sites/:siteId/issues/:issueId')
    expect(await screen.findByRole('alert')).toHaveTextContent('Issue not found')
  })
})
