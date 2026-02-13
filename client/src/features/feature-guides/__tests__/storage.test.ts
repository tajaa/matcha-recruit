import { describe, it, expect, beforeEach } from 'vitest';
import { getSeenGuides, markGuideSeen, hasSeenGuide, clearAllGuides } from '../storage';

describe('feature-guides storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns empty set for new user', () => {
    const seen = getSeenGuides('user-1');
    expect(seen.size).toBe(0);
  });

  it('markGuideSeen persists correctly', () => {
    markGuideSeen('compliance', 'user-1');
    const seen = getSeenGuides('user-1');
    expect(seen.has('compliance')).toBe(true);
    expect(seen.size).toBe(1);
  });

  it('hasSeenGuide returns true after marking', () => {
    expect(hasSeenGuide('ir-list', 'user-1')).toBe(false);
    markGuideSeen('ir-list', 'user-1');
    expect(hasSeenGuide('ir-list', 'user-1')).toBe(true);
  });

  it('persists multiple guides', () => {
    markGuideSeen('compliance', 'user-1');
    markGuideSeen('ir-list', 'user-1');
    markGuideSeen('er-copilot', 'user-1');

    const seen = getSeenGuides('user-1');
    expect(seen.size).toBe(3);
    expect(seen.has('compliance')).toBe(true);
    expect(seen.has('ir-list')).toBe(true);
    expect(seen.has('er-copilot')).toBe(true);
  });

  it('storage is scoped by userId', () => {
    markGuideSeen('compliance', 'user-1');
    expect(hasSeenGuide('compliance', 'user-1')).toBe(true);
    expect(hasSeenGuide('compliance', 'user-2')).toBe(false);
  });

  it('storage is scoped by release key', () => {
    markGuideSeen('compliance', 'user-1');
    // The key includes the release version, so a different release would not see this
    const key = Object.keys(localStorage).find(k => k.includes('matcha_feature_guides'));
    expect(key).toContain('2026-02-walkthrough-v1');
  });

  it('clearAllGuides removes all seen guides for user', () => {
    markGuideSeen('compliance', 'user-1');
    markGuideSeen('ir-list', 'user-1');
    expect(getSeenGuides('user-1').size).toBe(2);

    clearAllGuides('user-1');
    expect(getSeenGuides('user-1').size).toBe(0);
  });

  it('clearAllGuides does not affect other users', () => {
    markGuideSeen('compliance', 'user-1');
    markGuideSeen('compliance', 'user-2');

    clearAllGuides('user-1');
    expect(hasSeenGuide('compliance', 'user-1')).toBe(false);
    expect(hasSeenGuide('compliance', 'user-2')).toBe(true);
  });

  it('handles corrupted localStorage gracefully', () => {
    localStorage.setItem('matcha_feature_guides:2026-02-walkthrough-v1:user-1', '{invalid');
    const seen = getSeenGuides('user-1');
    expect(seen.size).toBe(0);
  });
});
