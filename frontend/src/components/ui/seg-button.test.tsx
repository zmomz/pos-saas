import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SegButton } from './seg-button';

// ISSUE-226 (a11y) — screen-reader pass on segmented controls. The app's
// `.dxr-seg` segmented controls (KDS board/station tabs, floor-map zone filter,
// report ranges, …) previously signalled the selected segment with a
// `data-active` attribute ALONE — a purely visual cue. A screen-reader user
// could not perceive which segment was active. `SegButton` is the shared
// primitive that reflects a single `active` prop into BOTH the visual
// `data-active` and the assistive `aria-pressed`, and defaults to
// `type="button"` so a segment placed inside a <form> never submits it.

describe('SegButton (ISSUE-226 a11y segmented control)', () => {
  it('exposes the selected state to assistive tech via aria-pressed', () => {
    render(
      <>
        <SegButton active>Active</SegButton>
        <SegButton active={false}>Inactive</SegButton>
      </>,
    );
    expect(screen.getByRole('button', { name: 'Active', pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inactive', pressed: false })).toBeInTheDocument();
  });

  it('keeps the visual data-active cue in sync with active', () => {
    const { rerender } = render(<SegButton active>Range</SegButton>);
    expect(screen.getByRole('button').getAttribute('data-active')).toBe('true');
    rerender(<SegButton active={false}>Range</SegButton>);
    expect(screen.getByRole('button').getAttribute('data-active')).toBe('false');
  });

  it('defaults to type="button" so it never submits an enclosing form', () => {
    render(<SegButton active={false}>Tab</SegButton>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
  });

  it('forwards onClick, className and other button props', () => {
    render(
      <SegButton active={false} className="extra" data-testid="seg" disabled>
        X
      </SegButton>,
    );
    const btn = screen.getByTestId('seg');
    expect(btn).toHaveClass('extra');
    expect(btn).toBeDisabled();
  });
});
