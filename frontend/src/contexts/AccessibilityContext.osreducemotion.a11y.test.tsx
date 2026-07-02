import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';

import { AccessibilityProvider, useAccessibility } from './AccessibilityContext';

/**
 * ISSUE-226 (a11y) — honour the OS-level `prefers-reduced-motion: reduce` app-wide.
 *
 * The in-app reduce-motion toggle stilled animations only when a viewer flipped
 * it. A viewer who had already expressed the preference at the OS level (e.g. a
 * vestibular-disorder user, WCAG 2.3.3) still got the full motion treatment
 * everywhere except the one `CountUp` component that checked the query itself.
 * The provider now treats the OS query as an additional source of truth: the
 * `reduce-motion` root class is applied when the explicit toggle OR the OS
 * preference asks for it, and it reacts live if the OS setting changes.
 */

function Probe() {
  const { reduceMotion, toggleReduceMotion } = useAccessibility();
  return (
    <div>
      <span data-testid="rm">{String(reduceMotion)}</span>
      <button onClick={toggleReduceMotion}>toggle-rm</button>
    </div>
  );
}

const renderProbe = () =>
  render(
    <AccessibilityProvider>
      <Probe />
    </AccessibilityProvider>,
  );

// A controllable matchMedia stub for the reduced-motion query so a test can both
// seed the initial OS preference and flip it while the provider is mounted.
function installReducedMotionMedia(initialMatches: boolean) {
  let matches = initialMatches;
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const mql = {
    get matches() {
      return matches;
    },
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
    addListener: (cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeListener: (cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
    dispatchEvent: () => true,
  };
  window.matchMedia = ((query: string) => {
    if (/prefers-reduced-motion/.test(query)) return mql as unknown as MediaQueryList;
    return {
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    } as unknown as MediaQueryList;
  }) as typeof window.matchMedia;
  return {
    setMatches(next: boolean) {
      matches = next;
      const e = { matches: next } as MediaQueryListEvent;
      listeners.forEach((cb) => cb(e));
    },
  };
}

describe('AccessibilityContext — OS prefers-reduced-motion', () => {
  const realMatchMedia = window.matchMedia;

  beforeEach(() => {
    document.documentElement.className = '';
    localStorage.clear();
  });

  afterEach(() => {
    window.matchMedia = realMatchMedia;
  });

  it('applies the reduce-motion root class when the OS prefers reduced motion, without flipping the explicit toggle', () => {
    installReducedMotionMedia(true);

    renderProbe();

    // Motion is stilled app-wide…
    expect(document.documentElement.classList.contains('reduce-motion')).toBe(true);
    // …but the *explicit* user preference is still off (nothing was toggled/persisted).
    expect(screen.getByTestId('rm')).toHaveTextContent('false');
    expect(localStorage.getItem('pos_a11y_reduce_motion')).not.toBe('true');
  });

  it('does not apply the class when the OS does not prefer reduced motion and the toggle is off', () => {
    installReducedMotionMedia(false);

    renderProbe();

    expect(document.documentElement.classList.contains('reduce-motion')).toBe(false);
  });

  it('reacts when the OS preference changes while mounted', () => {
    const media = installReducedMotionMedia(false);

    renderProbe();
    expect(document.documentElement.classList.contains('reduce-motion')).toBe(false);

    act(() => media.setMatches(true));
    expect(document.documentElement.classList.contains('reduce-motion')).toBe(true);

    act(() => media.setMatches(false));
    expect(document.documentElement.classList.contains('reduce-motion')).toBe(false);
  });
});
