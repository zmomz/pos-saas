import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Search, Package } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// #231 (Productivity — saved/recent searches): the global ⌘K palette remembers
// the queries a viewer actually acts on. Reopening the palette on a blank query
// surfaces those terms under a "Recent" group so a power user can re-run a
// frequent search in one keystroke instead of retyping it. Terms persist to
// localStorage (keyed by `recentSearchesKey`) so they survive a reload, and the
// feature is inert unless that key is supplied — the palette stays backwards
// compatible for callers that don't opt in.

const KEY = 'pos_recent_searches_test';
const STATIC: PaletteGroup[] = [
  { label: 'Navigate', items: [{ icon: Search, label: 'Go to reports' }] },
];

function productSearch(label = 'Widget · 123', onSelect = vi.fn()) {
  return vi
    .fn()
    .mockResolvedValue([
      { label: 'Products', items: [{ icon: Package, label, onSelect }] },
    ] as PaletteGroup[]);
}

function openWith(props: Record<string, unknown>) {
  const utils = render(
    <CommandPalette groups={STATIC} triggerLabel="Open search" {...props} />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
  return utils;
}

beforeEach(() => localStorage.clear());

describe('CommandPalette recent searches (#231)', () => {
  it('remembers a query once a result is selected and shows it on reopen', async () => {
    const user = userEvent.setup();
    const onSearch = productSearch();
    openWith({ onSearch, recentSearchesKey: KEY, recentLabel: 'Recent' });

    // Search, then act on a hit — that commits the query to history.
    await user.type(screen.getByRole('combobox'), 'widget');
    await user.click(await screen.findByRole('option', { name: 'Widget · 123' }));
    expect(screen.queryByRole('dialog')).toBeNull();

    // Reopen on a blank query: the term surfaces under the Recent group.
    fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
    expect(screen.getByText('Recent')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'widget' })).toBeInTheDocument();
  });

  it('re-runs the search when a recent term is picked, without closing', async () => {
    const user = userEvent.setup();
    const onSearch = productSearch();
    // Seed history directly so we start on a blank palette with a Recent group.
    localStorage.setItem(KEY, JSON.stringify(['widget']));
    openWith({ onSearch, recentSearchesKey: KEY, recentLabel: 'Recent' });

    await user.click(screen.getByRole('option', { name: 'widget' }));

    // The palette stays open and the query is re-run through onSearch.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveValue('widget');
    expect(await screen.findByRole('option', { name: 'Widget · 123' })).toBeInTheDocument();
    await vi.waitFor(() => expect(onSearch).toHaveBeenCalledWith('widget'));
  });

  it('keeps no history when no recentSearchesKey is supplied', async () => {
    const user = userEvent.setup();
    const onSearch = productSearch();
    openWith({ onSearch, recentLabel: 'Recent' }); // opted out

    await user.type(screen.getByRole('combobox'), 'widget');
    await user.click(await screen.findByRole('option', { name: 'Widget · 123' }));

    fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
    expect(screen.queryByText('Recent')).toBeNull();
  });

  it('dedupes and orders the history most-recent-first', async () => {
    const user = userEvent.setup();
    // Seed an earlier, differently-cased 'apple' plus 'banana'.
    localStorage.setItem(KEY, JSON.stringify(['Apple', 'banana']));
    const onSearch = productSearch();
    openWith({ onSearch, recentSearchesKey: KEY, recentLabel: 'Recent' });

    // Re-search 'apple' and act on it — it should jump to the front, not double.
    await user.type(screen.getByRole('combobox'), 'apple');
    await user.click(await screen.findByRole('option', { name: 'Widget · 123' }));

    expect(JSON.parse(localStorage.getItem(KEY) as string)).toEqual(['apple', 'banana']);
  });
});
