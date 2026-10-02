import { beforeEach, describe, expect, it, vi } from 'vitest'

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }))
vi.mock('../client', () => ({ api: { post: postMock, get: vi.fn(), patch: vi.fn() } }))

import { ASSIGN_BATCH_SIZE, PartialAssignmentError, assignEmployeesToStore } from './scheduleStores'

const ids = (count: number) => Array.from({ length: count }, (_, index) => `e${index}`)

beforeEach(() => {
  postMock.mockReset()
  postMock.mockImplementation(async (_path: string, body: { employee_ids: string[] }) => ({
    assigned: body.employee_ids, skipped: [],
  }))
})

describe('assignEmployeesToStore', () => {
  it('splits a roster larger than one request may carry', async () => {
    // A 1,000-row import can leave more than the server's 500-id cap waiting,
    // and the dialog's default is "everyone". One request 422'd and assigned
    // nobody; batches assign them all.
    const result = await assignEmployeesToStore('loc-1', ids(ASSIGN_BATCH_SIZE * 2 + 1))

    expect(postMock.mock.calls.map(([, body]) => body.employee_ids.length)).toEqual([500, 500, 1])
    expect(postMock.mock.calls.every(([path]) => path === '/employee-schedule/locations/loc-1/employees')).toBe(true)
    expect(result.assigned).toHaveLength(1001)
  })

  it('sends one request when everyone fits, and merges skipped ids', async () => {
    postMock.mockResolvedValueOnce({ assigned: ['e0'], skipped: ['e1'] })

    expect(await assignEmployeesToStore('loc-1', ids(2))).toEqual({ assigned: ['e0'], skipped: ['e1'] })
    expect(postMock).toHaveBeenCalledTimes(1)
  })

  it('says what landed when a later batch fails', async () => {
    const down = new Error('Service unavailable')
    postMock.mockImplementationOnce(async (_path: string, body: { employee_ids: string[] }) => ({
      assigned: body.employee_ids, skipped: [],
    })).mockRejectedValueOnce(down)

    const failure = await assignEmployeesToStore('loc-1', ids(ASSIGN_BATCH_SIZE + 5)).catch((caught) => caught)

    expect(failure).toBeInstanceOf(PartialAssignmentError)
    expect(failure.assigned).toHaveLength(ASSIGN_BATCH_SIZE)
    expect(failure.cause).toBe(down)
  })

  it('passes a first-batch failure through untouched: nothing was assigned', async () => {
    const refused = new Error('Not authorized')
    postMock.mockReset().mockRejectedValue(refused)

    await expect(assignEmployeesToStore('loc-1', ids(3))).rejects.toBe(refused)
  })
})
