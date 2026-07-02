import { describe, it, expect } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useSavedFilters } from './useSavedFilters';

// #231 (Productivity — saved filters). A power user pins the current list
// filter combination under a name and re-applies it in one click; the presets
// survive a reload (localStorage) and are keyed per screen.
interface ProductFilter {
  search: string;
  categoryFilter: string;
  showArchived: boolean;
}

const KEY = 'dxr.savedfilters.products';
const A: ProductFilter = { search: 'milk', categoryFilter: '3', showArchived: false };
const B: ProductFilter = { search: '', categoryFilter: 'all', showArchived: true };

describe('useSavedFilters', () => {
  it('saves a named filter and persists it to localStorage', () => {
    const { result } = renderHook(() => useSavedFilters<ProductFilter>(KEY));

    act(() => result.current.save('Dairy on hand', A));

    expect(result.current.saved).toEqual([{ name: 'Dairy on hand', value: A }]);
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual([
      { name: 'Dairy on hand', value: A },
    ]);
  });

  it('upserts by name (case-insensitive) instead of duplicating', () => {
    const { result } = renderHook(() => useSavedFilters<ProductFilter>(KEY));

    act(() => result.current.save('Dairy', A));
    act(() => result.current.save('dairy', B));

    expect(result.current.saved).toEqual([{ name: 'dairy', value: B }]);
  });

  it('ignores a blank / whitespace-only name', () => {
    const { result } = renderHook(() => useSavedFilters<ProductFilter>(KEY));

    act(() => result.current.save('   ', A));

    expect(result.current.saved).toEqual([]);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it('trims the stored name', () => {
    const { result } = renderHook(() => useSavedFilters<ProductFilter>(KEY));

    act(() => result.current.save('  Low stock  ', A));

    expect(result.current.saved[0].name).toBe('Low stock');
  });

  it('removes a filter by name', () => {
    const { result } = renderHook(() => useSavedFilters<ProductFilter>(KEY));

    act(() => result.current.save('Dairy', A));
    act(() => result.current.save('Archived', B));
    act(() => result.current.remove('Dairy'));

    expect(result.current.saved).toEqual([{ name: 'Archived', value: B }]);
  });

  it('hydrates its initial state from localStorage', () => {
    localStorage.setItem(KEY, JSON.stringify([{ name: 'Seed', value: A }]));

    const { result } = renderHook(() => useSavedFilters<ProductFilter>(KEY));

    expect(result.current.saved).toEqual([{ name: 'Seed', value: A }]);
  });

  it('tolerates a corrupt localStorage entry', () => {
    localStorage.setItem(KEY, '{not json');

    const { result } = renderHook(() => useSavedFilters<ProductFilter>(KEY));

    expect(result.current.saved).toEqual([]);
  });
});
