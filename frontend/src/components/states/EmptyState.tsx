import type { ComponentType, ReactNode } from 'react';
import { Inbox } from 'lucide-react';
import { useLanguage } from '@/lib/i18n';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  /** Lucide icon component; defaults to an inbox. */
  icon?: ComponentType<{ className?: string }>;
  /** Headline — falls back to a generic "Nothing here yet". */
  message?: string;
  /** Supporting line under the headline. */
  description?: string;
  /** Optional call-to-action (e.g. a "New …" button). */
  action?: ReactNode;
  className?: string;
}

/**
 * Shared empty state (UX-02) — visually distinct from `ErrorState` so "no data"
 * never reads as "load failed". Replaces the split where some pages rendered an
 * empty `<Card>` and others an in-table `<tr>`.
 */
export default function EmptyState({
  icon: Icon = Inbox,
  message,
  description,
  action,
  className,
}: EmptyStateProps) {
  const { t } = useLanguage();
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 py-16 text-center', className)}>
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
        <Icon className="h-6 w-6" />
      </span>
      <p className="text-base font-medium">{message || t('no_data')}</p>
      <p className="max-w-sm text-sm text-muted-foreground">{description || t('no_data_desc')}</p>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
