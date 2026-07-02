import { describe, it, expect } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useFavorites } from './useFavorites';

// #273 (Productivity follow-up — entity-level favorites). Star an individual
// record (a customer / product) so it's one click away later. Favorites are a
// per-screen set of record ids, persisted to localStorage so they survive a
// reload — mirrors useSavedFilters' storage discipline.
const KEY = 'dxr.favorites.customers';

describe('useFavorites', () => {
  it('starts empty when nothing is persisted', () => {
    const { result } = renderHook(() => useFavorites(KEY));

    expect(result.current.count).toBe(0);
    expect(result.current.isFavorite('c1')).toBe(false);
  });

  it('toggles a record on and persists it to localStorage', () => {
    const { result } = renderHook(() => useFavorites(KEY));

    act(() => result.current.toggle('c1'));

    expect(result.current.isFavorite('c1')).toBe(true);
    expect(result.current.count).toBe(1);
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual(['c1']);
  });

  it('toggles a record back off', () => {
    const { result } = renderHook(() => useFavorites(KEY));

    act(() => result.current.toggle('c1'));
    act(() => result.current.toggle('c1'));

    expect(result.current.isFavorite('c1')).toBe(false);
    expect(result.current.count).toBe(0);
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual([]);
  });

  it('holds several independent favorites', () => {
    const { result } = renderHook(() => useFavorites(KEY));

    act(() => result.current.toggle('c1'));
    act(() => result.current.toggle('c2'));

    expect(result.current.isFavorite('c1')).toBe(true);
    expect(result.current.isFavorite('c2')).toBe(true);
    expect(result.current.count).toBe(2);
  });

  it('coerces non-string ids to strings so numeric keys match', () => {
    const { result } = renderHook(() => useFavorites(KEY));

    act(() => result.current.toggle(7));

    expect(result.current.isFavorite(7)).toBe(true);
    expect(result.current.isFavorite('7')).toBe(true);
  });

  it('hydrates its initial state from localStorage', () => {
    localStorage.setItem(KEY, JSON.stringify(['c9']));

    const { result } = renderHook(() => useFavorites(KEY));

    expect(result.current.isFavorite('c9')).toBe(true);
    expect(result.current.count).toBe(1);
  });

  it('tolerates a corrupt localStorage entry', () => {
    localStorage.setItem(KEY, '{not json');

    const { result } = renderHook(() => useFavorites(KEY));

    expect(result.current.count).toBe(0);
  });

  it('clears every favorite', () => {
    const { result } = renderHook(() => useFavorites(KEY));

    act(() => result.current.toggle('c1'));
    act(() => result.current.toggle('c2'));
    act(() => result.current.clear());

    expect(result.current.count).toBe(0);
    expect(JSON.parse(localStorage.getItem(KEY)!)).toEqual([]);
  });
});
