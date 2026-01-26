import { vi, type Mock } from 'vitest';

type MockResponse = {
  ok: boolean;
  status: number;
  statusText: string;
  headers: Headers;
  json: () => Promise<unknown>;
  text: () => Promise<string>;
  clone: () => MockResponse;
};

function createMockResponse(data: unknown, status: number, ok: boolean): MockResponse {
  const response: MockResponse = {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'Content-Type': 'application/json' }),
    json: async () => data,
    text: async () => JSON.stringify(data),
    clone: () => createMockResponse(data, status, ok),
  };
  return response;
}

/**
 * Mock fetch to return a successful response.
 * Supports multiple sequential calls with different responses.
 */
export function mockFetchSuccess<T>(responseData: T, status = 200): Mock {
  const mock = vi.fn().mockResolvedValue(createMockResponse(responseData, status, true));
  global.fetch = mock;
  return mock;
}

/**
 * Mock fetch to return an error response.
 */
export function mockFetchError(message = 'Network error', status = 500): Mock {
  const mock = vi.fn().mockResolvedValue(createMockResponse(message, status, false));
  global.fetch = mock;
  return mock;
}

/**
 * Mock fetch to reject with a network error (not an HTTP error).
 */
export function mockFetchNetworkError(message = 'Network error'): Mock {
  const mock = vi.fn().mockRejectedValue(new Error(message));
  global.fetch = mock;
  return mock;
}

/**
 * Mock fetch with sequential responses for testing retry logic or multiple calls.
 */
export function mockFetchSequence(responses: Array<{ data: unknown; status?: number; ok?: boolean }>): Mock {
  const mock = vi.fn();
  responses.forEach((response, index) => {
    const { data, status = 200, ok = true } = response;
    mock.mockResolvedValueOnce(createMockResponse(data, status, ok));
  });
  global.fetch = mock;
  return mock;
}

/**
 * Reset only the fetch mock, not all mocks.
 */
export function resetFetchMock(): void {
  if (global.fetch && typeof (global.fetch as Mock).mockRestore === 'function') {
    (global.fetch as Mock).mockRestore();
  }
}

/**
 * Get the fetch mock for assertions.
 */
export function getFetchMock(): Mock {
  return global.fetch as Mock;
}

/**
 * Assert fetch was called with specific URL and options.
 */
export function expectFetchCalledWith(urlPattern: string | RegExp, options?: Partial<RequestInit>): void {
  const mock = getFetchMock();
  expect(mock).toHaveBeenCalled();

  const calls = mock.mock.calls;
  const matchingCall = calls.find(([url]: [string]) => {
    if (typeof urlPattern === 'string') {
      return url.includes(urlPattern);
    }
    return urlPattern.test(url);
  });

  expect(matchingCall).toBeDefined();

  if (options && matchingCall) {
    expect(matchingCall[1]).toMatchObject(options);
  }
}
