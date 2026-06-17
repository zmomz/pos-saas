import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { useTheme } from '@/contexts/ThemeContext';
import { User, Globe, Bell, Palette, Shield, Sun, Moon, Check } from 'lucide-react';
import { changePassword, getUserPreferences, saveUserPreferences, type NotificationPrefs } from '@/lib/api';
import PageHeading from '@/components/dashboard/rx/PageHeading';

export default function UserProfile() {
  const { language, setLanguage, t } = useLanguage();
  const tt = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };
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
  // Local change-password control (ISSUE-097): replaces the atoms.dev
  // "managed by auth provider" placeholder now that auth is local.
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [pwSaving, setPwSaving] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);
  const [pwSuccess, setPwSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Load the server-persisted profile so it follows the user across devices.
    // Fall back to the local cache only if the server is unreachable.
    getUserPreferences()
      .then((prefs) => {
        if (cancelled) return;
        setDisplayName(prefs.display_name || '');
        setNotifPrefs(prefs.notification_prefs);
      })
      .catch(() => {
        if (cancelled) return;
        setDisplayName(localStorage.getItem('pos-display-name') || '');
        const cached = localStorage.getItem('pos-notification-prefs');
        if (cached) {
          try {
            setNotifPrefs(JSON.parse(cached));
          } catch {
            // use defaults
          }
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSaveProfile() {
    setSaving(true);
    try {
      await saveUserPreferences({ display_name: displayName, notification_prefs: notifPrefs });
      // Keep a local cache for instant paint / offline fallback.
      localStorage.setItem('pos-display-name', displayName);
      localStorage.setItem('pos-notification-prefs', JSON.stringify(notifPrefs));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword() {
    setPwError(null);
    setPwSuccess(false);
    if (newPassword.length < 8) {
      setPwError(t('password_too_short'));
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setPwError(t('passwords_do_not_match'));
      return;
    }
    setPwSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
      setPwSuccess(true);
      setTimeout(() => setPwSuccess(false), 3000);
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setPwError(detail || (err instanceof Error ? err.message : t('change_password_failed')));
    } finally {
      setPwSaving(false);
    }
  }

  function toggleNotifPref(key: keyof NotificationPrefs) {
    setNotifPrefs((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeading
        icon={<span className="dxr-sw dxr-sw-brand h-9 w-9"><User className="h-[18px] w-[18px]" /></span>}
        title={tt('profile', 'Profile')}
        subtitle={tt('profile_subtitle', 'Manage your account, preferences and security')}
      />

      <div className="max-w-3xl space-y-6">
        {/* Profile Section */}
        <div className="dxr-tile space-y-4">
          <h2 className="text-foreground flex items-center gap-2 font-semibold">
            <User className="h-5 w-5 text-brand-400" />
            {tt('profile', 'Profile')}
          </h2>
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 rounded-full bg-brand-600/30 flex items-center justify-center">
              <User className="h-8 w-8 text-brand-400" />
            </div>
            <div className="flex-1">
              <label className="text-sm text-muted-foreground mb-1 block">{tt('display_name', 'Display Name')}</label>
              <Input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={tt('your_name', 'Your name')}
                className="max-w-sm"
              />
            </div>
          </div>
        </div>

        {/* Language Preference */}
        <div className="dxr-tile space-y-4">
          <h2 className="text-foreground flex items-center gap-2 font-semibold">
            <Globe className="h-5 w-5 text-success" />
            {t('language')}
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {languageOptions.map((opt) => (
              <Button
                key={opt.value}
                onClick={() => setLanguage(opt.value as Language)}
                variant={language === opt.value ? 'default' : 'outline'}
              >
                {opt.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Theme Preference */}
        <div className="dxr-tile space-y-4">
          <h2 className="text-foreground flex items-center gap-2 font-semibold">
            <Palette className="h-5 w-5 text-violet" />
            {tt('theme', 'Theme')}
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <Button
              onClick={() => { if (isDark) toggleTheme(); }}
              variant={!isDark ? 'default' : 'outline'}
            >
              <Sun className="h-4 w-4 me-2" /> {tt('light', 'Light')}
            </Button>
            <Button
              onClick={() => { if (!isDark) toggleTheme(); }}
              variant={isDark ? 'default' : 'outline'}
            >
              <Moon className="h-4 w-4 me-2" /> {tt('dark', 'Dark')}
            </Button>
          </div>
        </div>

        {/* Notification Preferences */}
        <div className="dxr-tile space-y-3">
          <h2 className="text-foreground flex items-center gap-2 font-semibold">
            <Bell className="h-5 w-5 text-warning" />
            {t('notifications')}
          </h2>
          {[
            { key: 'email_alerts' as const, label: tt('email_alerts', 'Email Alerts'), desc: tt('email_alerts_desc', 'Receive important updates via email') },
            { key: 'low_stock_alerts' as const, label: tt('low_stock_alerts', 'Low Stock Alerts'), desc: tt('low_stock_alerts_desc', 'Get notified when products are running low') },
            { key: 'daily_summary' as const, label: tt('daily_summary', 'Daily Summary'), desc: tt('daily_summary_desc', 'Receive a daily sales summary') },
            { key: 'transaction_alerts' as const, label: tt('transaction_alerts', 'Transaction Alerts'), desc: tt('transaction_alerts_desc', 'Get notified for each transaction') },
          ].map((item) => (
            <div key={item.key} className="flex items-center justify-between py-2 border-b border-border last:border-0">
              <div>
                <p className="text-foreground text-sm font-medium">{item.label}</p>
                <p className="text-muted-foreground text-xs">{item.desc}</p>
              </div>
              <Button
                size="sm"
                onClick={() => toggleNotifPref(item.key)}
                className={notifPrefs[item.key]
                  ? 'bg-success hover:bg-success/90 text-white'
                  : 'bg-muted hover:bg-muted text-muted-foreground'
                }
              >
                {notifPrefs[item.key] ? tt('on', 'On') : tt('off', 'Off')}
              </Button>
            </div>
          ))}
        </div>

        {/* Session Info */}
        <div className="dxr-tile space-y-3">
          <h2 className="text-foreground flex items-center gap-2 font-semibold">
            <Shield className="h-5 w-5 text-danger" />
            {tt('security_and_sessions', 'Security & Sessions')}
          </h2>
          <div className="flex items-center justify-between py-2">
            <div>
              <p className="text-foreground text-sm font-medium">{tt('current_session', 'Current Session')}</p>
              <p className="text-muted-foreground text-xs">{tt('active_now', 'Active now')}</p>
            </div>
            <Badge className="pill-success">{tt('active', 'Active')}</Badge>
          </div>
          <div className="py-2 border-t border-border space-y-3">
            <p className="text-foreground text-sm font-medium">{t('change_password')}</p>
            <Input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder={t('current_password')}
              className="max-w-sm"
            />
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={t('new_password')}
              className="max-w-sm"
            />
            <Input
              type="password"
              value={confirmNewPassword}
              onChange={(e) => setConfirmNewPassword(e.target.value)}
              placeholder={t('confirm_password')}
              className="max-w-sm"
            />
            {pwError && <p className="text-sm text-danger">{pwError}</p>}
            {pwSuccess && <p className="text-sm text-success">{t('password_changed')}</p>}
            <Button
              size="sm"
              onClick={handleChangePassword}
              disabled={pwSaving}
            >
              {pwSaving ? t('saving') : t('change_password')}
            </Button>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex gap-3">
          <Button onClick={handleSaveProfile} disabled={saving}>
            {saving ? t('loading') : saved ? (
              <>
                <Check className="h-4 w-4 me-2" />
                {tt('saved', 'Saved!')}
              </>
            ) : t('save_changes')}
          </Button>
        </div>
      </div>
    </div>
  );
}