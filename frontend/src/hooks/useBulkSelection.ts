import { useCallback, useMemo, useState } from 'react';

/**
 * #231 (Productivity — bulk ops). Shared multi-row selection state for the
 * management list screens. Extracted from ProductManagement once a second page
 * (CustomerManagement) needed the same select-all-on-page + per-row selection
 * behaviour behind a batch action.
 *
 * - `pageIds` are the row ids currently visible (a page, or the whole filtered
 *   list on screens without pagination). `toggleAllOnPage` only ever touches
 *   these, so an individually-selected off-page row survives a page-level
 *   deselect.
 * - `clear()` is what the caller fires after committing a batch action.
 *
 * Generic over the id type so numeric- and string-keyed screens share it.
 */
export function useBulkSelection<Id>(pageIds: Id[]) {
  const [selectedIds, setSelectedIds] = useState<Set<Id>>(new Set());

  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));

  const toggle = useCallback((id: Id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAllOnPage = useCallback(() => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      // Recompute against the latest state so a stale render can't misjudge the
      // add-vs-remove direction.
      const everyOnPage = pageIds.length > 0 && pageIds.every((id) => next.has(id));
      if (everyOnPage) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });
  }, [pageIds]);

  const clear = useCallback(() => setSelectedIds(new Set()), []);

  const isSelected = useCallback((id: Id) => selectedIds.has(id), [selectedIds]);

  return useMemo(
    () => ({
      selectedIds,
      selectedCount: selectedIds.size,
      allPageSelected,
      isSelected,
      toggle,
      toggleAllOnPage,
      clear,
    }),
    [selectedIds, allPageSelected, isSelected, toggle, toggleAllOnPage, clear],
  );
}

export default useBulkSelection;
