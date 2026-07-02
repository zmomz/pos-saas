import { describe, it, expect } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useBulkSelection } from './useBulkSelection';

// #231 (Productivity — bulk ops). A shared multi-row selection primitive for the
// management list screens: per-row toggle, a select-all-on-page toggle keyed to
// the ids currently visible, and a clear() the caller fires after a batch action.
const PAGE = [1, 2, 3];

describe('useBulkSelection', () => {
  it('starts empty', () => {
    const { result } = renderHook(() => useBulkSelection<number>(PAGE));
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.allPageSelected).toBe(false);
    expect(result.current.isSelected(1)).toBe(false);
  });

  it('toggles a single row on and off', () => {
    const { result } = renderHook(() => useBulkSelection<number>(PAGE));

    act(() => result.current.toggle(2));
    expect(result.current.isSelected(2)).toBe(true);
    expect(result.current.selectedCount).toBe(1);
    expect([...result.current.selectedIds]).toEqual([2]);

    act(() => result.current.toggle(2));
    expect(result.current.isSelected(2)).toBe(false);
    expect(result.current.selectedCount).toBe(0);
  });

  it('select-all-on-page selects every visible id, then deselects them', () => {
    const { result } = renderHook(() => useBulkSelection<number>(PAGE));

    act(() => result.current.toggleAllOnPage());
    expect(result.current.allPageSelected).toBe(true);
    expect(result.current.selectedCount).toBe(3);

    act(() => result.current.toggleAllOnPage());
    expect(result.current.allPageSelected).toBe(false);
    expect(result.current.selectedCount).toBe(0);
  });

  it('select-all leaves off-page selections untouched when toggling the page off', () => {
    // A row selected individually that is NOT on the current page must survive a
    // page-level deselect (only the visible ids are cleared).
    const { result } = renderHook(() => useBulkSelection<number>(PAGE));

    act(() => result.current.toggle(99)); // off-page
    act(() => result.current.toggleAllOnPage()); // add 1,2,3
    expect(result.current.selectedCount).toBe(4);

    act(() => result.current.toggleAllOnPage()); // remove 1,2,3 only
    expect(result.current.isSelected(99)).toBe(true);
    expect(result.current.selectedCount).toBe(1);
  });

  it('allPageSelected is false for an empty page even with other selections', () => {
    const { result } = renderHook(() => useBulkSelection<number>([]));
    act(() => result.current.toggle(7));
    expect(result.current.allPageSelected).toBe(false);
  });

  it('clear() empties the whole selection', () => {
    const { result } = renderHook(() => useBulkSelection<number>(PAGE));
    act(() => result.current.toggleAllOnPage());
    act(() => result.current.clear());
    expect(result.current.selectedCount).toBe(0);
    expect(result.current.isSelected(1)).toBe(false);
  });
});
