import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataTable from './DataTable';

// ISSUE-226 (a11y · keyboard-only nav audit) — the shared `.dxr-tbl` primitive
// lets a page make its rows clickable via `onRowClick` (it adds an onClick and a
// `cursor-pointer` affordance to each <tr>). But a bare <tr onClick> is invisible
// to the keyboard: it is not in the tab order, exposes no role, and never reacts
// to Enter/Space — so a keyboard-only or screen-reader operator can *see* the
// pointer affordance yet cannot activate the row (WCAG 2.1.1 Keyboard / 4.1.2
// Name, Role, Value). A clickable row must be a real, focusable button-like
// control; a non-clickable table must stay plain markup.

interface Row {
  id: number;
  name: string;
}

const ROWS: Row[] = [
  { id: 1, name: 'Burger' },
  { id: 2, name: 'Fries' },
];

function renderTable(onRowClick?: (row: Row, index: number) => void) {
  return render(
    <DataTable<Row>
      columns={[{ key: 'name', header: 'Item', cell: (r) => r.name }]}
      rows={ROWS}
      rowKey={(r) => r.id}
      onRowClick={onRowClick}
    />,
  );
}

describe('DataTable clickable-row keyboard a11y (ISSUE-226)', () => {
  it('exposes each clickable row as a focusable button-role control', () => {
    renderTable(() => {});

    const rows = screen.getAllByRole('button');
    expect(rows.length).toBe(2);
    rows.forEach((row) => {
      expect(row.tagName).toBe('TR');
      expect(row).toHaveAttribute('tabindex', '0');
    });
  });

  it('activates the row handler when Enter is pressed on a focused row', async () => {
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    renderTable(onRowClick);

    const [firstRow] = screen.getAllByRole('button');
    firstRow.focus();
    await user.keyboard('{Enter}');

    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[0], 0);
  });

  it('activates the row handler when Space is pressed on a focused row', async () => {
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    renderTable(onRowClick);

    const rows = screen.getAllByRole('button');
    rows[1].focus();
    await user.keyboard(' ');

    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(ROWS[1], 1);
  });

  it('leaves rows as plain, non-interactive markup when there is no onRowClick', () => {
    renderTable(undefined);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    const rows = document.querySelectorAll('tbody tr');
    rows.forEach((row) => {
      expect(row).not.toHaveAttribute('tabindex');
      expect(row).not.toHaveAttribute('role');
    });
  });
});
