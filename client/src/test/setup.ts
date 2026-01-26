import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

// Store original fetch to restore later
const originalFetch = global.fetch;

beforeEach(() => {
  // Clear any mocks from previous tests
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();

  // Restore original fetch if it was mocked
  global.fetch = originalFetch;
});

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock ResizeObserver (needed for Recharts and other resize-dependent components)
class ResizeObserverMock {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
global.ResizeObserver = ResizeObserverMock;

// Mock IntersectionObserver (needed for lazy loading, infinite scroll, etc.)
class IntersectionObserverMock {
  readonly root: Element | null = null;
  readonly rootMargin: string = '';
  readonly thresholds: ReadonlyArray<number> = [];
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = vi.fn().mockReturnValue([]);
}
global.IntersectionObserver = IntersectionObserverMock;

// Suppress console.error for expected errors in tests
// Uncomment if you want to suppress React act() warnings during development
// const originalError = console.error;
// console.error = (...args: unknown[]) => {
//   if (typeof args[0] === 'string' && args[0].includes('act(')) return;
//   originalError.apply(console, args);
// };
