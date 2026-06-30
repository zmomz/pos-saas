import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { PaletteGroup } from '@/components/dashboard/rx/CommandPalette';

/**
 * Chrome a page contributes to the shared shell command bar. The shell owns the
 * 80px icon rail, greeting, ⌘K palette and notification bell; a page only needs
 * to supply its subtitle line, a primary action button and any ⌘K quick actions.
 */
export interface PageChromeConfig {
  /**
   * Page-identity H1 (issue #213). Overrides the title the shell derives from
   * the nav rail; ignored on the dashboard home, which keeps the greeting.
   */
  title?: string;
  /** Subtitle line shown under the greeting (defaults to nothing). */
  subtitle?: string;
  /** Primary action button rendered at the end of the command bar. */
  primaryAction?: ReactNode;
  /** Page-specific quick actions prepended to the global ⌘K palette. */
  paletteGroups?: PaletteGroup[];
}

interface PageChromeContextValue {
  chrome: PageChromeConfig;
  setChrome: (c: PageChromeConfig) => void;
}

const PageChromeContext = createContext<PageChromeContextValue | null>(null);

export function PageChromeProvider({ children }: { children: ReactNode }) {
  const [chrome, setChrome] = useState<PageChromeConfig>({});
  return (
    <PageChromeContext.Provider value={{ chrome, setChrome }}>
      {children}
    </PageChromeContext.Provider>
  );
}

/** Shell-side reader. Returns an empty config when used outside a provider. */
export function useShellChrome(): PageChromeConfig {
  return useContext(PageChromeContext)?.chrome ?? {};
}

/**
 * Page-side setter. Registers command-bar chrome for the current route and
 * clears it on unmount. Pass a dependency list so the chrome refreshes when the
 * page's handlers or labels change (same contract as `useEffect`).
 */
export function usePageChrome(config: PageChromeConfig, deps: unknown[]) {
  const ctx = useContext(PageChromeContext);
  const setChrome = ctx?.setChrome;
  useEffect(() => {
    if (!setChrome) return;
    setChrome(config);
    return () => setChrome({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setChrome, ...deps]);
}
