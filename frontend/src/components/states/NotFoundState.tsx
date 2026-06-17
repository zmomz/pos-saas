import type { ComponentType, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n';
import { cn } from '@/lib/utils';

interface NotFoundStateProps {
  /** Large status code above the title; pass `""` to hide (e.g. a named 404). */
  code?: string;
  /** Lucide icon in the badge; defaults to a warning triangle. */
  icon?: ComponentType<{ className?: string }>;
  /** Headline — falls back to the generic "Page Not Found". */
  title?: string;
  /** Supporting line under the headline. */
  description?: string;
  /** Optional CTA; defaults to a "Back Home" link to `/`. */
  action?: ReactNode;
  className?: string;
}

/**
 * Shared "not found" takeover (Phase 5) — one source of truth for the route-level
 * 404 (`NotFound`) and the in-page "distributor not found" branch on the public
 * agent landing page, which previously shipped three divergent designs. Token-based
 * so it themes with the app and flips direction with the language.
 */
export default function NotFoundState({
  code = '404',
  icon: Icon = AlertTriangle,
  title,
  description,
  action,
  className,
}: NotFoundStateProps) {
  const { t, isRTL } = useLanguage();
  const tt = (key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  };

  return (
    <div
      dir={isRTL ? 'rtl' : 'ltr'}
      className={cn('min-h-screen flex items-center justify-center bg-background p-6', className)}
    >
      <div className="text-center px-4">
        <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-border bg-card shadow-sm">
          <Icon className="h-10 w-10 text-warning" />
        </div>
        {code ? (
          <h1 className="mb-2 text-6xl font-bold tabular-nums text-foreground">{code}</h1>
        ) : null}
        <p className="mb-3 text-xl font-semibold text-foreground">
          {title || tt('page_not_found', 'Page Not Found')}
        </p>
        <p className="mx-auto mb-8 max-w-md text-muted-foreground">
          {description || tt('page_not_found_desc', 'The page you are looking for does not exist or has been moved.')}
        </p>
        {action ?? (
          <Button asChild>
            <Link to="/">
              <Home className="h-5 w-5" />
              {tt('back_home', 'Back Home')}
            </Link>
          </Button>
        )}
      </div>
    </div>
  );
}
