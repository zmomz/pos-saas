import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from 'react';

/**
 * Accessibility program (ISSUE-226) — the foundational a11y *modes* slice.
 *
 * A single source of truth for the two viewer-driven display preferences that
 * the rest of the accessibility work builds on:
 *   - high-contrast mode (a `hc` class on <html> that swaps in higher-contrast
 *     design tokens — see index.css), and
 *   - font scaling (a `data-font-scale` attribute on <html> that steps the base
 *     font size up for low-vision users).
 *
 * Both are persisted to localStorage and re-applied on load, so a viewer's
 * choice survives a refresh and every worker/tab respects it. Kept separate
 * from ThemeContext (light/dark is a brand/preference axis; contrast and text
 * size are assistive axes that compose *on top of* either theme).
 */

export type FontScale = 'normal' | 'large' | 'x-large';

export const FONT_SCALES: readonly FontScale[] = ['normal', 'large', 'x-large'];

const HC_KEY = 'pos_a11y_high_contrast';
const FONT_KEY = 'pos_a11y_font_scale';

interface AccessibilityContextType {
  highContrast: boolean;
  toggleHighContrast: () => void;
  setHighContrast: (on: boolean) => void;
  fontScale: FontScale;
  setFontScale: (scale: FontScale) => void;
  cycleFontScale: () => void;
}

const AccessibilityContext = createContext<AccessibilityContextType | null>(null);

export const useAccessibility = () => {
  const context = useContext(AccessibilityContext);
  if (!context) {
    throw new Error('useAccessibility must be used within an AccessibilityProvider');
  }
  return context;
};

const readFontScale = (): FontScale => {
  const stored = localStorage.getItem(FONT_KEY);
  return stored && (FONT_SCALES as readonly string[]).includes(stored)
    ? (stored as FontScale)
    : 'normal';
};

interface AccessibilityProviderProps {
  children: ReactNode;
}

export const AccessibilityProvider: React.FC<AccessibilityProviderProps> = ({ children }) => {
  const [highContrast, setHighContrastState] = useState<boolean>(
    () => localStorage.getItem(HC_KEY) === 'true',
  );
  const [fontScale, setFontScaleState] = useState<FontScale>(readFontScale);

  useEffect(() => {
    document.documentElement.classList.toggle('hc', highContrast);
    localStorage.setItem(HC_KEY, String(highContrast));
  }, [highContrast]);

  useEffect(() => {
    document.documentElement.setAttribute('data-font-scale', fontScale);
    localStorage.setItem(FONT_KEY, fontScale);
  }, [fontScale]);

  const toggleHighContrast = useCallback(() => setHighContrastState((prev) => !prev), []);
  const setHighContrast = useCallback((on: boolean) => setHighContrastState(on), []);
  const setFontScale = useCallback((scale: FontScale) => setFontScaleState(scale), []);
  const cycleFontScale = useCallback(
    () =>
      setFontScaleState((prev) => {
        const i = FONT_SCALES.indexOf(prev);
        return FONT_SCALES[(i + 1) % FONT_SCALES.length];
      }),
    [],
  );

  return (
    <AccessibilityContext.Provider
      value={{
        highContrast,
        toggleHighContrast,
        setHighContrast,
        fontScale,
        setFontScale,
        cycleFontScale,
      }}
    >
      {children}
    </AccessibilityContext.Provider>
  );
};
