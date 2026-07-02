import { useCallback, useState } from 'react';

/**
 * #231 (Productivity — saved filters/reports). A named snapshot of a list
 * screen's filter combination (search box + selects + toggles). `value` is the
 * screen-specific filter shape, so the hook is generic over it.
 */
export interface SavedFilter<T> {
  name: string;
  value: T;
}

// Keep the preset list a shortcut, not a second navigation rail.
const MAX_SAVED_FILTERS = 12;

// Read the persisted presets, tolerating a missing or corrupt entry (mirrors
// the CommandPalette localStorage helpers).
function read<T>(key: string): SavedFilter<T>[] {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (e): e is SavedFilter<T> =>
        !!e && typeof e === 'object' && typeof (e as SavedFilter<T>).name === 'string',
    );
  } catch {
    return [];
  }
}

/**
 * Persist a per-screen set of named filter presets in localStorage so a power
 * user re-applies a common view in one click and it survives a reload.
 *
 * - `save(name, value)` upserts by name (trimmed, case-insensitive) so re-saving
 *   under an existing name updates it rather than duplicating; a blank name is
 *   ignored. The list is capped at {@link MAX_SAVED_FILTERS}, oldest dropped.
 * - `remove(name)` deletes the matching preset.
 *
 * `storageKey` scopes the presets to one screen (e.g. products vs. customers).
 */
export function useSavedFilters<T>(storageKey: string) {
  const [saved, setSaved] = useState<SavedFilter<T>[]>(() => read<T>(storageKey));

  const write = useCallback(
    (next: SavedFilter<T>[]) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        /* storage disabled / over quota — keep the in-memory copy */
      }
      return next;
    },
    [storageKey],
  );

  const save = useCallback(
    (name: string, value: T) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      setSaved((prev) => {
        const without = prev.filter((f) => f.name.toLowerCase() !== trimmed.toLowerCase());
        return write([...without, { name: trimmed, value }].slice(-MAX_SAVED_FILTERS));
      });
    },
    [write],
  );

  const remove = useCallback(
    (name: string) => {
      setSaved((prev) => write(prev.filter((f) => f.name.toLowerCase() !== name.toLowerCase())));
    },
    [write],
  );

  return { saved, save, remove };
}

export default useSavedFilters;
