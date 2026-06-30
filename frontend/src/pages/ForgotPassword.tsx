import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AuthLayout from '@/components/auth/AuthLayout';
import { requestPasswordReset } from '@/lib/api';
import { useLanguage } from '@/lib/i18n';

/**
 * Self-service "forgot password" request screen (#199, parity #3).
 *
 * Screen 1 of the 2-screen reset flow on `/auth/password/*`. Posts the email to
 * the anti-enumeration `/auth/password/forgot` endpoint, which always responds
 * 200. We therefore show the SAME neutral confirmation whether or not the
 * address maps to an account — the copy must never reveal that an email exists.
 *
 * In dev / no-SMTP mode the backend echoes the reset token in the response so
 * the flow is usable without a real mailbox; when present we surface a shortcut
 * into screen 2 instead of pretending a mail was delivered.
 */
export default function ForgotPassword() {
  const { t } = useLanguage();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await requestPasswordReset(email);
      setDevToken(result.reset_token ?? null);
      setSent(true);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || (err instanceof Error ? err.message : t('auth_failed')));
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <AuthLayout title={t('forgot_sent_title')}>
        <div className="space-y-5">
          <p className="text-sm text-foreground/90">{t('forgot_sent_body')}</p>

          {devToken && (
            <div className="rounded-lg border border-dashed border-border bg-muted/40 p-3 text-sm">
              <p className="mb-2 text-muted-foreground">{t('forgot_dev_token_note')}</p>
              <Link
                to={`/auth/password/reset?token=${encodeURIComponent(devToken)}`}
                className="font-medium text-primary underline underline-offset-4"
              >
                {t('continue_to_reset')}
              </Link>
            </div>
          )}

          <Button asChild variant="outline" className="w-full">
            <Link to="/login">{t('back_to_login')}</Link>
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title={t('forgot_password_title')} description={t('forgot_password_desc')}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor="email" className="text-foreground/90">
            {t('email')}
          </Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? t('loading') : t('send_reset_link')}
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
