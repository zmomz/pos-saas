import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage, languageOptions } from '@/lib/i18n';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

const roleToPath: Record<string, string> = {
  master: '/master',
  agent: '/agent',
  client: '/client',
};

export default function Index() {
  const navigate = useNavigate();
  const { t, language, setLanguage, isRTL } = useLanguage();
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
        className="min-h-screen bg-slate-900 flex items-center justify-center"
      >
        <div className="text-white text-lg animate-pulse">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div dir={isRTL ? 'rtl' : 'ltr'} className="min-h-screen bg-slate-900 flex flex-col">
      <header className="flex items-center justify-between p-4 border-b border-slate-700">
        <h1 className="text-xl font-bold text-white">{t('app_name')}</h1>
        <Select value={language} onValueChange={(v) => setLanguage(v as never)}>
          <SelectTrigger className="w-32 bg-slate-800 border-slate-600 text-white">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="bg-slate-800 border-slate-600">
            {languageOptions.map((opt) => (
              <SelectItem key={opt.value} value={opt.value} className="text-white hover:bg-slate-700">
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </header>

      <main className="flex-1 flex items-center justify-center p-6">
        <Card className="w-full max-w-md bg-slate-800 border-slate-700">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl text-white">{t('welcome')}</CardTitle>
            <CardDescription className="text-slate-400">{t('welcome_desc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              {mode === 'register' && (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="name" className="text-slate-300">{t('name')}</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="bg-slate-900 border-slate-600 text-white"
                  />
                </div>
              )}
              <div className="flex flex-col gap-2">
                <Label htmlFor="email" className="text-slate-300">{t('email')}</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="bg-slate-900 border-slate-600 text-white"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="password" className="text-slate-300">{t('password')}</Label>
                <Input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="bg-slate-900 border-slate-600 text-white"
                />
              </div>

              {error && <p className="text-sm text-red-400">{error}</p>}

              <Button
                type="submit"
                disabled={submitting}
                className="w-full bg-brand-600 hover:bg-brand-700 text-white"
              >
                {submitting ? t('loading') : mode === 'login' ? t('login') : t('create_account')}
              </Button>

              <button
                type="button"
                onClick={() => {
                  setMode(mode === 'login' ? 'register' : 'login');
                  setError(null);
                }}
                className="text-sm text-slate-400 hover:text-slate-200 underline"
              >
                {mode === 'login'
                  ? t('dont_have_account')
                  : t('already_have_account')}
              </button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
