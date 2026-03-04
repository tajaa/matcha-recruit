import { useSyncExternalStore } from 'react';

function subscribe(cb: () => void) {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  return () => observer.disconnect();
}

function getSnapshot(): boolean {
  return document.documentElement.classList.contains('theme-light-pages');
}

function getServerSnapshot(): boolean {
  return false;
}

/** Returns true when the user has toggled light mode via the sidebar theme button. */
export function useIsLightMode(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
