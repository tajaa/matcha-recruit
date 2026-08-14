import { describe, expect, it } from 'vitest'
import { resolveLegacyChannelTarget } from './LegacySurfaceRedirect'

describe('resolveLegacyChannelTarget', () => {
  it('routes Operations channels to the Ops shell', () => {
    expect(resolveLegacyChannelTarget(
      { channel_scope: 'operations' },
      'channel-1',
      '?message=msg-1',
    )).toBe('/ops/channels/channel-1?message=msg-1')
  })

  it('routes project discussions through the project chat tab', () => {
    expect(resolveLegacyChannelTarget(
      { channel_scope: 'project_discussion', project_id: 'project-1' },
      'channel-1',
      '',
    )).toBe('/work/projects/project-1?tab=chat')
  })

  it('keeps community channels in the current shell', () => {
    expect(resolveLegacyChannelTarget(
      { channel_scope: 'community' },
      'channel-1',
      '',
    )).toBeNull()
  })
})
