import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Chat from './Chat'
import type { CappeSocialConnection, CappeSocialPlanCard, CappeSocialSettings } from '../../../types'

const api = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(), upload: vi.fn(),
}))
vi.mock('../../../api', () => ({ cappeApi: api }))

const IG: CappeSocialConnection = {
  id: 'c-ig', platform: 'instagram', external_id: 'ig1', handle: 'pocoffee', display_name: 'pocoffee', avatar_url: null,
  status: 'connected', last_error: null, followers_count: 10, metrics: {}, metrics_at: null, token_expires_at: null,
  connected_at: '2026-10-01T00:00:00Z',
}
const FB: CappeSocialConnection = { ...IG, id: 'c-fb', platform: 'facebook', handle: null, display_name: 'Po Coffee' }
const SETTINGS: CappeSocialSettings = {
  autoreply_mode: 'off', reply_to_comments: true, reply_to_messages: true, tone: 'friendly', business_facts: '',
  signature: null, default_hashtags: [], max_auto_per_hour: 20, escalate_words: [], autoreply_available: true,
  video_available: true, ai_available: true,
}
const CARD: CappeSocialPlanCard = {
  id: 'plan1', status: 'proposed', revision: 1, model: 'claude-haiku-5-5', created_at: null, post_ids: [],
  plan: {
    when: { mode: 'at', local: '2026-10-21T14:00', scheduled_at: '2026-10-21T21:00:00Z',
      label: 'Wed, Oct 21 · 2:00 PM PDT', source: 'owner' },
    accounts: [{ connection_id: 'c-ig', platform: 'instagram', handle: 'pocoffee' },
      { connection_id: 'c-fb', platform: 'facebook', handle: 'Po Coffee' }],
    link: { kind: 'product', product_id: 'p1', product_name: 'Oat Latte', url: 'https://po.example.test/shop/oat-latte' },
    posts: [{ items: [1], media: [{ kind: 'image', url: 'https://cdn.example.test/cappe/social/a.jpg' }],
      instagram: { caption: 'Meet the oat latte.', hashtags: ['#oatlatte', '#coffee'] },
      facebook: { text: 'Our oat latte is back.' }, alt_text: 'A latte', offset_days: 0 }],
    spread_days: 0, warnings: ['TikTok can’t be posted to yet — this goes to Instagram and Facebook.'], needs: [],
  },
}

function show(onPosted = vi.fn(), settings = SETTINGS) {
  render(<Chat siteId="s-1" connections={[IG, FB]} settings={settings} onPosted={onPosted} />)
  return onPosted
}

// The chat list loads on every mount; anything else a test asks for is its own.
function getting(chat?: unknown, chats: unknown[] = []) {
  api.get.mockImplementation((path: string) => Promise.resolve(path.endsWith('/chat/conversations') ? chats : chat))
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
  getting()
  try { localStorage.clear() } catch { /* no storage in this runner */ }
})

describe('Chat', () => {
  it('turns a message into a plan card with each network’s copy', async () => {
    api.post.mockResolvedValue({ conversation_id: 'conv1', plan: CARD, message: {
      id: 'm2', role: 'assistant', content: 'Two posts, tomorrow at 2pm.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post this everywhere at 2pm tomorrow' } })
    fireEvent.keyDown(screen.getByLabelText('Message'), { key: 'Enter' })
    expect(await screen.findByText('Two posts, tomorrow at 2pm.')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/sites/s-1/social/chat/turns', {
      conversation_id: null, message: 'post this everywhere at 2pm tomorrow', attachments: [] })
    const card = screen.getByLabelText('Plan')
    expect(within(card).getByLabelText('Instagram caption')).toHaveValue('Meet the oat latte.')
    expect(within(card).getByLabelText('Hashtags')).toHaveValue('#oatlatte #coffee')
    expect(within(card).getByLabelText('Facebook text')).toHaveValue('Our oat latte is back.')
    expect(within(card).getByText('Oat Latte')).toBeInTheDocument()
    expect(within(card).getByText('Wed, Oct 21 · 2:00 PM PDT')).toBeInTheDocument()
    expect(within(card).getByText(/TikTok can’t be posted to yet/)).toBeInTheDocument()
    expect(within(card).getByLabelText('When')).toHaveValue('2026-10-21T14:00')
  })

  it('confirms the plan as edited, by revision', async () => {
    api.post.mockResolvedValueOnce({ conversation_id: 'conv1', plan: CARD, message: {
      id: 'm2', role: 'assistant', content: 'Planned.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    const onPosted = show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByLabelText('Plan')
    fireEvent.change(within(card).getByLabelText('Instagram caption'), { target: { value: 'Oat latte season.' } })
    fireEvent.click(within(card).getByRole('checkbox', { name: /facebook/i }))
    fireEvent.click(within(card).getByRole('checkbox', { name: /Oat Latte/ }))
    api.post.mockResolvedValueOnce({ plan: { ...CARD, status: 'executed', post_ids: ['p-1'] }, posts: [] })
    fireEvent.click(within(card).getByRole('button', { name: 'Schedule post' }))
    await waitFor(() => expect(onPosted).toHaveBeenCalledWith('Post scheduled.', 'queue'))
    const [path, body] = api.post.mock.calls[1]
    expect(path).toBe('/sites/s-1/social/chat/conversations/conv1/plans/plan1/confirm')
    expect(body).toEqual({
      revision: 1, mode: 'at', when_local: '2026-10-21T14:00', connection_ids: ['c-ig'], keep_link: false,
      posts: [{ instagram: { caption: 'Oat latte season.', hashtags: ['#oatlatte', '#coffee'] },
        facebook: { text: 'Our oat latte is back.' }, alt_text: 'A latte', tiktok: null, youtube: null }],
      exports: null,
    })
    expect(await screen.findByText(/Done — the post is in the Queue/)).toBeInTheDocument()
  })

  it('leaves out an account that was disconnected since the plan was made', async () => {
    api.post.mockResolvedValueOnce({ conversation_id: 'conv1', plan: CARD, message: {
      id: 'm2', role: 'assistant', content: 'Planned.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    render(<Chat siteId="s-1" connections={[IG, { ...FB, status: 'expired' }]} settings={SETTINGS} onPosted={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByLabelText('Plan')
    api.post.mockResolvedValueOnce({ plan: { ...CARD, status: 'executed', post_ids: ['p-1'] }, posts: [] })
    fireEvent.click(within(card).getByRole('button', { name: 'Schedule post' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
    expect(api.post.mock.calls[1][1].connection_ids).toEqual(['c-ig'])
  })

  it('does not start a second turn while one is running', async () => {
    let finish: (v: unknown) => void = () => {}
    api.post.mockReturnValueOnce(new Promise((resolve) => { finish = resolve }))
    show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post it' } })
    fireEvent.keyDown(screen.getByLabelText('Message'), { key: 'Enter' })
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'and again' } })
    fireEvent.keyDown(screen.getByLabelText('Message'), { key: 'Enter' })
    expect(api.post).toHaveBeenCalledTimes(1)
    finish({ conversation_id: 'conv1', plan: null, message: {
      id: 'm2', role: 'assistant', content: 'What would you like to post?', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    expect(await screen.findByText('What would you like to post?')).toBeInTheDocument()
  })

  it('posts now or saves drafts, and can set a plan aside', async () => {
    api.post.mockResolvedValueOnce({ conversation_id: 'conv1', plan: CARD, message: {
      id: 'm2', role: 'assistant', content: 'Planned.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    const onPosted = show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByLabelText('Plan')
    fireEvent.click(within(card).getByRole('button', { name: 'Post now' }))
    api.post.mockResolvedValueOnce({ plan: { ...CARD, status: 'executed', post_ids: ['p-1'] }, posts: [] })
    fireEvent.click(within(card).getByRole('button', { name: 'Post it now' }))
    await waitFor(() => expect(onPosted).toHaveBeenCalledWith('Post going out now.', 'queue'))
    expect(api.post.mock.calls[1][1]).toMatchObject({ mode: 'now', when_local: null })
  })

  it('sets a plan aside', async () => {
    api.post.mockResolvedValueOnce({ conversation_id: 'conv1', plan: CARD, message: {
      id: 'm2', role: 'assistant', content: 'Planned.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByLabelText('Plan')
    api.post.mockResolvedValueOnce({ ...CARD, status: 'dismissed' })
    fireEvent.click(within(card).getByRole('button', { name: 'Not this' }))
    expect(await screen.findByText('This plan was set aside.')).toBeInTheDocument()
    expect(api.post.mock.calls[1][0]).toBe('/sites/s-1/social/chat/conversations/conv1/plans/plan1/dismiss')
  })

  it('keeps the message when the turn fails', async () => {
    api.post.mockRejectedValue(new Error('Couldn’t plan that just now — try again in a moment.'))
    show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t plan that just now')
    expect(screen.getByLabelText('Message')).toHaveValue('post it')
  })

  it('sends dropped photos with the message and refuses an empty send', async () => {
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }))
    show()
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Drop a photo or a video, or say what to post')
    api.upload.mockResolvedValue({ url: 'https://cdn.example.test/cappe/social/a.jpg', width: 1, height: 1, padded: false })
    const photo = new File([new Uint8Array(4)], 'latte.jpg', { type: 'image/jpeg' })
    fireEvent.change(screen.getByLabelText('Attach files'), { target: { files: [photo] } })
    await waitFor(() => expect(api.upload).toHaveBeenCalled())
    api.post.mockResolvedValue({ conversation_id: 'conv1', plan: null, message: {
      id: 'm2', role: 'assistant', content: 'What should it say?', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    await waitFor(() => expect(screen.getByRole('img', { name: 'latte.jpg' })).toHaveAttribute(
      'src', 'https://cdn.example.test/cappe/social/a.jpg'))
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/s-1/social/chat/turns', {
      conversation_id: null, message: '',
      attachments: [{ kind: 'image', url: 'https://cdn.example.test/cappe/social/a.jpg', name: 'latte.jpg' }] }))
    expect(await screen.findByText('What should it say?')).toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('reopens the last chat and can start a new one', async () => {
    try { localStorage.setItem('cappe-social-chat:s-1', 'conv1') } catch { return }
    getting({ id: 'conv1', title: 'Latte', plan: { ...CARD, status: 'executed', post_ids: ['p1', 'p2'] },
      messages: [{ id: 'm1', role: 'user', content: 'post it', attachments: [], created_at: '2026-10-20T10:00:00Z' }] })
    show()
    expect(await screen.findByText('post it')).toBeInTheDocument()
    expect(screen.getByText(/2 posts are in the Queue/)).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'New chat' }).at(-1)!)
    expect(screen.queryByText('post it')).not.toBeInTheDocument()
    expect(localStorage.getItem('cappe-social-chat:s-1')).toBeNull()
  })

  it('says when there is no assistant and when video needs a plan', async () => {
    show(vi.fn(), { ...SETTINGS, ai_available: false, video_available: false })
    expect(screen.getByText(/needs Claude set up/)).toBeInTheDocument()
    expect(screen.getByLabelText('Message')).toBeDisabled()
    const clip = new File([new Uint8Array(4)], 'clip.mp4', { type: 'video/mp4' })
    fireEvent.change(screen.getByLabelText('Attach files'), { target: { files: [clip] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Video posts are part of the Business, Pro and Creator plans.')
  })

  it('lists past chats, opens, renames and deletes them', async () => {
    const chats = [
      { id: 'conv1', title: 'Latte launch', created_at: null, updated_at: new Date().toISOString(), last: 'Here’s a plan', plan_status: 'proposed' },
      { id: 'conv2', title: 'Old', created_at: null, updated_at: '2026-10-01T00:00:00Z', last: null, plan_status: 'executed' },
    ]
    getting({ id: 'conv2', title: 'Old', plan: null,
      messages: [{ id: 'm9', role: 'user', content: 'from before', attachments: [], created_at: '2026-10-01T00:00:00Z' }] }, chats)
    show()
    const list = (await screen.findAllByRole('navigation', { name: 'Chats' }))[0]
    expect(await within(list).findByText('Latte launch')).toBeInTheDocument()
    expect(within(list).getByLabelText('Plan waiting')).toBeInTheDocument()
    expect(within(list).getByText(/Here’s a plan/)).toBeInTheDocument()
    fireEvent.click(within(list).getByText('Old'))
    expect(await screen.findByText('from before')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/sites/s-1/social/chat/conversations/conv2')
    expect(localStorage.getItem('cappe-social-chat:s-1')).toBe('conv2')

    api.patch.mockResolvedValue({})
    fireEvent.click(within(list).getByRole('button', { name: 'Rename Latte launch' }))
    const input = within(list).getByLabelText('Chat name')
    fireEvent.change(input, { target: { value: 'Fall launch' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(api.patch).toHaveBeenCalledWith('/sites/s-1/social/chat/conversations/conv1', { title: 'Fall launch' })
    expect(await within(list).findByText('Fall launch')).toBeInTheDocument()

    api.delete.mockResolvedValue(undefined)
    fireEvent.click(within(list).getByRole('button', { name: 'Delete Old' }))
    await waitFor(() => expect(within(list).queryByText('Old')).not.toBeInTheDocument())
    expect(api.delete).toHaveBeenCalledWith('/sites/s-1/social/chat/conversations/conv2')
    expect(screen.queryByText('from before')).not.toBeInTheDocument()  // it was open: a new chat starts
  })

  it('says so when a chat is gone, and a failed rename reloads the list', async () => {
    const chats = [
      { id: 'conv1', title: 'Gone', created_at: null, updated_at: '2026-10-01T00:00:00Z', last: null, plan_status: null },
      { id: 'conv2', title: 'Kept', created_at: null, updated_at: '2026-10-01T00:00:00Z', last: null, plan_status: null },
    ]
    api.get.mockImplementation((path: string) => (path.endsWith('/chat/conversations')
      ? Promise.resolve(chats) : Promise.reject(new Error('404'))))
    show()
    const list = (await screen.findAllByRole('navigation', { name: 'Chats' }))[0]
    fireEvent.click(await within(list).findByText('Gone'))
    expect(await screen.findByRole('alert')).toHaveTextContent('That chat is gone')
    expect(within(list).queryByText('Gone')).not.toBeInTheDocument()
    api.patch.mockRejectedValue(new Error('nope'))
    fireEvent.click(within(list).getByRole('button', { name: 'Rename Kept' }))
    const input = within(list).getByLabelText('Chat name')
    fireEvent.change(input, { target: { value: 'New name' } })
    fireEvent.blur(input)
    expect(await within(list).findByText('Kept')).toBeInTheDocument()
    expect(within(list).queryByText('New name')).not.toBeInTheDocument()
  })

  it('makes only files for a video when asked, and sends the TikTok and YouTube words', async () => {
    const filesCard: CappeSocialPlanCard = {
      ...CARD,
      plan: {
        ...CARD.plan, warnings: [],
        posts: [{ ...CARD.plan.posts[0], media: [{ kind: 'video', asset_id: 'a1', poster: 'https://cdn.example.test/p.jpg' }],
          tiktok: { caption: 'POV: oat latte', hashtags: ['#fyp'] },
          youtube: { title: 'Oat latte is back', description: 'Back for fall.', tags: ['oat latte', 'coffee'] } }],
        exports: { platforms: ['instagram', 'tiktok', 'youtube'], captions: true, items: [1], reason: 'asked',
          files_only: true, note: 'Nothing is posted: you’ll get files for Instagram, TikTok and YouTube to download from Exports.' },
      },
    }
    api.post.mockResolvedValueOnce({ conversation_id: 'conv1', plan: filesCard, message: {
      id: 'm2', role: 'assistant', content: 'Files coming up.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    const onPosted = show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'prepare for all platforms with captions' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByLabelText('Plan')
    expect(within(card).getByText(/Nothing is posted: you’ll get files/)).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Files only' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(card).queryByText('Post to')).not.toBeInTheDocument()
    expect(within(card).getByRole('checkbox', { name: 'Word-for-word captions' })).toBeChecked()
    fireEvent.change(within(card).getByLabelText('TikTok caption'), { target: { value: 'Oat latte szn' } })
    fireEvent.change(within(card).getByLabelText(/YouTube tags/), { target: { value: 'oat latte, fall, ' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Instagram file' }))
    api.post.mockResolvedValueOnce({ plan: { ...filesCard, status: 'executed', post_ids: [], export_ids: ['e1'] },
      posts: [], exports: [{ id: 'e1' }] })
    fireEvent.click(within(card).getByRole('button', { name: 'Prepare files' }))
    await waitFor(() => expect(onPosted).toHaveBeenCalledWith('Files being prepared in Exports.', 'exports'))
    const body = api.post.mock.calls[1][1]
    expect(body).toMatchObject({ mode: 'export', connection_ids: [], exports: { platforms: ['tiktok', 'youtube'], captions: true } })
    expect(body.posts[0].tiktok).toEqual({ caption: 'Oat latte szn', hashtags: ['#fyp'] })
    expect(body.posts[0].youtube).toEqual({ title: 'Oat latte is back', description: 'Back for fall.', tags: ['oat latte', 'fall'] })
    expect(await screen.findByText(/the files are in Exports/)).toBeInTheDocument()
  })

  it('posts and prepares files together, and refuses files with no platform', async () => {
    const both: CappeSocialPlanCard = {
      ...CARD,
      plan: { ...CARD.plan, posts: [{ ...CARD.plan.posts[0], tiktok: { caption: 'tt', hashtags: [] },
        youtube: { title: 'yt', description: 'd', tags: [] } }],
        exports: { platforms: ['tiktok', 'youtube'], captions: false, items: [1], reason: 'coming_soon', files_only: false,
          note: 'TikTok and YouTube can’t be posted to yet, so you’ll get files to download and upload yourself.' } },
    }
    api.post.mockResolvedValueOnce({ conversation_id: 'conv1', plan: both, message: {
      id: 'm2', role: 'assistant', content: 'Planned.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    const onPosted = show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post everywhere' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByLabelText('Plan')
    api.post.mockResolvedValueOnce({ plan: { ...both, status: 'executed', post_ids: ['p1'], export_ids: ['e1', 'e2'] },
      posts: [], exports: [{ id: 'e1' }, { id: 'e2' }] })
    fireEvent.click(within(card).getByRole('button', { name: 'Schedule post + prepare files' }))
    await waitFor(() => expect(onPosted).toHaveBeenCalledWith(
      'Post scheduled. Files for 2 videos being prepared in Exports.', 'queue'))
    expect(await screen.findByText(/the post is in the Queue, and files for 2 videos are in Exports/)).toBeInTheDocument()
  })

  it('needs a platform before making files', async () => {
    const files: CappeSocialPlanCard = {
      ...CARD,
      plan: { ...CARD.plan, posts: [{ ...CARD.plan.posts[0], tiktok: { caption: 'tt', hashtags: [] } }],
        exports: { platforms: ['tiktok'], captions: false, items: [1], reason: 'no_accounts', files_only: true, note: 'n' } },
    }
    api.post.mockResolvedValueOnce({ conversation_id: 'conv1', plan: files, message: {
      id: 'm2', role: 'assistant', content: 'Planned.', attachments: [], created_at: '2026-10-20T10:00:00Z' } })
    show()
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'post it' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    const card = await screen.findByLabelText('Plan')
    fireEvent.click(within(card).getByRole('button', { name: 'TikTok file' }))
    fireEvent.click(within(card).getByRole('button', { name: 'Prepare files' }))
    expect(await within(card).findByRole('alert')).toHaveTextContent('Pick at least one platform')
    expect(api.post).toHaveBeenCalledTimes(1)
  })
})
