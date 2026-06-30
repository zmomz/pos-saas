import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp';
import AuthLayout from '@/components/auth/AuthLayout';
import { useAuth } from '@/contexts/AuthContext';
import { isMfaChallenge } from '@/lib/auth';
import { useLanguage } from '@/lib/i18n';

const roleToPath: Record<string, string> = {
  master: '/master',
  agent: '/agent',
  client: '/client',
};

export default function Index() {
  const navigate = useNavigate();
  const { t, tt, isRTL } = useLanguage();
  const { user, loading, login, completeMfaLogin, loginWithPin, register } = useAuth();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  // Within login mode the merchant's team can sign in by password or by PIN
  // (#216, on-terminal staff login). Register only ever uses a password.
  const [method, setMethod] = useState<'password' | 'pin'>('password');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [pin, setPin] = useState('');
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // #202 — when a password login returns an MFA challenge, hold the ticket and
  // switch the form to second-factor entry until it is verified.
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState('');

  // Once authenticated, route to the role-specific dashboard.
  useEffect(() => {
    if (user) {
      navigate(roleToPath[user.role] || '/client', { replace: true });
    }
  }, [user, navigate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === 'login') {
        if (method === 'pin') {
          await loginWithPin(email, pin);
        } else {
          const result = await login(email, password);
          // An MFA-enabled account is not signed in yet — switch to the
          // second-factor step and keep the ticket to complete it.
          if (isMfaChallenge(result)) {
            setMfaToken(result.mfaToken);
            setMfaCode('');
            return;
          }
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

  async function handleVerifyMfa(e: React.FormEvent) {
    e.preventDefault();
    if (!mfaToken) return;
    setSubmitting(true);
    setError(null);
    try {
      await completeMfaLogin(mfaToken, mfaCode);
      // Navigation happens in the effect above once `user` is set.
    } catch (err) {
      setError(err instanceof Error ? err.message : t('auth_failed'));
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
      {mfaToken ? (
        <form onSubmit={handleVerifyMfa} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="mfa-code" className="text-foreground/90">
              {tt('mfa_code_label', 'Verification code')}
            </Label>
            <p className="text-sm text-muted-foreground">
              {tt(
                'mfa_code_hint',
                'Enter the 6-digit code from your authenticator app, or a recovery code.'
              )}
            </p>
            <InputOTP
              id="mfa-code"
              maxLength={6}
              value={mfaCode}
              onChange={setMfaCode}
              aria-label={tt('mfa_code_label', 'Verification code')}
              autoFocus
            >
              <InputOTPGroup>
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <InputOTPSlot key={i} index={i} />
                ))}
              </InputOTPGroup>
            </InputOTP>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? t('loading') : tt('mfa_verify', 'Verify')}
          </Button>
          <button
            type="button"
            onClick={() => {
              setMfaToken(null);
              setMfaCode('');
              setError(null);
            }}
            className="text-sm text-muted-foreground hover:text-foreground underline"
          >
            {tt('mfa_back_to_login', 'Back to login')}
          </button>
        </form>
      ) : (
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {mode === 'login' && (
          <div className="dxr-seg grid grid-cols-2" role="tablist" aria-label={t('login')}>
            <button
              type="button"
              role="tab"
              aria-selected={method === 'password'}
              data-active={method === 'password'}
              onClick={() => {
                setMethod('password');
                setError(null);
              }}
            >
              {t('password')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={method === 'pin'}
              data-active={method === 'pin'}
              onClick={() => {
                setMethod('pin');
                setError(null);
              }}
            >
              {t('pin_login')}
            </button>
          </div>
        )}

        {mode === 'register' && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="name" className="text-foreground/90">{t('name')}</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor="email" className="text-foreground/90">
            {mode === 'login' && method === 'pin' ? t('pin_merchant_email') : t('email')}
          </Label>
          <Input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        {mode === 'login' && method === 'pin' ? (
          <div className="flex flex-col gap-2">
            <Label htmlFor="pin" className="text-foreground/90">{t('pin')}</Label>
            <Input
              id="pin"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              required
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              placeholder="••••"
            />
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Label htmlFor="password" className="text-foreground/90">{t('password')}</Label>
            <Input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {mode === 'login' && (
              <Link
                to="/auth/password/forgot"
                className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground self-end"
              >
                {t('forgot_password_link')}
              </Link>
            )}
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? t('loading') : mode === 'login' ? t('login') : t('create_account')}
        </Button>
      </form>
      )}
    </AuthLayout>
  );
}
