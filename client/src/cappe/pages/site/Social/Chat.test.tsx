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

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset())
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
    await waitFor(() => expect(onPosted).toHaveBeenCalledWith('Post scheduled.'))
    const [path, body] = api.post.mock.calls[1]
    expect(path).toBe('/sites/s-1/social/chat/conversations/conv1/plans/plan1/confirm')
    expect(body).toEqual({
      revision: 1, mode: 'at', when_local: '2026-10-21T14:00', connection_ids: ['c-ig'], keep_link: false,
      posts: [{ instagram: { caption: 'Oat latte season.', hashtags: ['#oatlatte', '#coffee'] },
        facebook: { text: 'Our oat latte is back.' }, alt_text: 'A latte' }],
    })
    expect(await screen.findByText(/Done — the post is in the Queue/)).toBeInTheDocument()
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
    await waitFor(() => expect(onPosted).toHaveBeenCalledWith('Post going out now.'))
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
    api.get.mockResolvedValue({ id: 'conv1', title: 'Latte', plan: { ...CARD, status: 'executed', post_ids: ['p1', 'p2'] },
      messages: [{ id: 'm1', role: 'user', content: 'post it', attachments: [], created_at: '2026-10-20T10:00:00Z' }] })
    show()
    expect(await screen.findByText('post it')).toBeInTheDocument()
    expect(screen.getByText(/2 posts are in the Queue/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }))
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
})
