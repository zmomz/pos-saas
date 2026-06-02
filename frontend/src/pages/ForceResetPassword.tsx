import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useAuth } from '@/contexts/AuthContext';
import { changePassword } from '@/lib/api';
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

  async function handleSubmit() {
    setError(null);
    if (newPassword.length < 8) {
      setError(t('password_too_short') || 'Password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirm) {
      setError(t('passwords_do_not_match') || 'Passwords do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(currentPassword, newPassword);
      await refetch();
      navigate('/', { replace: true });
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || (err instanceof Error ? err.message : 'Failed to change password.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 p-4">
      <Card className="w-full max-w-md bg-slate-800 border-slate-700">
        <CardHeader>
          <CardTitle className="text-white">
            {t('set_new_password') || 'Set a new password'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-slate-300">
            {t('first_login_reset_prompt') ||
              `Welcome${user?.name ? `, ${user.name}` : ''}. For security you must replace your temporary password before continuing.`}
          </p>

          {/* CL-02: guided first-login language step. Applies instantly via the
              shared LanguageProvider and persists the choice. */}
          <div className="space-y-1">
            <label className="text-xs text-slate-400">{t('choose_language')}</label>
            <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
              <SelectTrigger className="bg-slate-700 border-slate-600 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {languageOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Input
            type="password"
            placeholder={t('current_temp_password') || 'Current (temporary) password'}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="bg-slate-700 border-slate-600 text-white"
          />
          <Input
            type="password"
            placeholder={t('new_password') || 'New password'}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="bg-slate-700 border-slate-600 text-white"
          />
          <Input
            type="password"
            placeholder={t('confirm_password') || 'Confirm new password'}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="bg-slate-700 border-slate-600 text-white"
          />
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="flex gap-2 justify-between">
            <Button
              variant="outline"
              onClick={() => logout()}
              className="border-slate-600 text-slate-300"
            >
              {t('logout') || 'Logout'}
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={submitting}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              {submitting ? (t('saving') || 'Saving...') : (t('save') || 'Save')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
