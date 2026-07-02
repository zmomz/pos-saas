import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Search, Package } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// ISSUE-226 (Accessibility — screen-reader pass): the ⌘K palette already drives
// the combobox `aria-activedescendant` / `aria-selected` highlight pattern, but
// its results container carried no `role="listbox"` and its rows no
// `role="option"`. `aria-selected` and `aria-activedescendant` are only valid
// when they point at an `option` owned by a `listbox` (WCAG 4.1.2 Name, Role,
// Value) — without those roles the highlight the code sets is meaningless to a
// screen reader and the combobox references a control of no known role. This
// slice completes the combobox↔listbox↔option contract.

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

function open() {
  render(<CommandPalette groups={makeGroups()} triggerLabel="Open search" />);
  fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
  return screen.getByRole('combobox');
}

beforeEach(() => {
  localStorage.clear();
  onReports.mockReset();
  onProducts.mockReset();
});

describe('CommandPalette listbox/option roles (ISSUE-226)', () => {
  it('exposes the results as a listbox the combobox controls', () => {
    const input = open();
    const listbox = screen.getByRole('listbox');
    expect(input).toHaveAttribute('aria-controls', listbox.id);
  });

  it('exposes each result row with the option role', () => {
    open();
    expect(screen.getByRole('option', { name: 'Go to reports' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Go to products' })).toBeInTheDocument();
  });

  it('points aria-activedescendant at the highlighted option', () => {
    const input = open();
    fireEvent.keyDown(input, { key: 'ArrowDown' });

    const first = screen.getByRole('option', { name: 'Go to reports' });
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', first.id);
  });
});
