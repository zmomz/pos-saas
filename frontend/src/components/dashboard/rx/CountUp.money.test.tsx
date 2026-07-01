import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import CountUp from './CountUp';
import { RIYAL } from '@/lib/format';

// ISSUE-208 (M11 FE-Platform): currency must flow through `formatMoney*` so the
// riyal sign, grouping and decimals are consistent everywhere. The dashboards
// used to render money as `<CountUp prefix="⃁ " />`, a bespoke bypass that put
// the symbol *before* the number and skipped `formatMoney` entirely. `money`
// mode routes the animated value through `formatMoney` instead.

// Force prefers-reduced-motion so the component renders the final value
// synchronously (no requestAnimationFrame animation to await).
beforeEach(() => {
  window.matchMedia = ((query: string) => ({
    matches: /prefers-reduced-motion/.test(query),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
});

afterEach(() => vi.restoreAllMocks());

describe('CountUp money mode (ISSUE-208)', () => {
  it('routes the value through formatMoney (trailing riyal sign, grouped)', () => {
    const { container } = render(<CountUp value={1234} money lang="en" />);
    // formatMoney => "1,234 ⃁" — symbol trailing, not a leading prefix.
    expect(container.textContent).toBe(`1,234 ${RIYAL}`);
    expect(container.textContent).not.toMatch(/^⃁/);
  });

  it('honours decimals in money mode', () => {
    const { container } = render(<CountUp value={1234.5} money lang="en" decimals={2} />);
    expect(container.textContent).toBe(`1,234.50 ${RIYAL}`);
  });

  it('still supports prefix/suffix when not in money mode', () => {
    const { container } = render(<CountUp value={42} prefix="#" suffix="!" />);
    expect(container.textContent).toBe('#42!');
  });
});
