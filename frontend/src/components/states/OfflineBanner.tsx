import { useEffect, useState } from 'react';
import { WifiOff } from 'lucide-react';
import { useLanguage } from '@/lib/i18n';
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import { queuedCount } from '@/lib/offlineQueue';

/**
 * Global offline banner (UX-02 / F-051). Mounted once in DashboardLayout so it
 * covers every back-office page at once — the IB §5 universal rule that "an
 * offline banner + queued-count appears whenever the network is down."
 *
 * Renders nothing while online. When the network drops it shows a warning strip
 * plus the number of POS sales still buffered in IndexedDB, so a cashier knows
 * nothing has been lost. The queued-count read is defensive: IndexedDB may be
 * unavailable (SSR / tests) and must never crash the banner.
 */
export default function OfflineBanner() {
  const { t, isRTL } = useLanguage();
  const online = useOnlineStatus();
  const [queued, setQueued] = useState(0);

  useEffect(() => {
    if (online) {
      setQueued(0);
      return;
    }
    let cancelled = false;
    queuedCount()
      .then((n) => {
        if (!cancelled) setQueued(n);
      })
      .catch(() => {
        if (!cancelled) setQueued(0);
      });
    return () => {
      cancelled = true;
    };
  }, [online]);

  if (online) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      dir={isRTL ? 'rtl' : 'ltr'}
      className="flex items-center justify-center gap-2 border-b border-warning/30 bg-warning/15 px-4 py-2 text-sm font-medium text-warning"
    >
      <WifiOff className="h-4 w-4 flex-shrink-0" />
      <span>{t('offline_banner')}</span>
      {queued > 0 && (
        <span className="rounded-full bg-warning/25 px-2 py-0.5 text-xs tabular-nums">
          {queued} {t('queued_sales')}
        </span>
      )}
    </div>
  );
}
