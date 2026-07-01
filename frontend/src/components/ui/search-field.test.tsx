import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SearchField } from './search-field';

// M11 · FE-Platform a11y (#226) — accessible search boxes.
//
// The list/table pages (Customers, Suppliers, …) each render a magnifier icon
// next to a bare <Input> whose only text is a `placeholder`. A placeholder is
// NOT an accessible name (WCAG 4.1.2 name/role/value): a screen-reader user who
// lands on the field hears "edit text, blank" with no hint of what it filters,
// and the hint vanishes the moment they type. SearchField centralises the
// icon-plus-input pattern and guarantees the control is exposed as a named
// `searchbox`, so every page that adopts it is announced correctly.

describe('SearchField', () => {
  it('exposes the control as a named searchbox using the explicit label', () => {
    render(<SearchField label="Search customers" placeholder="Search by name…" />);
    const box = screen.getByRole('searchbox', { name: 'Search customers' });
    expect(box).toBeInTheDocument();
  });

  it('falls back to the placeholder for the accessible name when no label is given', () => {
    render(<SearchField placeholder="Search suppliers" />);
    expect(screen.getByRole('searchbox', { name: 'Search suppliers' })).toBeInTheDocument();
  });

  it('forwards value and onChange like a controlled input', async () => {
    const onChange = vi.fn();
    render(<SearchField label="Search" value="" onChange={onChange} />);
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search' }), 'a');
    expect(onChange).toHaveBeenCalled();
  });

  it('renders a decorative magnifier icon that is hidden from assistive tech', () => {
    const { container } = render(<SearchField label="Search" />);
    const icon = container.querySelector('svg');
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute('aria-hidden', 'true');
  });
});
