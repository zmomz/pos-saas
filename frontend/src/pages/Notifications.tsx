import { useState, useEffect } from 'react';
import { Bell, AlertTriangle, CheckCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { getNotifications, markNotificationRead } from '@/lib/api';
import ErrorState from '@/components/states/ErrorState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';

interface Notification {
  id: string;
  type: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export default function Notifications() {
  const { language, t, tt, isRTL } = useLanguage();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    fetchNotifications();
  }, []);

  async function fetchNotifications() {
    try {
      setLoading(true);
      setError(false);
      setDenied(false);
      const data = await getNotifications();
      setNotifications(data?.notifications || []);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) setDenied(true);
      else setError(true);
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleMarkRead(id: string) {
    try {
      await markNotificationRead(id);
      setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    } catch {
      // silent fail
    }
  }

  async function handleMarkAllRead() {
    try {
      const unread = notifications.filter((n) => !n.is_read);
      await Promise.all(unread.map((n) => markNotificationRead(n.id)));
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch {
      // silent fail
    }
  }

  function formatTime(dateStr: string) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString(
        language === 'ar' ? 'ar-SA' : language === 'hi' ? 'hi-IN' : language === 'ur' ? 'ur-PK' : 'en-US',
        { dateStyle: 'medium', timeStyle: 'short' }
      );
    } catch {
      return dateStr;
    }
  }

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const title = t('notifications');
  const markAllLabel = t('mark_all_read');
  const emptyLabel = t('no_notifications');

  return (
    <div className="animate-fade-up space-y-5" dir={isRTL ? 'rtl' : 'ltr'}>
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-9 w-9"><Bell className="h-[18px] w-[18px]" /></span>}
        title={title}
        subtitle={unreadCount > 0 ? `${unreadCount} ${tt('unread', 'unread')}` : tt('all_caught_up', 'All caught up')}
      >
        {unreadCount > 0 && (
          <Button variant="outline" size="sm" onClick={handleMarkAllRead}>
            <CheckCheck className="h-4 w-4" />
            {markAllLabel}
          </Button>
        )}
      </PageHeading>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand border-t-transparent" />
          <span className="ms-3 text-muted-foreground">{t('loading')}</span>
        </div>
      )}

      {!loading && denied && <PermissionDenied />}
      {!loading && !denied && error && <ErrorState onRetry={fetchNotifications} />}

      {!loading && !denied && !error && notifications.length === 0 && (
        <div className="dxr-tile flex flex-col items-center justify-center py-20 text-muted-foreground">
          <Bell className="mb-4 h-16 w-16 opacity-25" />
          <p className="text-lg">{emptyLabel}</p>
        </div>
      )}

      {!loading && !denied && !error && notifications.length > 0 && (
        <div className="space-y-3">
          {notifications.map((n) => {
            const isLow = n.type === 'low_stock';
            return (
              <div
                key={n.id}
                onClick={() => !n.is_read && handleMarkRead(n.id)}
                className={cn(
                  'dxr-tile dxr-hover flex items-start gap-4 cursor-pointer p-4',
                  !n.is_read ? 'border-s-4 border-s-brand' : 'opacity-70'
                )}
              >
                <span className={cn('dxr-sw h-10 w-10', isLow ? 'dxr-sw-warning' : 'dxr-sw-brand')}>
                  {isLow ? <AlertTriangle className="h-5 w-5" /> : <Bell className="h-5 w-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cn('text-sm', !n.is_read ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
                    {n.message}
                  </p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">{formatTime(n.created_at)}</p>
                </div>
                {!n.is_read && <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-brand" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
