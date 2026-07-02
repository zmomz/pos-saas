import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import RouteAnnouncer from './RouteAnnouncer';

// ISSUE-226 (a11y · screen-reader pass) — SPA route announcer, WCAG 2.4.x.
// A single-page app swaps the <main> content on navigation without a full page
// load, so a screen reader gets NO signal that the destination changed: focus
// stays put and nothing is spoken. This adds a persistent polite live region
// that narrates the new page's name on every in-app route change, while staying
// silent on the very first mount (the surrounding page load already gives the
// user context there).

describe('RouteAnnouncer (ISSUE-226)', () => {
  it('exposes a polite, atomic, visually-hidden live region', () => {
    const { getByTestId } = render(<RouteAnnouncer title="Products" />);
    const region = getByTestId('route-announcer');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveAttribute('aria-atomic', 'true');
    // sr-only keeps it out of the visual layout but in the a11y tree.
    expect(region.className).toContain('sr-only');
  });

  it('stays silent on the initial mount (no premature announcement)', () => {
    const { getByTestId } = render(<RouteAnnouncer title="Products" />);
    // Live regions only announce *updates*; speaking on first paint would
    // double up with the browser's own page-load context, so start empty.
    expect(getByTestId('route-announcer').textContent).toBe('');
  });

  it('announces the new page name when the title changes (a navigation)', () => {
    const { getByTestId, rerender } = render(<RouteAnnouncer title="Products" />);
    rerender(<RouteAnnouncer title="Reports" />);
    expect(getByTestId('route-announcer').textContent).toBe('Reports');
  });
});
