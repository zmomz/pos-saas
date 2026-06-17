import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n';

interface ErrorStateProps {
  message?: string;
  description?: string;
  onRetry?: () => void;
}

/**
 * Shared error state (UX-02 / F-051) — visually distinct from the empty state so
 * a failed fetch never masquerades as "no data". Pages that previously swallowed
 * a thrown request into an empty list (Reports, Notifications, …) render this,
 * with an optional retry that re-runs the failed load.
 */
export default function ErrorState({ message, description, onRetry }: ErrorStateProps) {
  const { t } = useLanguage();
  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <AlertTriangle className="h-12 w-12 text-danger/70" />
      <p className="text-base font-medium text-danger">{message || t('load_error')}</p>
      <p className="max-w-sm text-sm text-muted-foreground">
        {description || t('load_error_desc')}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t('retry')}
        </Button>
      )}
    </div>
  );
}
