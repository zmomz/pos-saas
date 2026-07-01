import { useCallback, useEffect, useMemo, useRef, useState, type ElementType } from 'react';
import { Search, Clock } from 'lucide-react';

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
}

// Debounce so a fast typist fires one /search call, not one per keystroke.
const SEARCH_DEBOUNCE_MS = 180;

// Keep the recent list short so it stays a shortcut, not a scroll.
const MAX_RECENT = 6;

// Read the persisted recent-search terms, tolerating a missing/corrupt entry.
function readRecent(key?: string): string[] {
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
}: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [resultGroups, setResultGroups] = useState<PaletteGroup[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [recent, setRecent] = useState<string[]>(() => readRecent(recentSearchesKey));
  // Monotonic request id: a slow response for a stale query is discarded so the
  // list always reflects the latest keystroke, never an out-of-order reply.
  const reqIdRef = useRef(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
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

  // Recent searches (blank query only), then live backend hits, then the
  // filtered static nav/quick-action groups.
  const displayGroups = useMemo(
    () => [...(recentGroup ? [recentGroup] : []), ...resultGroups, ...filtered],
    [recentGroup, resultGroups, filtered],
  );

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
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
            role="dialog"
            aria-modal="true"
            aria-label={label}
            className="w-full max-w-[560px] overflow-hidden rounded-[18px] border border-border bg-popover shadow-2xl"
          >
            <div className="flex items-center gap-3 border-b border-border px-4 py-4">
              <Search className="h-[19px] w-[19px] text-muted-foreground" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={placeholder}
                aria-label={placeholder}
                className="w-full bg-transparent text-base text-foreground outline-none placeholder:text-muted-foreground"
              />
            </div>
            <div className="max-h-[50vh] overflow-y-auto p-2">
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
              {!searching && !searchError && displayGroups.length === 0 && (
                <div className="px-3 py-6 text-center text-sm text-muted-foreground">No matches</div>
              )}
              {displayGroups.map((g) => (
                <div key={g.label} className="p-1">
                  <div className="px-3 pb-1 pt-2 font-mono text-[10px] uppercase tracking-[0.12em] rtl:tracking-normal text-muted-foreground">
                    {g.label}
                  </div>
                  {g.items.map((it) => {
                    const Icon = it.icon;
                    return (
                      <button
                        key={it.label}
                        type="button"
                        onClick={() => {
                          // A committed action on a non-blank query is a "real"
                          // search worth remembering (#231).
                          recordSearch(q);
                          it.onSelect?.();
                          if (!it.keepOpen) setOpen(false);
                        }}
                        className="flex w-full items-center gap-3 rounded-[11px] px-3 py-2.5 text-start text-sm font-semibold text-foreground transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-brand-500/10"
                      >
                        <Icon className="h-[18px] w-[18px] text-muted-foreground" />
                        {it.label}
                        {it.kbd && <span className="ms-auto font-mono text-[11px] text-muted-foreground">{it.kbd}</span>}
                      </button>
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
