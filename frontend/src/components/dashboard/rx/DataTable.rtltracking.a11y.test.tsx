import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import DataTable from './DataTable';

// ISSUE-226 (a11y · RTL) — Arabic letter-spacing reset, extended to the shared
// `.dxr-tbl` data-table primitive. Every list-heavy page renders its column
// headers through this one <DataTable>, whose `.dxr-tbl th` treatment is the
// classic Latin overline: `uppercase tracking-[0.06em]` (index.css). Arabic
// joins its letters cursively, so that tracking shatters the joins under an
// Arabic/RTL locale; the base `[dir='rtl']` reset in index.css lives in
// @layer base and loses to the components-layer tracking on `.dxr-tbl th`, so
// the spacing survives on the header cells. The fix mirrors the
// `rtl:tracking-normal` idiom already applied to the AgentDashboard client
// headers, the MasterDashboard leaderboard header, and the ⌘K group headings:
// neutralise the tracking only under an RTL ancestor, leaving LTR untouched.

interface Row {
  id: number;
  name: string;
  qty: number;
}

const ROWS: Row[] = [{ id: 1, name: 'Burger', qty: 2 }];

function renderTable() {
  return render(
    <DataTable<Row>
      columns={[
        { key: 'name', header: 'Item', cell: (r) => r.name },
        { key: 'qty', header: 'Qty', align: 'end', cell: (r) => r.qty },
      ]}
      rows={ROWS}
      rowKey={(r) => r.id}
    />,
  );
}

describe('DataTable header RTL letter-spacing (ISSUE-226)', () => {
  it('resets tracking on every uppercase .dxr-tbl column header under RTL', () => {
    const { container } = renderTable();

    // The shared table voice: <table class="dxr-tbl"> whose <th> cells carry
    // the uppercase/tracked overline treatment from index.css.
    expect(container.querySelector('table.dxr-tbl')).toBeInTheDocument();

    const headers = container.querySelectorAll('thead th');
    expect(headers.length).toBe(2);
    headers.forEach((th) => {
      // Non-color, RTL-only reset so Arabic joins aren't shattered.
      expect(th.className).toContain('rtl:tracking-normal');
    });
  });
});
