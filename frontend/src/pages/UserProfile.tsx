import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { useTheme } from '@/contexts/ThemeContext';
import { User, Globe, Bell, Palette, Shield, Sun, Moon } from 'lucide-react';

interface NotificationPrefs {
  email_alerts: boolean;
  low_stock_alerts: boolean;
  daily_summary: boolean;
  transaction_alerts: boolean;
}

export default function UserProfile() {
  const { language, setLanguage, t } = useLanguage();
  const { theme, toggleTheme, isDark } = useTheme();
  const [displayName, setDisplayName] = useState('');
  const [notifPrefs, setNotifPrefs] = useState<NotificationPrefs>({
    email_alerts: true,
    low_stock_alerts: true,
    daily_summary: false,
    transaction_alerts: true,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const savedName = localStorage.getItem('pos-display-name') || '';
    setDisplayName(savedName);
    const savedPrefs = localStorage.getItem('pos-notification-prefs');
    if (savedPrefs) {
      try {
        setNotifPrefs(JSON.parse(savedPrefs));
      } catch {
        // use defaults
      }
    }
  }, []);

  function handleSaveProfile() {
    setSaving(true);
    localStorage.setItem('pos-display-name', displayName);
    localStorage.setItem('pos-notification-prefs', JSON.stringify(notifPrefs));
    setTimeout(() => {
      setSaving(false);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }, 500);
  }

  function toggleNotifPref(key: keyof NotificationPrefs) {
    setNotifPrefs((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Profile Section */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <User className="h-5 w-5 text-blue-400" />
            Profile
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-full bg-blue-600/30 flex items-center justify-center">
              <User className="h-8 w-8 text-blue-400" />
            </div>
            <div className="flex-1">
              <label className="text-sm text-slate-400 mb-1 block">Display Name</label>
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your name"
                className="bg-slate-700 border-slate-600 text-white max-w-sm"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Language Preference */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Globe className="h-5 w-5 text-green-400" />
            {t('language')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {languageOptions.map((opt) => (
              <Button
                key={opt.value}
                onClick={() => setLanguage(opt.value as Language)}
                className={language === opt.value
                  ? 'bg-blue-600 text-white border-blue-500'
                  : 'bg-slate-700 text-slate-300 border-slate-600 hover:bg-slate-600'
                }
                variant="outline"
              >
                {opt.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Theme Preference */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Palette className="h-5 w-5 text-purple-400" />
            Theme
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3">
            <Button
              onClick={() => { if (isDark) toggleTheme(); }}
              className={!isDark
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }
              variant="outline"
            >
              <Sun className="h-4 w-4 mr-2" /> Light
            </Button>
            <Button
              onClick={() => { if (!isDark) toggleTheme(); }}
              className={isDark
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }
              variant="outline"
            >
              <Moon className="h-4 w-4 mr-2" /> Dark
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Notification Preferences */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Bell className="h-5 w-5 text-yellow-400" />
            {t('notifications')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {[
            { key: 'email_alerts' as const, label: 'Email Alerts', desc: 'Receive important updates via email' },
            { key: 'low_stock_alerts' as const, label: 'Low Stock Alerts', desc: 'Get notified when products are running low' },
            { key: 'daily_summary' as const, label: 'Daily Summary', desc: 'Receive a daily sales summary' },
            { key: 'transaction_alerts' as const, label: 'Transaction Alerts', desc: 'Get notified for each transaction' },
          ].map((item) => (
            <div key={item.key} className="flex items-center justify-between py-2 border-b border-slate-700 last:border-0">
              <div>
                <p className="text-white text-sm font-medium">{item.label}</p>
                <p className="text-slate-400 text-xs">{item.desc}</p>
              </div>
              <Button
                size="sm"
                onClick={() => toggleNotifPref(item.key)}
                className={notifPrefs[item.key]
                  ? 'bg-green-600 hover:bg-green-700 text-white'
                  : 'bg-slate-700 hover:bg-slate-600 text-slate-400'
                }
              >
                {notifPrefs[item.key] ? 'On' : 'Off'}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Session Info */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            <Shield className="h-5 w-5 text-red-400" />
            Security & Sessions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between py-2">
            <div>
              <p className="text-white text-sm font-medium">Current Session</p>
              <p className="text-slate-400 text-xs">Active now</p>
            </div>
            <Badge className="bg-green-500/20 text-green-400">Active</Badge>
          </div>
          <div className="flex items-center justify-between py-2 border-t border-slate-700">
            <div>
              <p className="text-white text-sm font-medium">Change Password</p>
              <p className="text-slate-400 text-xs">Managed by authentication provider</p>
            </div>
            <Button size="sm" variant="outline" disabled className="border-slate-600 text-slate-500">
              Via Auth Provider
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex gap-3">
        <Button onClick={handleSaveProfile} disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white">
          {saving ? t('loading') : saved ? '✓ Saved!' : t('save_changes')}
        </Button>
      </div>
    </div>
  );
}