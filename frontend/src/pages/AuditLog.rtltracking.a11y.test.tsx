import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AuditLog from './AuditLog';

// ISSUE-226 (a11y · RTL) — Arabic letter-spacing reset, extended to the
// audit-log data-table column-header row. The five column headers (Timestamp /
// User / Action / Details / IP) render translated labels in a classic Latin
// `uppercase tracking-wider` overline treatment carried on the header <tr>.
// Arabic joins its letters cursively, so that tracking shatters the joins under
// an Arabic/RTL locale; the base `[dir='rtl']` reset in index.css lives in
// @layer base and loses to Tailwind's utility layer. This mirrors the
// `rtl:tracking-normal` idiom already applied to the sidebar nav-section, the
// ⌘K group headings, and the ForecastInsights stat overlines.

const BASE = 'http://127.0.0.1:8000';

const AUDIT = { items: [], total: 0, skip: 0, limit: 200 };

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <AuditLog />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AuditLog column-header RTL letter-spacing (ISSUE-226)', () => {
  it('resets tracking on the uppercase column-header row under RTL', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/audit_logs`, () => HttpResponse.json(AUDIT))
    );
    const { container } = renderPage();

    // The header row always renders, even with zero log entries.
    await screen.findByRole('table');
    const headerRow = container.querySelector('thead tr');
    expect(headerRow).not.toBeNull();
    expect(headerRow!.className).toContain('uppercase');
    expect(headerRow!.className).toContain('tracking-wider');
    // Non-color, RTL-only reset so Arabic joins aren't shattered.
    expect(headerRow!.className).toContain('rtl:tracking-normal');
  });
});
