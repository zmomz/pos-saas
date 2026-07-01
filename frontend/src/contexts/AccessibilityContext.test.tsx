import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AccessibilityProvider, useAccessibility } from './AccessibilityContext';

// A tiny consumer that surfaces the a11y state and exposes buttons to mutate it,
// mirroring how the rest of the suite exercises context via a rendered component
// (there is no renderHook helper in this repo).
function Probe() {
  const {
    highContrast,
    toggleHighContrast,
    fontScale,
    setFontScale,
    cycleFontScale,
  } = useAccessibility();
  return (
    <div>
      <span data-testid="hc">{String(highContrast)}</span>
      <span data-testid="scale">{fontScale}</span>
      <button onClick={toggleHighContrast}>toggle-hc</button>
      <button onClick={() => setFontScale('large')}>set-large</button>
      <button onClick={cycleFontScale}>cycle</button>
    </div>
  );
}

const renderProbe = () =>
  render(
    <AccessibilityProvider>
      <Probe />
    </AccessibilityProvider>,
  );

describe('AccessibilityContext — high contrast', () => {
  beforeEach(() => {
    document.documentElement.className = '';
    document.documentElement.removeAttribute('data-font-scale');
  });

  it('defaults off, and toggling adds the `hc` root class and persists it', async () => {
    const user = userEvent.setup();
    renderProbe();

    expect(screen.getByTestId('hc')).toHaveTextContent('false');
    expect(document.documentElement.classList.contains('hc')).toBe(false);

    await user.click(screen.getByText('toggle-hc'));

    expect(screen.getByTestId('hc')).toHaveTextContent('true');
    expect(document.documentElement.classList.contains('hc')).toBe(true);
    expect(localStorage.getItem('pos_a11y_high_contrast')).toBe('true');
  });

  it('restores a persisted high-contrast preference on mount', () => {
    localStorage.setItem('pos_a11y_high_contrast', 'true');
    renderProbe();

    expect(screen.getByTestId('hc')).toHaveTextContent('true');
    expect(document.documentElement.classList.contains('hc')).toBe(true);
  });
});

describe('AccessibilityContext — font scaling', () => {
  beforeEach(() => {
    document.documentElement.className = '';
    document.documentElement.removeAttribute('data-font-scale');
  });

  it('defaults to `normal` and reflects the scale on the root attribute', () => {
    renderProbe();

    expect(screen.getByTestId('scale')).toHaveTextContent('normal');
    expect(document.documentElement.getAttribute('data-font-scale')).toBe('normal');
  });

  it('sets a larger font scale, applying the root attribute and persisting it', async () => {
    const user = userEvent.setup();
    renderProbe();

    await user.click(screen.getByText('set-large'));

    expect(screen.getByTestId('scale')).toHaveTextContent('large');
    expect(document.documentElement.getAttribute('data-font-scale')).toBe('large');
    expect(localStorage.getItem('pos_a11y_font_scale')).toBe('large');
  });

  it('restores a persisted font scale on mount', () => {
    localStorage.setItem('pos_a11y_font_scale', 'x-large');
    renderProbe();

    expect(screen.getByTestId('scale')).toHaveTextContent('x-large');
    expect(document.documentElement.getAttribute('data-font-scale')).toBe('x-large');
  });

  it('cycles normal → large → x-large → normal', async () => {
    const user = userEvent.setup();
    renderProbe();

    await user.click(screen.getByText('cycle'));
    expect(screen.getByTestId('scale')).toHaveTextContent('large');
    await user.click(screen.getByText('cycle'));
    expect(screen.getByTestId('scale')).toHaveTextContent('x-large');
    await user.click(screen.getByText('cycle'));
    expect(screen.getByTestId('scale')).toHaveTextContent('normal');
  });
});

describe('useAccessibility guard', () => {
  it('throws when used outside an AccessibilityProvider', () => {
    // Silence the expected React error boundary noise for this negative case.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/must be used within an AccessibilityProvider/);
    spy.mockRestore();
  });
});
