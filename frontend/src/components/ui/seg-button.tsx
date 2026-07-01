import * as React from 'react';

/**
 * SegButton — one button inside a `.dxr-seg` segmented control (ISSUE-226 a11y).
 *
 * The app's segmented controls (KDS board/station tabs, floor-map zone filter,
 * report date ranges, …) are plain `<button>`s whose selected segment was
 * signalled by a `data-active` attribute ALONE. `data-active` is styling-only:
 * a screen-reader user gets no cue as to which segment is active. This shared
 * primitive reflects a single `active` prop into BOTH:
 *   - `data-active` — the visual cue the `.dxr-seg` CSS keys off, and
 *   - `aria-pressed` — the assistive-tech cue announcing the toggle state.
 *
 * It also defaults `type` to `"button"` so a segment dropped inside a <form>
 * never accidentally submits it (the native default is `"submit"`).
 */

export interface SegButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Whether this segment is the currently-selected one. */
  active: boolean;
}

export const SegButton = React.forwardRef<HTMLButtonElement, SegButtonProps>(
  ({ active, type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      data-active={active}
      aria-pressed={active}
      {...props}
    />
  ),
);
SegButton.displayName = 'SegButton';
