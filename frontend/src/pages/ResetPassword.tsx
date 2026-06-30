import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AuthLayout from '@/components/auth/AuthLayout';
import { resetPassword } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';

/**
 * Self-service "reset password" screen (#199, parity #3).
 *
 * Screen 2 of the 2-screen flow on `/auth/password/*`. The single-use token
 * normally arrives in the URL from the emailed link (`?token=…`); when it is
 * absent (e.g. the user landed here directly) we expose a field to paste the
 * code so the screen is still usable. Posts to `/auth/password/reset`, which
 * enforces password complexity server-side — we surface its message verbatim.
 */
export default function ResetPassword() {
  const { t } = useLanguage();
  const [searchParams] = useSearchParams();
  const tokenFromUrl = searchParams.get('token') ?? '';

  const [token, setToken] = useState(tokenFromUrl);
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!token.trim()) {
      setError(t('reset_token_missing'));
      return;
    }
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
      await resetPassword(token.trim(), newPassword);
      setDone(true);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || (err instanceof Error ? err.message : t('reset_password_failed')));
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <AuthLayout title={t('reset_password_success_title')}>
        <div className="space-y-5">
          <p className="text-sm text-foreground/90">{t('reset_password_success_body')}</p>
          <Button asChild className="w-full">
            <Link to="/login">{t('back_to_login')}</Link>
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t('reset_password_title')} description={t('reset_password_desc')}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* The token usually rides the URL; only prompt for it when it didn't. */}
        {!tokenFromUrl && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="reset-code" className="text-foreground/90">
              {t('reset_code_label')}
            </Label>
            <Input
              id="reset-code"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">{t('reset_code_hint')}</p>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <Label htmlFor="new-password" className="text-foreground/90">
            {t('new_password')}
          </Label>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            required
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor="confirm-password" className="text-foreground/90">
            {t('confirm_password')}
          </Label>
          <Input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? t('loading') : t('reset_password_submit')}
        </Button>

        <Link
          to="/login"
          className="text-center text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
        >
          {t('back_to_login')}
        </Link>
      </form>
    </AuthLayout>
  );
}
