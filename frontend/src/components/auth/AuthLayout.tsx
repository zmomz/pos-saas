import type { ReactNode } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useLanguage, languageOptions, type Language } from '@/lib/i18n';

interface AuthLayoutProps {
  /** Card headline (already translated). */
  title: string;
  /** Optional supporting line under the headline. */
  description?: string;
  children: ReactNode;
  /** Optional content rendered under the card (e.g. a mode toggle). */
  footer?: ReactNode;
  /**
   * Show the header language switcher. Off for first-login reset, which carries
   * its own guided language step (CL-02).
   */
  showLanguageSwitcher?: boolean;
}

/**
 * Shared branded shell for the auth gate (Phase 5). Gives the login and
 * first-login reset screens one petrol/gold identity — gradient logo lockup,
 * soft brand wash and a consistent card — instead of two bare shadcn cards that
 * didn't match each other. Token-based, so it themes with the app and flips
 * direction with the language.
 */
export default function AuthLayout({
  title,
  description,
  children,
  footer,
  showLanguageSwitcher = true,
}: AuthLayoutProps) {
  const { t, language, setLanguage, isRTL } = useLanguage();
  const initial = (t('app_name') || 'P').charAt(0).toUpperCase();

  return (
    <div dir={isRTL ? 'rtl' : 'ltr'} className="relative flex min-h-screen flex-col bg-background">
      {/* Soft petrol wash so the gate doesn't read as a flat white box. */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(680px 420px at 80% -6%, hsl(var(--primary) / 0.12), transparent 62%)',
        }}
      />

      <header className="relative flex items-center justify-between p-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-[11px] bg-gradient-to-br from-brand to-brand-700 text-base font-extrabold text-white shadow-brand">
            {initial}
          </span>
          <span className="text-lg font-bold text-foreground">{t('app_name')}</span>
        </div>
        {showLanguageSwitcher && (
          <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {languageOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </header>

      <main className="relative flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="rounded-[20px] border border-border bg-card p-8 shadow-card">
            <div className="mb-6 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-[16px] bg-gradient-to-br from-brand to-brand-700 text-2xl font-extrabold text-white shadow-brand">
                {initial}
              </div>
              <h1 className="text-2xl font-bold text-foreground">{title}</h1>
              {description ? (
                <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>
              ) : null}
            </div>
            {children}
          </div>
          {footer ? <div className="mt-4 text-center">{footer}</div> : null}
        </div>
      </main>
    </div>
  );
}
