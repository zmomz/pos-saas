import { useEffect, useMemo, useState, type ElementType } from 'react';
import { Search } from 'lucide-react';

export interface PaletteItem {
  icon: ElementType;
  label: string;
  kbd?: string;
  onSelect?: () => void;
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
}

/**
 * ⌘K / Ctrl-K command palette. Renders the trigger pill (for the page command
 * bar) plus the modal overlay. Self-contained: manages open state, keyboard
 * shortcut, Esc-to-close and live filtering.
 */
export default function CommandPalette({
  placeholder = 'Search or run a command…',
  triggerLabel = 'Search or run a command',
  label = 'Command palette',
  groups,
}: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');

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

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return groups;
    return groups
      .map((g) => ({ ...g, items: g.items.filter((i) => i.label.toLowerCase().includes(needle)) }))
      .filter((g) => g.items.length > 0);
  }, [q, groups]);

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
              {filtered.length === 0 && (
                <div className="px-3 py-6 text-center text-sm text-muted-foreground">No matches</div>
              )}
              {filtered.map((g) => (
                <div key={g.label} className="p-1">
                  <div className="px-3 pb-1 pt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                    {g.label}
                  </div>
                  {g.items.map((it) => {
                    const Icon = it.icon;
                    return (
                      <button
                        key={it.label}
                        type="button"
                        onClick={() => {
                          it.onSelect?.();
                          setOpen(false);
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
