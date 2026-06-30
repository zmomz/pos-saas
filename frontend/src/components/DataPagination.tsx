import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n';

interface DataPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

/**
 * Lightweight pagination control for list pages.
 *
 * The backend already accepts skip/limit on every entity list; this keeps the
 * rendered DOM bounded instead of dumping hundreds of rows at once (gap analysis:
 * "frontend mostly requests large limit and renders all"). Use with a sliced
 * array for client-side paging, or wire onPageChange to a server fetch.
 */
export function DataPagination({ page, pageSize, total, onPageChange }: DataPaginationProps) {
  const { t } = useLanguage();
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;

  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between pt-4 text-sm text-muted-foreground">
      <span>
        {start}–{end} {t('of')} {total}
      </span>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="border-input text-foreground/90 hover:bg-muted"
        >
          {t('previous')}
        </Button>
        <span className="px-2">
          {page} / {pageCount}
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
          className="border-input text-foreground/90 hover:bg-muted"
        >
          {t('next')}
        </Button>
      </div>
    </div>
  );
}
