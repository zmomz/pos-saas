import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Search, Package } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// ISSUE-226 (Accessibility — keyboard-only nav audit): the ⌘K palette is an
// `aria-modal` dialog, so keyboard focus must stay *inside* it while open (WCAG
// 2.4.3 Focus Order). Without a focus trap a keyboard-only user who Tabs past the
// last row lands on controls behind the backdrop — interacting with a page they
// can't see under the modal. Tab from the last focusable must wrap to the first,
// and Shift+Tab from the first must wrap to the last.

const onReports = vi.fn();
const onProducts = vi.fn();

function makeGroups(): PaletteGroup[] {
  return [
    {
      label: 'Navigate',
      items: [
        { icon: Search, label: 'Go to reports', onSelect: onReports },
        { icon: Package, label: 'Go to products', onSelect: onProducts },
      ],
    },
  ];
}

beforeEach(() => {
  localStorage.clear();
  onReports.mockReset();
  onProducts.mockReset();
});

describe('CommandPalette focus trap (ISSUE-226)', () => {
  it('wraps focus to the first control when Tab is pressed on the last', () => {
    render(<CommandPalette groups={makeGroups()} triggerLabel="Open search" />);
    fireEvent.click(screen.getByRole('button', { name: /Open search/ }));

    const input = screen.getByRole('combobox');
    const last = screen.getByRole('button', { name: 'Go to products' });
    last.focus();
    expect(last).toHaveFocus();

    fireEvent.keyDown(last, { key: 'Tab' });

    expect(input).toHaveFocus();
  });

  it('wraps focus to the last control when Shift+Tab is pressed on the first', () => {
    render(<CommandPalette groups={makeGroups()} triggerLabel="Open search" />);
    fireEvent.click(screen.getByRole('button', { name: /Open search/ }));

    const input = screen.getByRole('combobox');
    const last = screen.getByRole('button', { name: 'Go to products' });
    input.focus();
    expect(input).toHaveFocus();

    fireEvent.keyDown(input, { key: 'Tab', shiftKey: true });

    expect(last).toHaveFocus();
  });
});
