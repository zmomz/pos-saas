import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import AuthLayout from '@/components/auth/AuthLayout';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useAuth } from '@/contexts/AuthContext';
import {
  changePassword,
  getClientProfile,
  setBusinessType as apiSetBusinessType,
  type BusinessType,
} from '@/lib/api';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';

/**
 * First-login force-password-change screen (C-1 / CL-01).
 *
 * Shown to any account flagged `must_change_password` (freshly provisioned
 * agents/clients). Reuses the authenticated change-password endpoint with the
 * temp password as the current password; on success the backend clears the
 * flag, and we refetch the session so routing proceeds to the dashboard.
 */
export default function ForceResetPassword() {
  const { user, refetch, logout } = useAuth();
  const { t, language, setLanguage } = useLanguage();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // CL-02: the client picks their business type during first-login setup. Only
  // a client tenancy has one; pre-select the agent-provisioned default.
  const isClient = user?.role === 'client';
  const [businessType, setBusinessType] = useState<BusinessType>('retail');

  useEffect(() => {
    if (!isClient) return;
    let cancelled = false;
    getClientProfile()
      .then((profile) => {
        if (!cancelled && profile?.business_type) {
          setBusinessType(profile.business_type);
        }
      })
      .catch(() => {
        // No profile / not a client → keep the retail default; non-fatal.
      });
    return () => {
      cancelled = true;
    };
  }, [isClient]);

  async function handleSubmit() {
    setError(null);
    if (newPassword.length < 8) {
      setError(t('password_too_short'));
      return;
    }
    if (newPassword !== confirm) {
      setError(t('passwords_do_not_match'));
      return;
    }
    setSubmitting(true);
    try {
      // Persist the chosen business type BEFORE changing the password so a
      // failure here is cleanly retryable (the temp password is still valid).
      if (isClient) {
        await apiSetBusinessType(businessType);
      }
      await changePassword(currentPassword, newPassword);
      await refetch();
      navigate('/', { replace: true });
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || (err instanceof Error ? err.message : t('change_password_failed')));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout title={t('set_new_password')} showLanguageSwitcher={false}>
      <div className="space-y-4">
        <p className="text-sm text-foreground/90">
          {user?.name ? `${user.name} — ` : ''}
          {t('first_login_reset_prompt')}
        </p>

        {/* CL-02: guided first-login language step. Applies instantly via the
            shared LanguageProvider and persists the choice. */}
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t('choose_language')}</label>
          <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {languageOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* CL-02: guided first-login business-type step. Drives retail vs
            restaurant POS mode and gates the restaurant vertical (RST-*).
            Only a client tenancy has a business type. */}
        {isClient && (
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">{t('choose_business_type')}</label>
            <Select
              value={businessType}
              onValueChange={(v) => setBusinessType(v as BusinessType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="retail">{t('business_type_retail')}</SelectItem>
                <SelectItem value="restaurant">{t('business_type_restaurant')}</SelectItem>
                <SelectItem value="both">{t('business_type_both')}</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{t('business_type_hint')}</p>
          </div>
        )}

        <Input
          type="password"
          placeholder={t('current_temp_password')}
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
        />
        <Input
          type="password"
          placeholder={t('new_password')}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <Input
          type="password"
          placeholder={t('confirm_password')}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-between gap-2">
          <Button variant="outline" onClick={() => logout()}>
            {t('logout')}
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? t('saving') : t('save')}
          </Button>
        </div>
      </div>
    </AuthLayout>
  );
}
