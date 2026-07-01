import { useState, useEffect } from 'react';
import { Bell, AlertTriangle, CheckCheck, Send, Mail, MessageCircle, Smartphone, CalendarClock } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { SegButton } from '@/components/ui/seg-button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useLanguage } from '@/lib/i18n';
import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import {
  getNotifications,
  markNotificationRead,
  sendNotification,
  type NotificationChannel,
} from '@/lib/api';
import { notifyError } from '@/lib/notify';
import ErrorState from '@/components/states/ErrorState';
import LoadingState from '@/components/states/LoadingState';
import PermissionDenied from '@/components/states/PermissionDenied';
import PageHeading from '@/components/dashboard/rx/PageHeading';

interface Notification {
  id: string;
  type: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

// The channels the composer can target. Each carries its own recipient idiom so
// the field labels itself by what the operator actually types (an email address
// vs. a phone number vs. a device/user), never a generic "to".
const CHANNELS: { value: NotificationChannel; icon: typeof Mail }[] = [
  { value: 'email', icon: Mail },
  { value: 'whatsapp', icon: MessageCircle },
  { value: 'push', icon: Smartphone },
];

export default function Notifications() {
  const { language, t, tt, isRTL } = useLanguage();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [denied, setDenied] = useState(false);

  // Composer state (M10 / parity #8).
  const [composeOpen, setComposeOpen] = useState(false);
  const [channel, setChannel] = useState<NotificationChannel>('email');
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [scheduleOn, setScheduleOn] = useState(false);
  const [scheduledAt, setScheduledAt] = useState('');
  const [sending, setSending] = useState(false);

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

  function resetComposer() {
    setChannel('email');
    setRecipient('');
    setSubject('');
    setBody('');
    setScheduleOn(false);
    setScheduledAt('');
  }

  async function handleSend() {
    setSending(true);
    try {
      const scheduled_at = scheduleOn && scheduledAt ? new Date(scheduledAt).toISOString() : null;
      const res = await sendNotification({
        channel,
        to: recipient.trim(),
        subject: subject.trim() || undefined,
        body,
        scheduled_at,
      });
      // Report the server's real outcome — never claim "sent" when the channel
      // only logged (no provider) or the send was deferred.
      if (res.status === 'scheduled') {
        toast.success(tt('notification_scheduled', 'Notification scheduled'));
      } else if (res.status === 'sent') {
        toast.success(tt('notification_sent', 'Notification sent'));
      } else {
        toast.info(tt('notification_logged', 'Recorded — this channel has no provider configured yet'));
      }
      setComposeOpen(false);
      resetComposer();
    } catch (err) {
      notifyError(err, tt('notification_send_failed', 'Could not send the notification'));
    } finally {
      setSending(false);
    }
  }

  const recipientLabel =
    channel === 'email'
      ? tt('recipient_email', 'Email address')
      : channel === 'whatsapp'
      ? tt('recipient_phone', 'Phone number')
      : tt('recipient_device', 'Device or user');
  const recipientType = channel === 'email' ? 'email' : channel === 'whatsapp' ? 'tel' : 'text';
  const canSend = recipient.trim() !== '' && body.trim() !== '' && (!scheduleOn || scheduledAt !== '');

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
        <Button size="sm" onClick={() => setComposeOpen(true)}>
          <Send className="h-4 w-4" />
          {tt('compose', 'Compose')}
        </Button>
      </PageHeading>

      {loading && <LoadingState />}

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
            // A11y (ISSUE-226): an unread tile is a real control — clicking it
            // marks it read — so it must be keyboard-reachable and activatable
            // and carry an accessible name (WCAG 2.1.1 / 4.1.2). A read tile does
            // nothing on click, so it stays a plain, non-interactive region.
            const interactive = !n.is_read;
            return (
              <div
                key={n.id}
                onClick={() => interactive && handleMarkRead(n.id)}
                role={interactive ? 'button' : undefined}
                tabIndex={interactive ? 0 : undefined}
                aria-label={interactive ? `${tt('mark_read', 'Mark as read')}: ${n.message}` : undefined}
                onKeyDown={
                  interactive
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleMarkRead(n.id);
                        }
                      }
                    : undefined
                }
                className={cn(
                  'dxr-tile dxr-hover flex items-start gap-4 p-4',
                  interactive ? 'cursor-pointer' : 'opacity-70',
                  !n.is_read && 'border-s-4 border-s-brand'
                )}
              >
                <span className={cn('dxr-sw h-10 w-10', isLow ? 'dxr-sw-warning' : 'dxr-sw-brand')}>
                  {isLow ? <AlertTriangle className="h-5 w-5" /> : <Bell className="h-5 w-5" />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cn('text-sm', !n.is_read ? 'font-semibold text-foreground' : 'text-muted-foreground')}>
                    {n.message}
                  </p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">{formatDateTime(n.created_at, language)}</p>
                </div>
                {!n.is_read && <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-brand" />}
              </div>
            );
          })}
        </div>
      )}

      {/* Composer (M10 / parity #8) */}
      <Dialog open={composeOpen} onOpenChange={(o) => { setComposeOpen(o); if (!o) resetComposer(); }}>
        <DialogContent dir={isRTL ? 'rtl' : 'ltr'}>
          <DialogHeader>
            <DialogTitle>{tt('compose_notification', 'Compose notification')}</DialogTitle>
            <DialogDescription>
              {tt('compose_notification_desc', 'Send a message over the channel you choose, or schedule it for later.')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Channel */}
            <div className="space-y-1.5">
              <label className="dxr-eyebrow">{tt('channel', 'Channel')}</label>
              <div className="dxr-seg w-full">
                {CHANNELS.map(({ value, icon: Icon }) => (
                  <SegButton
                    key={value}
                    active={channel === value}
                    onClick={() => setChannel(value)}
                    className="flex-1"
                  >
                    <Icon className="h-4 w-4 me-1.5 inline-block" />
                    {tt(`channel_${value}`, value === 'email' ? 'Email' : value === 'whatsapp' ? 'WhatsApp' : 'Push')}
                  </SegButton>
                ))}
              </div>
            </div>

            {/* Recipient */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">{recipientLabel}</label>
              <Input
                type={recipientType}
                value={recipient}
                onChange={(e) => setRecipient(e.target.value)}
                placeholder={recipientLabel}
              />
            </div>

            {/* Subject */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">{tt('subject', 'Subject')}</label>
              <Input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder={tt('subject_placeholder', 'Optional subject')}
              />
            </div>

            {/* Message */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">{tt('message', 'Message')}</label>
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={tt('message_placeholder', 'Write your message…')}
                rows={4}
              />
            </div>

            {/* Schedule */}
            <div className="space-y-3 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CalendarClock className="h-4 w-4 text-brand-400" />
                  <span className="text-sm font-medium text-foreground">{tt('schedule_for_later', 'Schedule for later')}</span>
                </div>
                <Switch
                  checked={scheduleOn}
                  onCheckedChange={setScheduleOn}
                  aria-label={tt('schedule_for_later', 'Schedule for later')}
                />
              </div>
              {scheduleOn && (
                <Input
                  type="datetime-local"
                  value={scheduledAt}
                  onChange={(e) => setScheduledAt(e.target.value)}
                  aria-label={tt('send_at', 'Send at')}
                />
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setComposeOpen(false); resetComposer(); }}>
              {tt('cancel', 'Cancel')}
            </Button>
            <Button onClick={handleSend} disabled={!canSend || sending}>
              {scheduleOn ? <CalendarClock className="h-4 w-4" /> : <Send className="h-4 w-4" />}
              {sending
                ? t('saving')
                : scheduleOn
                ? tt('schedule', 'Schedule')
                : tt('send', 'Send')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
