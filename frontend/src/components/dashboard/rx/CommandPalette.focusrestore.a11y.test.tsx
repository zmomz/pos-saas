import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Search, Package } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// ISSUE-226 (Accessibility — keyboard-only nav audit): the ⌘K palette is a modal
// dialog, so when it closes keyboard focus must return to the control that opened
// it (WCAG 2.4.3 Focus Order). Without this a keyboard-only user is dumped at the
// top of the document every time they dismiss the palette and loses their place.

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

describe('CommandPalette focus restoration (ISSUE-226)', () => {
  it('returns focus to the trigger when the palette is closed with Escape', () => {
    render(<CommandPalette groups={makeGroups()} triggerLabel="Open search" />);
    const trigger = screen.getByRole('button', { name: /Open search/ });

    fireEvent.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it('returns focus to the trigger after activating a result', () => {
    render(<CommandPalette groups={makeGroups()} triggerLabel="Open search" />);
    const trigger = screen.getByRole('button', { name: /Open search/ });

    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: 'Go to reports' }));

    expect(onReports).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it('returns focus to the trigger when the backdrop is clicked', () => {
    render(<CommandPalette groups={makeGroups()} triggerLabel="Open search" />);
    const trigger = screen.getByRole('button', { name: /Open search/ });

    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog');
    // The overlay is the dialog's parent; clicking it (not the panel) dismisses.
    fireEvent.click(dialog.parentElement as HTMLElement);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(trigger).toHaveFocus();
  });
});
