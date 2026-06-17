import { Loader2 } from 'lucide-react';
import { useLanguage } from '@/lib/i18n';
import { cn } from '@/lib/utils';

interface LoadingStateProps {
  /** Override the default "Loading…" label. */
  message?: string;
  className?: string;
}

/**
 * Shared loading state — pairs with `ErrorState`/`EmptyState`/`PermissionDenied`
 * so the four in-page states look like one system. Replaces the three ad-hoc
 * loading treatments (bespoke `animate-pulse` text, a bare spinner ring,
 * nothing) flagged in the design audit.
 */
export default function LoadingState({ message, className }: LoadingStateProps) {
  const { t } = useLanguage();
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('flex flex-col items-center justify-center gap-3 py-16 text-center', className)}
    >
      <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
      <p className="text-sm text-muted-foreground">{message || t('loading')}</p>
    </div>
  );
}
