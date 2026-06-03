import { Lock } from 'lucide-react';
import { useLanguage } from '@/lib/i18n';

interface PermissionDeniedProps {
  message?: string;
  description?: string;
}

/**
 * Shared in-page permission-denied state (UX-02 / F-051). Pages that catch a 403
 * from a list endpoint render this instead of an empty or error view, so a user
 * who lacks access sees a clear "you don't have permission" rather than a blank
 * page or a misleading "no data".
 */
export default function PermissionDenied({ message, description }: PermissionDeniedProps) {
  const { t } = useLanguage();
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Lock className="h-12 w-12 text-muted-foreground" />
      <p className="text-base font-medium">{message || t('permission_denied')}</p>
      <p className="max-w-sm text-sm text-muted-foreground">
        {description || t('permission_denied_desc')}
      </p>
    </div>
  );
}
