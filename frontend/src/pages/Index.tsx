import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import AuthLayout from '@/components/auth/AuthLayout';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/lib/i18n';

const roleToPath: Record<string, string> = {
  master: '/master',
  agent: '/agent',
  client: '/client',
};

export default function Index() {
  const navigate = useNavigate();
  const { t, isRTL } = useLanguage();
  const { user, loading, login, register } = useAuth();

  const [mode, setMode] = useState<'login' | 'register'>('login');
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === 'login') {
        await login(email, password);
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
          {mode === 'login' && (
            <Link
              to="/auth/password/forgot"
              className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground self-end"
            >
              {t('forgot_password_link')}
            </Link>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" disabled={submitting} className="w-full">
          {submitting ? t('loading') : mode === 'login' ? t('login') : t('create_account')}
        </Button>
      </form>
    </AuthLayout>
  );
}
