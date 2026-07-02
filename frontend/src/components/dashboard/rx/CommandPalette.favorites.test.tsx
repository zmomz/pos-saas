import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Search, Package } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// #231 (Productivity — favorites): a power user can pin (star) a palette
// destination so it surfaces under a "Favorites" group at the very top of the
// ⌘K palette on a blank query — a one-keystroke jump to the pages they use
// most, without scrolling the whole nav rail. Pinned labels persist to
// localStorage (keyed by `favoritesKey`) so they survive a reload, and the
// feature is inert unless that key is supplied — the palette stays backwards
// compatible for callers that don't opt in. Only the static nav / quick-action
// items are favouritable; live /search hits and the Recent chips are not.

const FKEY = 'pos_favorites_test';
const STATIC: PaletteGroup[] = [
  {
    label: 'Navigate',
    items: [
      { icon: Search, label: 'Go to reports' },
      { icon: Package, label: 'Go to products' },
    ],
  },
];

function openWith(props: Record<string, unknown>) {
  const utils = render(
    <CommandPalette groups={STATIC} triggerLabel="Open search" {...props} />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
  return utils;
}

const favProps = {
  favoritesKey: FKEY,
  favoritesLabel: 'Favorites',
  favoriteAddLabel: 'Add to favorites',
  favoriteRemoveLabel: 'Remove from favorites',
};

beforeEach(() => localStorage.clear());

describe('CommandPalette favorites (#231)', () => {
  it('pins a starred item and surfaces it under Favorites on a blank query', () => {
    openWith(favProps);

    // No Favorites group yet — nothing is pinned.
    expect(screen.queryByText('Favorites')).toBeNull();

    // Star "Go to reports" via its toggle.
    fireEvent.click(
      screen.getByRole('button', { name: 'Add to favorites: Go to reports' }),
    );

    // Persisted, and the Favorites group now renders at the top with the item.
    expect(JSON.parse(localStorage.getItem(FKEY) as string)).toEqual(['Go to reports']);
    expect(screen.getByText('Favorites')).toBeInTheDocument();
    // The pinned label now appears twice: once in Favorites, once in Navigate.
    expect(screen.getAllByRole('button', { name: 'Go to reports' })).toHaveLength(2);
  });

  it('unpins a starred item via its filled star', () => {
    localStorage.setItem(FKEY, JSON.stringify(['Go to reports']));
    openWith(favProps);

    expect(screen.getByText('Favorites')).toBeInTheDocument();

    // The Favorites-group copy carries the "remove" toggle; click it.
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Remove from favorites: Go to reports' })[0],
    );

    expect(JSON.parse(localStorage.getItem(FKEY) as string)).toEqual([]);
    expect(screen.queryByText('Favorites')).toBeNull();
  });

  it('keeps no favorites and shows no star toggles when favoritesKey is absent', () => {
    openWith({ favoritesLabel: 'Favorites' }); // opted out

    expect(screen.queryByText('Favorites')).toBeNull();
    expect(
      screen.queryByRole('button', { name: /Add to favorites/ }),
    ).toBeNull();
  });

  it('drops a persisted favorite whose item no longer exists', () => {
    // 'Ghost' is stale (not in STATIC); 'Go to products' still resolves.
    localStorage.setItem(FKEY, JSON.stringify(['Ghost', 'Go to products']));
    openWith(favProps);

    expect(screen.getByText('Favorites')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ghost' })).toBeNull();
    // Resolves the surviving favorite (appears in both Favorites and Navigate).
    expect(screen.getAllByRole('button', { name: 'Go to products' })).toHaveLength(2);
  });
});
