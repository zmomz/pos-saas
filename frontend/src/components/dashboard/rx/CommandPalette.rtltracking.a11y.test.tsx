import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Search } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// ISSUE-226 (a11y · RTL) — Arabic script joins its letters cursively, so ANY
// letter-spacing (Latin `tracking-*` utilities, including the uppercase
// "overline" group-label pattern) shatters those joins and hurts legibility.
// The base `[dir='rtl']` letter-spacing reset in index.css sits in @layer base
// and therefore loses to Tailwind's utility layer, so component overline
// labels keep their tracking under Arabic. The fix mirrors the `rtl:rotate-180`
// idiom already used for directional icons: an `rtl:tracking-normal` variant
// that neutralises the spacing only under an RTL ancestor, while the Latin
// tracking is preserved in LTR.

const GROUPS: PaletteGroup[] = [
  { label: 'Navigate', items: [{ icon: Search, label: 'Go to reports' }] },
];

function open() {
  render(<CommandPalette groups={GROUPS} triggerLabel="Open search" />);
  fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
}

describe('CommandPalette RTL letter-spacing (ISSUE-226)', () => {
  it('resets tracking on the uppercase group heading under RTL', () => {
    open();
    const heading = screen.getByText('Navigate');
    // Latin tracking stays for the LTR reading; the RTL variant neutralises it.
    expect(heading.className).toMatch(/tracking-/);
    expect(heading.className).toContain('rtl:tracking-normal');
  });
});
