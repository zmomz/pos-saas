import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';
import { useTheme } from '@/contexts/ThemeContext';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import { User, Globe, Bell, Palette, Shield, Sun, Moon, Check, KeyRound, Monitor } from 'lucide-react';
import {
  changePassword,
  getUserPreferences,
  saveUserPreferences,
  getActiveSessions,
  revokeSession,
  getMfaStatus,
  enrollMfa,
  activateMfa,
  type NotificationPrefs,
  type SessionInfo,
  type MfaStatus,
  type MfaEnrollResult,
} from '@/lib/api';
import { formatDate } from '@/lib/format';
import PageHeading from '@/components/dashboard/rx/PageHeading';

// Light-touch device label from a user-agent string; surfaces the browser family
// instead of dumping the raw UA. Returns null when nothing recognizable is found.
function deviceLabel(ua?: string | null): string | null {
  if (!ua) return null;
  const m = /(Edg|Edge|OPR|Opera|Chrome|Firefox|Safari)/.exec(ua);
  if (!m) return null;
  return m[1].replace('Edg', 'Edge').replace('OPR', 'Opera');
}

export default function UserProfile() {
  const { language, setLanguage, t, tt } = useLanguage();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  // MFA (#202): status drives the security panel; an in-flight enrollment holds
  // the pending secret until a code is verified; recoveryCodes is shown once.
  const [mfaStatus, setMfaStatus] = useState<MfaStatus | null>(null);
  const [mfaEnroll, setMfaEnroll] = useState<MfaEnrollResult | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaRecoveryCodes, setMfaRecoveryCodes] = useState<string[] | null>(null);
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const { theme, toggleTheme, isDark } = useTheme();
  const [displayName, setDisplayName] = useState('');
  const [notifPrefs, setNotifPrefs] = useState<NotificationPrefs>({
    email_alerts: true,
    whatsapp_alerts: false,
    push_alerts: false,
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
        // Merge over the defaults so a server response that predates a channel
        // (e.g. whatsapp/push) leaves that Switch controlled, not undefined.
        setNotifPrefs((prev) => ({ ...prev, ...prefs.notification_prefs }));
      })
      .catch(() => {
        if (cancelled) return;
        setDisplayName(localStorage.getItem('pos-display-name') || '');
        const cached = localStorage.getItem('pos-notification-prefs');
        if (cached) {
          try {
            setNotifPrefs((prev) => ({ ...prev, ...JSON.parse(cached) }));
          } catch {
            // use defaults
          }
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load all active sessions for the management list (#202, parity #2). Kept in
  // a callable so a revoke can refresh it.
  async function loadSessions() {
    try {
      const data = await getActiveSessions();
      setSessions(data.sessions);
    } catch {
      setSessions([]);
    } finally {
      setSessionLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    getActiveSessions()
      .then((data) => {
        if (!cancelled) setSessions(data.sessions);
      })
      .catch(() => {
        if (!cancelled) setSessions([]);
      })
      .finally(() => {
        if (!cancelled) setSessionLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Whether MFA is already on drives the security panel (#202, parity #1).
    getMfaStatus()
      .then((status) => {
        if (!cancelled) setMfaStatus(status);
      })
      .catch(() => {
        if (!cancelled) setMfaStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleRevokeSession(id: string) {
    setRevokingId(id);
    try {
      await revokeSession(id);
      await loadSessions();
    } finally {
      setRevokingId(null);
    }
  }

  async function handleEnrollMfa() {
    setMfaError(null);
    setMfaBusy(true);
    try {
      const result = await enrollMfa();
      setMfaEnroll(result);
      setMfaCode('');
    } catch (err) {
      setMfaError(err instanceof Error ? err.message : t('change_password_failed'));
    } finally {
      setMfaBusy(false);
    }
  }

  async function handleActivateMfa() {
    setMfaError(null);
    setMfaBusy(true);
    try {
      const result = await activateMfa(mfaCode);
      setMfaRecoveryCodes(result.recovery_codes);
      setMfaStatus({ enabled: true, recovery_codes_remaining: result.recovery_codes.length });
      setMfaEnroll(null);
      setMfaCode('');
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMfaError(detail || tt('mfa_invalid_code', 'Invalid verification code. Try again.'));
    } finally {
      setMfaBusy(false);
    }
  }

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
        <div className="dxr-tile space-y-5">
          <h2 className="text-foreground flex items-center gap-2 font-semibold">
            <Bell className="h-5 w-5 text-warning" />
            {t('notifications')}
          </h2>

          {/* Channels — how we reach you */}
          <div className="space-y-1">
            <p className="dxr-eyebrow">{tt('delivery_channels', 'Delivery channels')}</p>
            {[
              { key: 'email_alerts' as const, label: tt('email_alerts', 'Email'), desc: tt('email_alerts_desc', 'Receive important updates by email') },
              { key: 'whatsapp_alerts' as const, label: tt('whatsapp_alerts', 'WhatsApp'), desc: tt('whatsapp_alerts_desc', 'Receive updates on WhatsApp') },
              { key: 'push_alerts' as const, label: tt('push_alerts', 'Push'), desc: tt('push_alerts_desc', 'Receive push notifications on this device') },
            ].map((item) => (
              <div key={item.key} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                <div>
                  <p className="text-foreground text-sm font-medium">{item.label}</p>
                  <p className="text-muted-foreground text-xs">{item.desc}</p>
                </div>
                <Switch
                  checked={notifPrefs[item.key]}
                  onCheckedChange={() => toggleNotifPref(item.key)}
                  aria-label={item.label}
                />
              </div>
            ))}
          </div>

          {/* Categories — what we tell you about */}
          <div className="space-y-1">
            <p className="dxr-eyebrow">{tt('alert_categories', 'Alert categories')}</p>
            {[
              { key: 'low_stock_alerts' as const, label: tt('low_stock_alerts', 'Low Stock Alerts'), desc: tt('low_stock_alerts_desc', 'Get notified when products are running low') },
              { key: 'daily_summary' as const, label: tt('daily_summary', 'Daily Summary'), desc: tt('daily_summary_desc', 'Receive a daily sales summary') },
              { key: 'transaction_alerts' as const, label: tt('transaction_alerts', 'Transaction Alerts'), desc: tt('transaction_alerts_desc', 'Get notified for each transaction') },
            ].map((item) => (
              <div key={item.key} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                <div>
                  <p className="text-foreground text-sm font-medium">{item.label}</p>
                  <p className="text-muted-foreground text-xs">{item.desc}</p>
                </div>
                <Switch
                  checked={notifPrefs[item.key]}
                  onCheckedChange={() => toggleNotifPref(item.key)}
                  aria-label={item.label}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Session Info */}
        <div className="dxr-tile space-y-3">
          <h2 className="text-foreground flex items-center gap-2 font-semibold">
            <Shield className="h-5 w-5 text-danger" />
            {tt('security_and_sessions', 'Security & Sessions')}
          </h2>
          {/* Two-factor authentication (#202, parity #1) */}
          <div className="space-y-3 py-2">
            <p className="dxr-eyebrow flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              {tt('two_factor_auth', 'Two-factor authentication')}
            </p>

            {mfaRecoveryCodes ? (
              <div className="space-y-2">
                <p className="text-sm text-success">
                  {tt('mfa_enabled_now', 'Two-factor authentication is now on.')}
                </p>
                <p className="text-muted-foreground text-xs">
                  {tt(
                    'mfa_save_recovery',
                    'Save these recovery codes somewhere safe — each can be used once if you lose your authenticator.'
                  )}
                </p>
                <ul className="grid grid-cols-2 gap-2 font-mono text-sm">
                  {mfaRecoveryCodes.map((code) => (
                    <li key={code} className="dxr-tile px-3 py-1.5 text-center">
                      {code}
                    </li>
                  ))}
                </ul>
                <Button size="sm" variant="outline" onClick={() => setMfaRecoveryCodes(null)}>
                  {tt('done', 'Done')}
                </Button>
              </div>
            ) : mfaEnroll ? (
              <div className="space-y-3">
                <p className="text-muted-foreground text-xs">
                  {tt(
                    'mfa_enroll_hint',
                    'Add this secret to your authenticator app, then enter the 6-digit code it shows.'
                  )}
                </p>
                <code
                  data-testid="mfa-secret"
                  className="dxr-tile inline-block px-3 py-1.5 font-mono text-sm break-all"
                >
                  {mfaEnroll.secret}
                </code>
                <InputOTP
                  maxLength={6}
                  value={mfaCode}
                  onChange={setMfaCode}
                  aria-label={tt('mfa_code_label', 'Verification code')}
                >
                  <InputOTPGroup>
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                      <InputOTPSlot key={i} index={i} />
                    ))}
                  </InputOTPGroup>
                </InputOTP>
                {mfaError && <p className="text-sm text-danger">{mfaError}</p>}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={handleActivateMfa}
                    disabled={mfaBusy || mfaCode.length < 6}
                  >
                    {mfaBusy ? t('saving') : tt('mfa_activate', 'Activate')}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setMfaEnroll(null);
                      setMfaError(null);
                      setMfaCode('');
                    }}
                  >
                    {tt('cancel', 'Cancel')}
                  </Button>
                </div>
              </div>
            ) : mfaStatus?.enabled ? (
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-foreground text-sm font-medium">
                    {tt('mfa_on', 'Two-factor authentication is on')}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {tt('mfa_recovery_remaining', 'Recovery codes remaining')}:{' '}
                    {mfaStatus.recovery_codes_remaining}
                  </p>
                </div>
                <Badge className="pill-success shrink-0">{tt('active', 'Active')}</Badge>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3">
                <p className="text-muted-foreground text-xs">
                  {tt('mfa_off_hint', 'Add a second factor for stronger account security.')}
                </p>
                <Button size="sm" className="shrink-0" onClick={handleEnrollMfa} disabled={mfaBusy}>
                  {tt('enable_mfa', 'Enable two-factor authentication')}
                </Button>
              </div>
            )}
            {mfaError && !mfaEnroll && <p className="text-sm text-danger">{mfaError}</p>}
          </div>

          {/* Active sessions (#202, parity #2) */}
          <div className="space-y-2 py-2 border-t border-border">
            <p className="dxr-eyebrow flex items-center gap-2">
              <Monitor className="h-4 w-4" />
              {tt('active_sessions', 'Active sessions')}
            </p>
            {sessionLoading ? (
              <p className="text-muted-foreground text-xs animate-pulse">{t('loading')}</p>
            ) : sessions.length === 0 ? (
              <p className="text-muted-foreground text-xs">
                {tt('session_unavailable', 'Session details unavailable')}
              </p>
            ) : (
              <ul className="space-y-1">
                {sessions.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between gap-3 py-1.5 border-b border-border last:border-0"
                  >
                    <div className="min-w-0">
                      <p className="text-foreground text-sm font-medium truncate">
                        {deviceLabel(s.user_agent) || tt('unknown_device', 'Unknown device')}
                      </p>
                      <p className="text-muted-foreground text-xs truncate">
                        {s.created_at
                          ? `${tt('signed_in', 'Signed in')} ${formatDate(s.created_at, language)}`
                          : tt('active_now', 'Active now')}
                      </p>
                    </div>
                    {s.current ? (
                      <Badge className="pill-success shrink-0">{tt('active', 'Active')}</Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0"
                        onClick={() => handleRevokeSession(s.id)}
                        disabled={revokingId === s.id}
                      >
                        {revokingId === s.id ? t('loading') : tt('revoke', 'Revoke')}
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
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