import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Notifications from './Notifications'

const { apiGetMock, apiPostMock } = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPostMock: vi.fn(),
}))

vi.mock('../../../api/client', () => ({
  api: { get: apiGetMock, post: apiPostMock },
}))

function renderNotifications() {
  return render(
    <MemoryRouter>
      <Notifications />
    </MemoryRouter>,
  )
}

function workspaceNotification(index: number) {
  return {
    id: `workspace-${index}`,
    type: 'schedule_request_pending',
    title: `Workspace ${index}`,
    body: null,
    link: '/ops/schedule?tab=requests',
    created_at: new Date(Date.UTC(2026, 7, 28, 12, 0, 0) - index * 1_000).toISOString(),
  }
}

describe('Notifications feed', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    apiPostMock.mockReset()
  })

  it('keeps dashboard activity visible when the workspace feed fails', async () => {
    apiGetMock.mockImplementation((path: string) => {
      if (path.startsWith('/dashboard/notifications')) {
        return Promise.resolve({
          items: [{
            id: 'dashboard-1',
            type: 'employee',
            title: 'Dashboard event',
            subtitle: null,
            severity: null,
            status: null,
            created_at: '2026-08-28T12:00:00Z',
            link: '/app/employees/dashboard-1',
          }],
          total: 1,
        })
      }
      return Promise.reject(new Error('workspace unavailable'))
    })

    renderNotifications()

    expect(await screen.findByText('Dashboard event')).toBeInTheDocument()
    expect(screen.getByText('Some notifications could not be loaded. Use Load more to retry.')).toBeInTheDocument()
    expect(screen.getByText('1 loaded')).toBeInTheDocument()
  })

  it('paginates workspace notifications and keeps the real combined total', async () => {
    apiGetMock.mockImplementation((path: string) => {
      if (path.startsWith('/dashboard/notifications')) {
        return Promise.resolve({ items: [], total: 0 })
      }
      if (path.includes('offset=30')) {
        return Promise.resolve({ notifications: [workspaceNotification(30)], total: 31 })
      }
      return Promise.resolve({
        notifications: Array.from({ length: 30 }, (_, index) => workspaceNotification(index)),
        total: 31,
      })
    })

    renderNotifications()

    expect(await screen.findByText('31 total')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Load more (1 remaining)' }))

    expect(await screen.findByText('Workspace 30')).toBeInTheDocument()
    await waitFor(() => expect(apiGetMock).toHaveBeenCalledWith(
      '/matcha-work/notifications?limit=30&offset=30',
    ))
    expect(screen.queryByRole('button', { name: /Load more/ })).not.toBeInTheDocument()
  })
})
