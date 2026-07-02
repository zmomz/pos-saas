import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ElementType,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { Search, Clock, Star } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface PaletteItem {
  icon: ElementType;
  label: string;
  kbd?: string;
  onSelect?: () => void;
  /**
   * By default selecting an item closes the palette. Recent-search chips set
   * this so activating one refills the query and re-runs the search *in place*
   * instead of dismissing the palette.
   */
  keepOpen?: boolean;
}
export interface PaletteGroup {
  label: string;
  items: PaletteItem[];
}

interface CommandPaletteProps {
  placeholder?: string;
  /** text shown inside the trigger pill in the command bar */
  triggerLabel?: string;
  /** accessible name announced for the modal dialog */
  label?: string;
  groups: PaletteGroup[];
  /**
   * Optional async backend search (#231). When provided, the current query is
   * debounced and passed to it; the returned groups are merged in *above* the
   * static ones so live /search hits (products/customers/transactions) surface
   * from the global palette. Omit it and the palette stays a pure static filter.
   */
  onSearch?: (query: string) => Promise<PaletteGroup[]>;
  /** shown while an onSearch request is in flight */
  searchingLabel?: string;
  /** shown when an onSearch request rejects */
  searchErrorLabel?: string;
  /**
   * localStorage key for the recent-searches history (#231). When supplied, the
   * query a viewer acts on is remembered and, on the next blank open, the past
   * terms surface under a "Recent" group so a frequent search re-runs in one
   * click. Omit it and no history is kept.
   */
  recentSearchesKey?: string;
  /** header for the recent-searches group */
  recentLabel?: string;
  /**
   * localStorage key for pinned favorites (#231). When supplied, every static
   * nav / quick-action item gains a star toggle; starred labels are remembered
   * and surface under a "Favorites" group at the very top on a blank query, so
   * a power user reaches their most-used pages in one keystroke. Live /search
   * hits and the Recent chips are never favouritable. Omit it and no star shows.
   */
  favoritesKey?: string;
  /** header for the favorites group */
  favoritesLabel?: string;
  /** accessible verb for the "pin" star toggle (item label is appended) */
  favoriteAddLabel?: string;
  /** accessible verb for the "unpin" star toggle (item label is appended) */
  favoriteRemoveLabel?: string;
}

// Debounce so a fast typist fires one /search call, not one per keystroke.
const SEARCH_DEBOUNCE_MS = 180;

// Keep the recent list short so it stays a shortcut, not a scroll.
const MAX_RECENT = 6;

// Keep the pinned list short so Favorites stays a shortcut, not a second rail.
const MAX_FAVORITES = 8;

// Read a persisted string list (recent terms / favorite labels), tolerating a
// missing or corrupt entry.
function readStringList(key?: string): string[] {
  if (!key) return [];
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((t): t is string => typeof t === 'string') : [];
  } catch {
    return [];
  }
}

/**
 * ⌘K / Ctrl-K command palette. Renders the trigger pill (for the page command
 * bar) plus the modal overlay. Self-contained: manages open state, keyboard
 * shortcut, Esc-to-close and live filtering. With `onSearch` it also merges
 * live backend results into the list (#231 global search).
 */
export default function CommandPalette({
  placeholder = 'Search or run a command…',
  triggerLabel = 'Search or run a command',
  label = 'Command palette',
  groups,
  onSearch,
  searchingLabel = 'Searching…',
  searchErrorLabel = 'Search failed',
  recentSearchesKey,
  recentLabel = 'Recent',
  favoritesKey,
  favoritesLabel = 'Favorites',
  favoriteAddLabel = 'Add to favorites',
  favoriteRemoveLabel = 'Remove from favorites',
}: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [resultGroups, setResultGroups] = useState<PaletteGroup[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [recent, setRecent] = useState<string[]>(() => readStringList(recentSearchesKey));
  const [favorites, setFavorites] = useState<string[]>(() => readStringList(favoritesKey));
  // Index of the arrow-key-highlighted result across the whole flattened list
  // (-1 = nothing highlighted). Drives the combobox `aria-activedescendant`
  // pointer and each row's `aria-selected` so keyboard-only / SR users can walk
  // the palette without Tab-cycling every row (ISSUE-226).
  const [active, setActive] = useState(-1);
  // Monotonic request id: a slow response for a stale query is discarded so the
  // list always reflects the latest keystroke, never an out-of-order reply.
  const reqIdRef = useRef(0);
  // The element focused just before the palette opened. Restored on close so a
  // keyboard-only user returns to where they were instead of the top of the
  // document (WCAG 2.4.3). Covers every open path — trigger click and ⌘K alike.
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  // The dialog panel, so a Tab press can be confined to the focusables inside it
  // (focus trap) rather than escaping to the page behind the backdrop.
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => {
          if (!o) restoreFocusRef.current = document.activeElement as HTMLElement | null;
          return !o;
        });
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Closing the palette clears any live results so reopening never flashes stale
  // hits from a previous query.
  useEffect(() => {
    if (!open) {
      reqIdRef.current++;
      setQ('');
      setResultGroups([]);
      setSearching(false);
      setSearchError(false);
      // The dialog has unmounted by the time this effect runs, so returning
      // focus to the opener never fights the palette's own autofocus.
      restoreFocusRef.current?.focus();
      restoreFocusRef.current = null;
    }
  }, [open]);

  // Debounced backend search for the current query (#231).
  useEffect(() => {
    if (!open || !onSearch) return;
    const needle = q.trim();
    if (!needle) {
      reqIdRef.current++;
      setResultGroups([]);
      setSearching(false);
      setSearchError(false);
      return;
    }
    const reqId = ++reqIdRef.current;
    setSearching(true);
    setSearchError(false);
    const timer = setTimeout(() => {
      onSearch(needle)
        .then((gs) => {
          if (reqId !== reqIdRef.current) return; // stale response — ignore
          setResultGroups(gs);
        })
        .catch(() => {
          if (reqId !== reqIdRef.current) return;
          setResultGroups([]);
          setSearchError(true);
        })
        .finally(() => {
          if (reqId !== reqIdRef.current) return;
          setSearching(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [q, open, onSearch]);

  // Commit a term the viewer acted on to the front of the history (case-
  // insensitive dedup, capped, most-recent-first), persisting it so it
  // survives a reload. No-op unless the caller opted into a history key.
  const recordSearch = useCallback(
    (term: string) => {
      if (!recentSearchesKey) return;
      const trimmed = term.trim();
      if (!trimmed) return;
      setRecent((prev) => {
        const next = [trimmed, ...prev.filter((t) => t.toLowerCase() !== trimmed.toLowerCase())].slice(
          0,
          MAX_RECENT,
        );
        try {
          localStorage.setItem(recentSearchesKey, JSON.stringify(next));
        } catch {
          /* storage full / unavailable — keep the in-memory list anyway */
        }
        return next;
      });
    },
    [recentSearchesKey],
  );

  // Pin / unpin a nav destination by label, persisting the list so it survives
  // a reload. New pins go to the front (most-recent-first), capped. No-op unless
  // the caller opted into a favorites key.
  const toggleFavorite = useCallback(
    (label: string) => {
      if (!favoritesKey) return;
      setFavorites((prev) => {
        const next = prev.includes(label)
          ? prev.filter((f) => f !== label)
          : [label, ...prev].slice(0, MAX_FAVORITES);
        try {
          localStorage.setItem(favoritesKey, JSON.stringify(next));
        } catch {
          /* storage full / unavailable — keep the in-memory list anyway */
        }
        return next;
      });
    },
    [favoritesKey],
  );

  // Favorites group: only on a blank query, resolving each pinned label back to
  // its live item from the static groups. A pin whose destination no longer
  // exists (renamed/removed nav item) is silently dropped, never a dead row.
  const favoritesGroup = useMemo<PaletteGroup | null>(() => {
    if (!favoritesKey || q.trim() || favorites.length === 0) return null;
    const byLabel = new Map<string, PaletteItem>();
    for (const g of groups) for (const it of g.items) byLabel.set(it.label, it);
    const items = favorites
      .map((label) => byLabel.get(label))
      .filter((it): it is PaletteItem => Boolean(it));
    if (items.length === 0) return null;
    return { label: favoritesLabel, items };
  }, [favoritesKey, q, favorites, groups, favoritesLabel]);

  // Recent-search group: only on a blank query, and only once there's history.
  const recentGroup = useMemo<PaletteGroup | null>(() => {
    if (q.trim() || recent.length === 0) return null;
    return {
      label: recentLabel,
      items: recent.map((term) => ({
        icon: Clock,
        label: term,
        keepOpen: true,
        onSelect: () => setQ(term),
      })),
    };
  }, [q, recent, recentLabel]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return groups;
    return groups
      .map((g) => ({ ...g, items: g.items.filter((i) => i.label.toLowerCase().includes(needle)) }))
      .filter((g) => g.items.length > 0);
  }, [q, groups]);

  // Favorites (blank query only), then recent searches (blank query only), then
  // live backend hits, then the filtered static nav/quick-action groups. Only
  // the favorites + static groups are favouritable — the Recent chips and live
  // /search hits carry no stable pin identity.
  const sections = useMemo(
    () => [
      ...(favoritesGroup ? [{ group: favoritesGroup, favouritable: true }] : []),
      ...(recentGroup ? [{ group: recentGroup, favouritable: false }] : []),
      ...resultGroups.map((group) => ({ group, favouritable: false })),
      ...filtered.map((group) => ({ group, favouritable: true })),
    ],
    [favoritesGroup, recentGroup, resultGroups, filtered],
  );

  // The activatable rows, flattened in render order, so a single running index
  // can drive Arrow navigation across section boundaries. `offsets[s]` is the
  // flat index of section s's first row.
  const flatItems = useMemo(
    () => sections.flatMap(({ group: g }) => g.items),
    [sections],
  );
  const sectionOffsets = useMemo(() => {
    const offs: number[] = [];
    let acc = 0;
    for (const { group: g } of sections) {
      offs.push(acc);
      acc += g.items.length;
    }
    return offs;
  }, [sections]);
  const listId = 'command-palette-listbox';
  const activeId = active >= 0 && active < flatItems.length ? `${listId}-opt-${active}` : undefined;

  // A new result set (query/results changed) drops any stale highlight — the
  // old index no longer maps to the same row.
  useEffect(() => {
    setActive(-1);
  }, [sections]);

  // Arrow / Enter navigation while focus is in the search box. Wraps at both
  // ends so the list is a loop; Enter runs the highlighted row's action (and
  // remembers the query, mirroring a mouse click). Handled on the input rather
  // than the window listener so it never fights the page's own key bindings.
  const onInputKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLInputElement>) => {
      const n = flatItems.length;
      if (n === 0) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((i) => (i + 1) % n);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((i) => (i <= 0 ? n - 1 : i - 1));
      } else if (e.key === 'Enter' && active >= 0 && active < n) {
        e.preventDefault();
        const it = flatItems[active];
        recordSearch(q);
        it.onSelect?.();
        if (!it.keepOpen) setOpen(false);
      }
    },
    [flatItems, active, q, recordSearch],
  );

  // Focus trap: an `aria-modal` dialog must keep Tab focus inside itself so a
  // keyboard-only user never lands on the page hidden behind the backdrop (WCAG
  // 2.4.3). Wrap at both ends — Tab off the last control returns to the first,
  // Shift+Tab off the first jumps to the last — and pull focus back in if it has
  // somehow strayed outside the panel.
  const onDialogKeyDown = useCallback((e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab') return;
    const root = dialogRef.current;
    if (!root) return;
    const focusables = Array.from(
      root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const activeEl = document.activeElement as HTMLElement | null;
    if (e.shiftKey) {
      if (activeEl === first || !root.contains(activeEl)) {
        e.preventDefault();
        last.focus();
      }
    } else if (activeEl === last || !root.contains(activeEl)) {
      e.preventDefault();
      first.focus();
    }
  }, []);

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          restoreFocusRef.current = e.currentTarget;
          setOpen(true);
        }}
        className="hidden items-center gap-2.5 rounded-full border border-input bg-card px-4 py-2.5 text-[13.5px] text-muted-foreground shadow-sm transition-colors hover:border-brand md:flex"
      >
        <Search className="h-4 w-4" />
        <span>{triggerLabel}</span>
        <span className="ms-2 flex gap-1">
          <kbd className="rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground/70">⌘</kbd>
          <kbd className="rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground/70">K</kbd>
        </span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-[100] flex items-start justify-center bg-foreground/30 p-4 pt-[14vh] backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={label}
            onKeyDown={onDialogKeyDown}
            className="w-full max-w-[560px] overflow-hidden rounded-[18px] border border-border bg-popover shadow-2xl"
          >
            <div className="flex items-center gap-3 border-b border-border px-4 py-4">
              <Search className="h-[19px] w-[19px] text-muted-foreground" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onInputKeyDown}
                placeholder={placeholder}
                aria-label={placeholder}
                role="combobox"
                aria-expanded={flatItems.length > 0}
                aria-controls={listId}
                aria-autocomplete="list"
                aria-activedescendant={activeId}
                className="w-full bg-transparent text-base text-foreground outline-none placeholder:text-muted-foreground"
              />
            </div>
            <div id={listId} className="max-h-[50vh] overflow-y-auto p-2">
              {searchError && (
                <div className="px-3 py-3 text-center text-sm text-warning" role="status">
                  {searchErrorLabel}
                </div>
              )}
              {searching && !searchError && (
                <div className="px-3 py-3 text-center text-sm text-muted-foreground" role="status">
                  {searchingLabel}
                </div>
              )}
              {!searching && !searchError && sections.length === 0 && (
                <div className="px-3 py-6 text-center text-sm text-muted-foreground">No matches</div>
              )}
              {sections.map(({ group: g, favouritable }, sIdx) => (
                <div key={g.label} className="p-1">
                  <div className="px-3 pb-1 pt-2 font-mono text-[10px] uppercase tracking-[0.12em] rtl:tracking-normal text-muted-foreground">
                    {g.label}
                  </div>
                  {g.items.map((it, iIdx) => {
                    const Icon = it.icon;
                    // Star toggles only render when the caller opted into
                    // favorites AND the item lives in a favouritable group.
                    const showStar = Boolean(favoritesKey) && favouritable;
                    const pinned = favorites.includes(it.label);
                    // Flat index across all sections drives the Arrow highlight.
                    const optIndex = sectionOffsets[sIdx] + iIdx;
                    const isActive = optIndex === active;
                    return (
                      <div
                        key={it.label}
                        className={cn(
                          'group flex w-full items-center rounded-[11px] transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10',
                          isActive && 'bg-brand-50 text-brand-700 dark:bg-brand-500/10',
                        )}
                      >
                        <button
                          type="button"
                          id={`${listId}-opt-${optIndex}`}
                          aria-selected={isActive}
                          onClick={() => {
                            // A committed action on a non-blank query is a "real"
                            // search worth remembering (#231).
                            recordSearch(q);
                            it.onSelect?.();
                            if (!it.keepOpen) setOpen(false);
                          }}
                          className="flex min-w-0 flex-1 items-center gap-3 rounded-[11px] px-3 py-2.5 text-start text-sm font-semibold text-foreground"
                        >
                          <Icon className="h-[18px] w-[18px] shrink-0 text-muted-foreground" />
                          <span className="truncate">{it.label}</span>
                          {it.kbd && <span className="ms-auto font-mono text-[11px] text-muted-foreground">{it.kbd}</span>}
                        </button>
                        {showStar && (
                          <button
                            type="button"
                            onClick={() => toggleFavorite(it.label)}
                            aria-pressed={pinned}
                            aria-label={`${pinned ? favoriteRemoveLabel : favoriteAddLabel}: ${it.label}`}
                            className="me-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] text-muted-foreground transition-colors hover:text-gold"
                          >
                            <Star
                              className={cn('h-4 w-4', pinned && 'fill-gold text-gold')}
                              aria-hidden="true"
                            />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
