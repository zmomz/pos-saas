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
 *     font size up for low-vision users), and
 *   - reduce motion (a `reduce-motion` class on <html> that stills animations
 *     and transitions app-wide — an in-app control for viewers who cannot set
 *     the OS-level `prefers-reduced-motion` setting, e.g. on a shared terminal).
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
const REDUCE_MOTION_KEY = 'pos_a11y_reduce_motion';

interface AccessibilityContextType {
  highContrast: boolean;
  toggleHighContrast: () => void;
  setHighContrast: (on: boolean) => void;
  fontScale: FontScale;
  setFontScale: (scale: FontScale) => void;
  cycleFontScale: () => void;
  reduceMotion: boolean;
  toggleReduceMotion: () => void;
  setReduceMotion: (on: boolean) => void;
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
  const [reduceMotion, setReduceMotionState] = useState<boolean>(
    () => localStorage.getItem(REDUCE_MOTION_KEY) === 'true',
  );

  useEffect(() => {
    document.documentElement.classList.toggle('hc', highContrast);
    localStorage.setItem(HC_KEY, String(highContrast));
  }, [highContrast]);

  useEffect(() => {
    document.documentElement.setAttribute('data-font-scale', fontScale);
    localStorage.setItem(FONT_KEY, fontScale);
  }, [fontScale]);

  useEffect(() => {
    document.documentElement.classList.toggle('reduce-motion', reduceMotion);
    localStorage.setItem(REDUCE_MOTION_KEY, String(reduceMotion));
  }, [reduceMotion]);

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
  const toggleReduceMotion = useCallback(() => setReduceMotionState((prev) => !prev), []);
  const setReduceMotion = useCallback((on: boolean) => setReduceMotionState(on), []);

  return (
    <AccessibilityContext.Provider
      value={{
        highContrast,
        toggleHighContrast,
        setHighContrast,
        fontScale,
        setFontScale,
        cycleFontScale,
        reduceMotion,
        toggleReduceMotion,
        setReduceMotion,
      }}
    >
      {children}
    </AccessibilityContext.Provider>
  );
};
