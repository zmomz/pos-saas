import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Search } from 'lucide-react';
import CommandPalette, { type PaletteGroup } from './CommandPalette';

// ISSUE-226 (M11 FE-Platform · a11y) — the ⌘K command palette rendered its
// overlay as a bare <div>: no dialog role, no aria-modal, no accessible name.
// A screen-reader user who opened it heard nothing announced as a modal and
// had no way to know they had entered a transient overlay. Its search field
// also carried only a placeholder — not a robust accessible name (it vanishes
// the moment the user types). This slice gives the overlay proper modal-dialog
// semantics and names the search field.

const GROUPS: PaletteGroup[] = [
  { label: 'Navigate', items: [{ icon: Search, label: 'Go to reports' }] },
];

function open(props: Record<string, unknown> = {}) {
  render(<CommandPalette groups={GROUPS} triggerLabel="Open search" {...props} />);
  fireEvent.click(screen.getByRole('button', { name: /Open search/ }));
}

describe('CommandPalette a11y (ISSUE-226)', () => {
  it('exposes no dialog until it is opened', () => {
    render(<CommandPalette groups={GROUPS} triggerLabel="Open search" />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens a named modal dialog', () => {
    open();
    const dialog = screen.getByRole('dialog', { name: 'Command palette' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('lets the host override the dialog label', () => {
    open({ label: 'Quick actions' });
    expect(screen.getByRole('dialog', { name: 'Quick actions' })).toBeInTheDocument();
  });

  it('names the search field by its accessible name', () => {
    open({ placeholder: 'Find a command' });
    expect(
      screen.getByRole('combobox', { name: 'Find a command' }),
    ).toBeInTheDocument();
  });
});
