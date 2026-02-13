export const RELEASE_KEY = '2026-02-walkthrough-v1';

function getStorageKey(userId: string): string {
  return `matcha_feature_guides:${RELEASE_KEY}:${userId}`;
}

export function getSeenGuides(userId: string): Set<string> {
  try {
    const raw = localStorage.getItem(getStorageKey(userId));
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

export function markGuideSeen(guideId: string, userId: string): void {
  const seen = getSeenGuides(userId);
  seen.add(guideId);
  localStorage.setItem(getStorageKey(userId), JSON.stringify([...seen]));
}

export function hasSeenGuide(guideId: string, userId: string): boolean {
  return getSeenGuides(userId).has(guideId);
}

export function clearAllGuides(userId: string): void {
  localStorage.removeItem(getStorageKey(userId));
}
