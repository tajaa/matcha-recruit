import { useState, useEffect } from 'react';

export function useIsLightMode(): boolean {
  const check = () => !document.documentElement.classList.contains('theme-dark');
  const [isLight, setIsLight] = useState(check);
  useEffect(() => {
    const observer = new MutationObserver(() => setIsLight(check()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);
  return isLight;
}
