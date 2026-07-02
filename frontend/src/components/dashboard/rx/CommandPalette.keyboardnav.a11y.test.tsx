import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Search, Package } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// ISSUE-226 (Accessibility — keyboard-only nav audit): a keyboard-only user must
// be able to move through the ⌘K palette results with the Arrow keys and run the
// highlighted one with Enter, without Tab-cycling every row. The active option is
// announced via the combobox `aria-activedescendant` / `aria-selected` pattern so
// a screen reader tracks the highlight as it moves.

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

describe('CommandPalette keyboard navigation (ISSUE-226)', () => {
  it('highlights the first result on ArrowDown and points aria-activedescendant at it', () => {
    const input = open();

    // Nothing highlighted until the viewer navigates.
    expect(input).not.toHaveAttribute('aria-activedescendant');

    fireEvent.keyDown(input, { key: 'ArrowDown' });

    const first = screen.getByRole('button', { name: 'Go to reports' });
    expect(first.id).toBeTruthy();
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', first.id);
  });

  it('activates the highlighted item on Enter and closes the palette', () => {
    const input = open();

    fireEvent.keyDown(input, { key: 'ArrowDown' }); // highlight "Go to reports"
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onReports).toHaveBeenCalledTimes(1);
    expect(onProducts).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('wraps to the last item when ArrowUp is pressed from the top', () => {
    const input = open();

    fireEvent.keyDown(input, { key: 'ArrowUp' }); // from nothing -> last

    const last = screen.getByRole('button', { name: 'Go to products' });
    expect(last).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', last.id);
  });

  it('does nothing on Enter when no item is highlighted', () => {
    const input = open();

    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onReports).not.toHaveBeenCalled();
    expect(onProducts).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeNull(); // still open
  });
});
