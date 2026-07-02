import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Search, Package } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// #231 (Productivity — Global search UI): the ⌘K palette used to filter a
// static list of nav/quick-action items only. To make search *global* it now
// accepts an async `onSearch` that queries the cross-entity /search backend and
// merges the live hits into the palette. These tests drive that wiring through
// the rendered palette.

const STATIC: PaletteGroup[] = [
  { label: 'Navigate', items: [{ icon: Search, label: 'Go to reports' }] },
];

function openWith(props: Record<string, unknown>) {
  render(<CommandPalette groups={STATIC} triggerLabel="Open search" {...props} />);
  fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
}

describe('CommandPalette live /search (#231)', () => {
  it('surfaces backend hits for a typed query', async () => {
    const onSearch = vi.fn().mockResolvedValue([
      { label: 'Products', items: [{ icon: Package, label: 'Widget · 123', onSelect: vi.fn() }] },
    ] as PaletteGroup[]);
    const user = userEvent.setup();
    openWith({ onSearch });

    await user.type(screen.getByRole('combobox'), 'widget');

    expect(await screen.findByRole('option', { name: 'Widget · 123' })).toBeInTheDocument();
    await waitFor(() => expect(onSearch).toHaveBeenCalledWith('widget'));
  });

  it('activates a hit and closes the palette', async () => {
    const onSelect = vi.fn();
    const onSearch = vi.fn().mockResolvedValue([
      { label: 'Products', items: [{ icon: Package, label: 'Widget · 123', onSelect }] },
    ] as PaletteGroup[]);
    const user = userEvent.setup();
    openWith({ onSearch });

    await user.type(screen.getByRole('combobox'), 'widget');
    await user.click(await screen.findByRole('option', { name: 'Widget · 123' }));

    expect(onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows the error label when the search fails', async () => {
    const onSearch = vi.fn().mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    openWith({ onSearch, searchErrorLabel: 'Search failed' });

    await user.type(screen.getByRole('combobox'), 'widget');

    expect(await screen.findByText('Search failed')).toBeInTheDocument();
  });

  it('does not query the backend for a blank palette', () => {
    const onSearch = vi.fn().mockResolvedValue([]);
    openWith({ onSearch });

    // Opened but nothing typed → no backend call, static group still visible.
    expect(onSearch).not.toHaveBeenCalled();
    expect(screen.getByRole('option', { name: 'Go to reports' })).toBeInTheDocument();
  });
});
