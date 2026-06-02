import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, AlertTriangle, ArrowLeft, CheckCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { getNotifications, markNotificationRead } from '@/lib/api';

interface Notification {
  id: string;
  type: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export default function Notifications() {
  const navigate = useNavigate();
  const { language, setLanguage, t, isRTL } = useLanguage();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchNotifications();
  }, []);

  async function fetchNotifications() {
    try {
      setLoading(true);
      const data = await getNotifications();
      setNotifications(data?.notifications || []);
    } catch {
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleMarkRead(id: string) {
    try {
      await markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
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

  function getIcon(type: string) {
    if (type === 'low_stock') {
      return <AlertTriangle className="h-5 w-5 text-amber-400" />;
    }
    return <Bell className="h-5 w-5 text-blue-400" />;
  }

  function formatTime(dateStr: string) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString(language === 'ar' ? 'ar-SA' : language === 'hi' ? 'hi-IN' : language === 'ur' ? 'ur-PK' : 'en-US', {
        dateStyle: 'medium',
        timeStyle: 'short',
      });
    } catch {
      return dateStr;
    }
  }

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div className={`min-h-screen bg-slate-900 text-white ${isRTL ? 'rtl' : 'ltr'}`} dir={isRTL ? 'rtl' : 'ltr'}>
      {/* Header */}
      <header className="border-b border-slate-700 bg-slate-800 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate(-1)}
              className="text-slate-300 hover:text-white"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-xl font-bold">
              {language === 'ar' ? 'الإشعارات' : language === 'hi' ? 'सूचनाएं' : language === 'ur' ? 'اطلاعات' : 'Notifications'}
            </h1>
            {unreadCount > 0 && (
              <Badge className="bg-blue-600 text-white">{unreadCount}</Badge>
            )}
          </div>
          <Select value={language} onValueChange={(val) => setLanguage(val as Language)}>
            <SelectTrigger className="w-32 border-slate-700 bg-slate-700 text-white">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="border-slate-700 bg-slate-800 text-white">
              {languageOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-4xl p-6">
        {/* Mark all read button */}
        {unreadCount > 0 && (
          <div className="mb-4 flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={handleMarkAllRead}
              className="border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
            >
              <CheckCheck className="mr-2 h-4 w-4" />
              {language === 'ar' ? 'تحديد الكل كمقروء' : language === 'hi' ? 'सभी पढ़ा हुआ चिह्नित करें' : language === 'ur' ? 'سب پڑھا ہوا نشان زد کریں' : 'Mark all as read'}
            </Button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
            <span className="ml-3 text-slate-400">{t('loading')}</span>
          </div>
        )}

        {/* Empty state */}
        {!loading && notifications.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-slate-400">
            <Bell className="mb-4 h-16 w-16 opacity-30" />
            <p className="text-lg">
              {language === 'ar' ? 'لا توجد إشعارات' : language === 'hi' ? 'कोई सूचना नहीं' : language === 'ur' ? 'کوئی اطلاعات نہیں' : 'No notifications'}
            </p>
          </div>
        )}

        {/* Notification list */}
        {!loading && notifications.length > 0 && (
          <div className="space-y-3">
            {notifications.map((notification) => (
              <Card
                key={notification.id}
                className={`cursor-pointer border-slate-700 bg-slate-800 transition-colors hover:bg-slate-750 ${
                  !notification.is_read ? 'border-l-4 border-l-blue-500' : 'opacity-70'
                }`}
                onClick={() => !notification.is_read && handleMarkRead(notification.id)}
              >
                <CardContent className="flex items-start gap-4 p-4">
                  <div className="mt-0.5 flex-shrink-0">
                    {getIcon(notification.type)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm ${!notification.is_read ? 'font-medium text-white' : 'text-slate-400'}`}>
                      {notification.message}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatTime(notification.created_at)}
                    </p>
                  </div>
                  {!notification.is_read && (
                    <div className="flex-shrink-0">
                      <div className="h-2.5 w-2.5 rounded-full bg-blue-500" />
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}