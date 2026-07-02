import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Shared list/table primitive — the reference `.tbl` spec (ds.css:255-260),
 * exposed here as `.dxr-tbl`. Replaces the per-page hand-rolled `<table>`s
 * (GiftCard, Loyalty, Supplier, Branch, Channel, Product, …) so every
 * list-heavy page renders one header treatment (uppercase 10.5px tracked),
 * one row border, and one hover.
 *
 * Column-config driven for the common case; pages that need bespoke markup can
 * still drop down to the `.dxr-tbl` class on a raw <table>.
 */
export interface DataTableColumn<T> {
  /** Header label. */
  header: ReactNode;
  /** Cell renderer for a row. */
  cell: (row: T, index: number) => ReactNode;
  /** Align the column's content (default: start). */
  align?: 'start' | 'center' | 'end';
  /** Extra className applied to both the <th> and <td>. */
  className?: string;
  /** Stable key; falls back to the column index. */
  key?: string;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  /** Stable row key. */
  rowKey: (row: T, index: number) => string | number;
  /** Optional row click handler (adds pointer affordance). */
  onRowClick?: (row: T, index: number) => void;
  /** Rendered in place of the body when there are no rows. */
  empty?: ReactNode;
  className?: string;
}

const ALIGN: Record<NonNullable<DataTableColumn<unknown>['align']>, string> = {
  start: 'text-start',
  center: 'text-center',
  end: 'text-end',
};

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty,
  className,
}: DataTableProps<T>) {
  return (
    <div className={cn('w-full overflow-x-auto', className)}>
      <table className="dxr-tbl">
        <thead>
          <tr>
            {/* a11y (#226): the `.dxr-tbl th` overline treatment (index.css) is
                Latin `uppercase tracking-[0.06em]`; reset the tracking under RTL
                so Arabic cursive joins aren't shattered. */}
            {columns.map((col, i) => (
              <th
                key={col.key ?? i}
                className={cn('rtl:tracking-normal', col.align && ALIGN[col.align], col.className)}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && empty ? (
            <tr>
              <td colSpan={columns.length} className="text-center text-muted-foreground">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, ri) => (
              <tr
                key={rowKey(row, ri)}
                onClick={onRowClick ? () => onRowClick(row, ri) : undefined}
                className={cn(onRowClick && 'cursor-pointer')}
              >
                {columns.map((col, ci) => (
                  <td key={col.key ?? ci} className={cn(col.align && ALIGN[col.align], col.className)}>
                    {col.cell(row, ri)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
