import { useCallback, useState } from 'react';

/**
 * #273 (Productivity follow-up — entity-level favorites). A per-screen set of
 * "starred" record ids (a favourited customer / product / …), persisted to
 * localStorage so the pins survive a reload. Ids are stored as strings so a
 * numeric primary key and its string form are the same favourite.
 *
 * Mirrors {@link useSavedFilters}' storage discipline: a corrupt or missing
 * entry degrades to an empty set, and writes tolerate storage being disabled.
 */

// Read the persisted id list, tolerating a missing or corrupt entry.
function read(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.map((id) => String(id));
  } catch {
    return [];
  }
}

export function useFavorites(storageKey: string) {
  const [ids, setIds] = useState<Set<string>>(() => new Set(read(storageKey)));

  const write = useCallback(
    (next: Set<string>) => {
      try {
        localStorage.setItem(storageKey, JSON.stringify([...next]));
      } catch {
        /* storage disabled / over quota — keep the in-memory copy */
      }
      return next;
    },
    [storageKey],
  );

  const isFavorite = useCallback((id: string | number) => ids.has(String(id)), [ids]);

  const toggle = useCallback(
    (id: string | number) => {
      const key = String(id);
      setIds((prev) => {
        const next = new Set(prev);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return write(next);
      });
    },
    [write],
  );

  const clear = useCallback(() => setIds(() => write(new Set())), [write]);

  return { favorites: ids, isFavorite, toggle, clear, count: ids.size };
}

export default useFavorites;
