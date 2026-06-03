import { useEffect, useState } from 'react';

/**
 * Shared connectivity signal for the UX-02 offline state (F-051).
 *
 * Every back-office screen must surface an offline banner when the network drops
 * (IB §5 universal rule). Instead of each page re-implementing the
 * `navigator.onLine` + `online`/`offline` listener dance (as FloorMap / POSTerminal
 * once did locally), they read this hook — and the single global <OfflineBanner/>
 * mounted in DashboardLayout uses it to cover every page at once.
 *
 * Returns `true` when online. Safe outside a browser (SSR / prerender) where it
 * assumes online so nothing renders an offline banner during a static build.
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(
    typeof navigator === 'undefined' ? true : navigator.onLine
  );

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    // Re-sync once mounted in case connectivity flipped between the initial
    // render and this effect firing.
    setOnline(typeof navigator === 'undefined' ? true : navigator.onLine);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);

  return online;
}

export default useOnlineStatus;
