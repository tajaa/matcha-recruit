import { describe, it, expect, beforeEach } from 'vitest';
import { vibeChecksApi } from '../xp';
import {
  mockFetchSuccess,
  mockFetchError,
  mockFetchNetworkError,
  getFetchMock,
} from '../../test/mocks/fetch';
import {
  mockVibeCheckConfig,
  mockVibeAnalytics,
  mockVibeCheckResponse,
} from '../../test/fixtures/xp';

const API_BASE = '/api';

describe('vibeChecksApi', () => {
  beforeEach(() => {
    localStorage.setItem('matcha_access_token', 'test-token');
  });

  describe('getConfig', () => {
    it('fetches config from correct endpoint', async () => {
      mockFetchSuccess(mockVibeCheckConfig);

      const result = await vibeChecksApi.getConfig();

      expect(result).toEqual(mockVibeCheckConfig);

      const mock = getFetchMock();
      expect(mock).toHaveBeenCalledTimes(1);

      const [url, options] = mock.mock.calls[0];
      expect(url).toBe(`${API_BASE}/v1/xp/vibe-checks/config`);
      expect(options.method).toBeUndefined(); // GET is default
      expect(options.headers.Authorization).toBe('Bearer test-token');
      expect(options.headers['Content-Type']).toBe('application/json');
    });

    it('throws on 404 response', async () => {
      mockFetchError('Config not found', 404);

      await expect(vibeChecksApi.getConfig()).rejects.toThrow('Config not found');
    });

    it('throws on 401 unauthorized', async () => {
      mockFetchError('Unauthorized', 401);

      await expect(vibeChecksApi.getConfig()).rejects.toThrow();
    });

    it('throws on 500 server error', async () => {
      mockFetchError('Internal Server Error', 500);

      await expect(vibeChecksApi.getConfig()).rejects.toThrow();
    });

    it('throws on network failure', async () => {
      mockFetchNetworkError('Failed to fetch');

      await expect(vibeChecksApi.getConfig()).rejects.toThrow('Failed to fetch');
    });
  });

  describe('updateConfig', () => {
    it('sends PATCH request with correct payload', async () => {
      const updates = { enabled: false, frequency: 'monthly' as const };
      const updatedConfig = { ...mockVibeCheckConfig, ...updates };
      mockFetchSuccess(updatedConfig);

      const result = await vibeChecksApi.updateConfig(updates);

      expect(result).toEqual(updatedConfig);

      const mock = getFetchMock();
      const [url, options] = mock.mock.calls[0];
      expect(url).toBe(`${API_BASE}/v1/xp/vibe-checks/config`);
      expect(options.method).toBe('PATCH');
      expect(JSON.parse(options.body)).toEqual(updates);
    });

    it('handles partial updates', async () => {
      const updates = { enabled: true };
      mockFetchSuccess({ ...mockVibeCheckConfig, ...updates });

      await vibeChecksApi.updateConfig(updates);

      const mock = getFetchMock();
      const [, options] = mock.mock.calls[0];
      expect(JSON.parse(options.body)).toEqual({ enabled: true });
    });
  });

  describe('getAnalytics', () => {
    it('fetches analytics with period parameter', async () => {
      mockFetchSuccess(mockVibeAnalytics);

      const result = await vibeChecksApi.getAnalytics('week');

      expect(result).toEqual(mockVibeAnalytics);

      const mock = getFetchMock();
      const [url] = mock.mock.calls[0];
      expect(url).toBe(`${API_BASE}/v1/xp/vibe-checks/analytics?period=week`);
    });

    it('includes manager_id when provided', async () => {
      mockFetchSuccess(mockVibeAnalytics);

      await vibeChecksApi.getAnalytics('month', 'manager-123');

      const mock = getFetchMock();
      const [url] = mock.mock.calls[0];
      expect(url).toContain('period=month');
      expect(url).toContain('manager_id=manager-123');
    });

    it('handles all period values', async () => {
      const periods = ['week', 'month', 'quarter'];

      for (const period of periods) {
        mockFetchSuccess({ ...mockVibeAnalytics, period });
        await vibeChecksApi.getAnalytics(period);

        const mock = getFetchMock();
        const [url] = mock.mock.calls[mock.mock.calls.length - 1];
        expect(url).toContain(`period=${period}`);
      }
    });
  });

  describe('getResponses', () => {
    it('fetches responses with pagination parameters', async () => {
      const responses = [mockVibeCheckResponse];
      mockFetchSuccess(responses);

      const result = await vibeChecksApi.getResponses(25, 50);

      expect(result).toEqual(responses);

      const mock = getFetchMock();
      const [url] = mock.mock.calls[0];
      expect(url).toContain('limit=25');
      expect(url).toContain('offset=50');
    });

    it('uses default pagination values', async () => {
      mockFetchSuccess([mockVibeCheckResponse]);

      await vibeChecksApi.getResponses();

      const mock = getFetchMock();
      const [url] = mock.mock.calls[0];
      expect(url).toContain('limit=50');
      expect(url).toContain('offset=0');
    });

    it('includes employee_id when provided', async () => {
      mockFetchSuccess([mockVibeCheckResponse]);

      await vibeChecksApi.getResponses(50, 0, 'emp-123');

      const mock = getFetchMock();
      const [url] = mock.mock.calls[0];
      expect(url).toContain('employee_id=emp-123');
    });

    it('returns empty array when no responses', async () => {
      mockFetchSuccess([]);

      const result = await vibeChecksApi.getResponses();

      expect(result).toEqual([]);
    });
  });

  describe('submitResponse', () => {
    it('sends POST request with mood and comment', async () => {
      const data = { mood_rating: 4, comment: 'Great day!' };
      mockFetchSuccess(mockVibeCheckResponse);

      const result = await vibeChecksApi.submitResponse(data);

      expect(result).toEqual(mockVibeCheckResponse);

      const mock = getFetchMock();
      const [url, options] = mock.mock.calls[0];
      expect(url).toBe(`${API_BASE}/vibe-checks`);
      expect(options.method).toBe('POST');
      expect(JSON.parse(options.body)).toEqual(data);
    });

    it('allows submission without comment', async () => {
      const data = { mood_rating: 3 };
      mockFetchSuccess({ ...mockVibeCheckResponse, comment: undefined });

      await vibeChecksApi.submitResponse(data);

      const mock = getFetchMock();
      const [, options] = mock.mock.calls[0];
      expect(JSON.parse(options.body)).toEqual({ mood_rating: 3 });
    });

    it('validates mood_rating is included', async () => {
      const data = { mood_rating: 5, comment: '' };
      mockFetchSuccess(mockVibeCheckResponse);

      await vibeChecksApi.submitResponse(data);

      const mock = getFetchMock();
      const [, options] = mock.mock.calls[0];
      const body = JSON.parse(options.body);
      expect(body.mood_rating).toBe(5);
    });
  });

  describe('getHistory', () => {
    it('fetches user vibe check history', async () => {
      const history = [mockVibeCheckResponse, { ...mockVibeCheckResponse, id: 'response-2' }];
      mockFetchSuccess(history);

      const result = await vibeChecksApi.getHistory();

      expect(result).toEqual(history);

      const mock = getFetchMock();
      const [url] = mock.mock.calls[0];
      expect(url).toBe(`${API_BASE}/vibe-checks/history`);
    });

    it('returns empty array for new users', async () => {
      mockFetchSuccess([]);

      const result = await vibeChecksApi.getHistory();

      expect(result).toEqual([]);
    });
  });

  describe('authentication', () => {
    it('includes Bearer token from localStorage', async () => {
      localStorage.setItem('matcha_access_token', 'my-secret-token');
      mockFetchSuccess(mockVibeCheckConfig);

      await vibeChecksApi.getConfig();

      const mock = getFetchMock();
      const [, options] = mock.mock.calls[0];
      expect(options.headers.Authorization).toBe('Bearer my-secret-token');
    });

    it('sends null token when not authenticated', async () => {
      localStorage.clear();
      mockFetchSuccess(mockVibeCheckConfig);

      await vibeChecksApi.getConfig();

      const mock = getFetchMock();
      const [, options] = mock.mock.calls[0];
      // This documents current behavior - ideally should throw or redirect
      expect(options.headers.Authorization).toBe('Bearer null');
    });
  });

  describe('error messages', () => {
    it('preserves error message from server', async () => {
      mockFetchError('Validation failed: mood_rating must be 1-5', 400);

      await expect(vibeChecksApi.submitResponse({ mood_rating: 0 })).rejects.toThrow(
        'Validation failed: mood_rating must be 1-5'
      );
    });

    it('provides fallback message for empty error response', async () => {
      mockFetchError('', 500);

      await expect(vibeChecksApi.getConfig()).rejects.toThrow();
    });
  });
});
