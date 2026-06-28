import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AuthLayout from '@/components/auth/AuthLayout';
import OtpField from '@/components/auth/OtpField';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/lib/i18n';

const roleToPath: Record<string, string> = {
  master: '/master',
  agent: '/agent',
  client: '/client',
};

export default function Index() {
  const navigate = useNavigate();
  const { t, tt, isRTL } = useLanguage();
  const { user, loading, login, completeMfaLogin, register } = useAuth();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  // Second-factor gate: once /auth/login returns a challenge we hold its ticket
  // and swap the credentials form for a code prompt (ISSUE-202).
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const [code, setCode] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Once authenticated, route to the role-specific dashboard.
  useEffect(() => {
    if (user) {
      navigate(roleToPath[user.role] || '/client', { replace: true });
    }
  }, [user, navigate]);

  function resetMfa() {
    setMfaToken(null);
    setUseRecoveryCode(false);
    setCode('');
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === 'login') {
        const outcome = await login(email, password);
        if (outcome?.mfaRequired && outcome.mfaToken) {
          // Hold the ticket and challenge for a code; navigation waits for it.
          setMfaToken(outcome.mfaToken);
          return;
        }
      } else {
        await register(email, password, name || undefined);
      }
      // Navigation happens in the effect above once `user` is set.
    } catch (err) {
      setError(err instanceof Error ? err.message : t('auth_failed'));
    } finally {
      setSubmitting(false);
    }
  }

  async function verifyMfa(submittedCode: string) {
    if (!mfaToken || submitting) return;
    const trimmed = submittedCode.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setError(null);
    try {
      await completeMfaLogin(mfaToken, trimmed);
      // Navigation happens in the effect above once `user` is set.
    } catch (err) {
      setError(err instanceof Error ? err.message : t('auth_failed'));
      setCode('');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div
        dir={isRTL ? 'rtl' : 'ltr'}
        className="min-h-screen bg-background flex items-center justify-center"
      >
        <div className="text-foreground text-lg animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  // ----- Second-factor challenge -----
  if (mfaToken) {
    return (
      <AuthLayout
        title={tt('mfa_challenge_title', 'Two-step verification')}
        description={
          useRecoveryCode
            ? tt('mfa_recovery_hint', 'Enter one of your saved recovery codes.')
            : tt('mfa_challenge_hint', 'Enter the 6-digit code from your authenticator app.')
        }
        footer={
          <button
            type="button"
            onClick={resetMfa}
            className="text-sm text-muted-foreground hover:text-foreground underline"
          >
            {tt('mfa_back_to_signin', 'Back to sign in')}
          </button>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void verifyMfa(code);
          }}
          className="flex flex-col gap-4"
        >
          {useRecoveryCode ? (
            <div className="flex flex-col gap-2">
              <Label htmlFor="recovery-code" className="text-foreground/90">
                {tt('mfa_recovery_code', 'Recovery code')}
              </Label>
              <Input
                id="recovery-code"
                autoFocus
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="text-center tracking-widest"
              />
            </div>
          ) : (
            <OtpField
              value={code}
              onChange={setCode}
              onComplete={(v) => void verifyMfa(v)}
              disabled={submitting}
              autoFocus
              aria-label={tt('mfa_challenge_title', 'Two-step verification')}
            />
          )}

          {error && <p className="text-sm text-destructive text-center">{error}</p>}

          <Button
            type="submit"
            disabled={submitting || !code.trim()}
            className="w-full"
          >
            {submitting ? t('loading') : tt('mfa_verify', 'Verify')}
          </Button>

          <button
            type="button"
            onClick={() => {
              setUseRecoveryCode((v) => !v);
              setCode('');
              setError(null);
            }}
            className="text-sm text-muted-foreground hover:text-foreground underline"
          >
            {useRecoveryCode
              ? tt('mfa_use_authenticator', 'Use your authenticator app')
              : tt('mfa_use_recovery_code', 'Use a recovery code instead')}
          </button>
        </form>
      </AuthLayout>
    );
  }

  // ----- Credentials -----
  return (
    <AuthLayout
      title={t('welcome')}
      description={t('welcome_desc')}
      footer={
        <button
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login');
            setError(null);
          }}
          className="text-sm text-muted-foreground hover:text-foreground underline"
        >
          {mode === 'login' ? t('dont_have_account') : t('already_have_account')}
        </button>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {mode === 'register' && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="name" className="text-foreground/90">{t('name')}</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor="email" className="text-foreground/90">{t('email')}</Label>
          <Input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password" className="text-foreground/90">{t('password')}</Label>
          <Input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? t('loading') : mode === 'login' ? t('login') : t('create_account')}
        </Button>
      </form>
    </AuthLayout>
  );
}
