import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal, { POS_TENDER_OPTIONS } from './POSTerminal';

// ISSUE-268 (triage cleanup) — the single- and split-payment tender pickers used
// to carry two hand-maintained arrays that had already drifted: the single-payment
// picker offered `bank_transfer` while the split picker offered `transfer`, and
// neither could be trusted to stay in step with the other. This slice consolidates
// both pickers onto one shared `POS_TENDER_OPTIONS` constant and reconciles the
// naming onto the backend's canonical `transfer` tender type (see
// SUPPORTED_TENDER_TYPES in payment_gateway.py — `bank_transfer` was only ever an
// alias the backend normalised).

const BASE = 'http://127.0.0.1:8000/api/v1';
const PRODUCTS_URL = `${BASE}/entities/products`;

function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
    http.get(PRODUCTS_URL, () => HttpResponse.json([])),
    http.get(`${BASE}/pos/transactions`, () => HttpResponse.json({ items: [] })),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <POSTerminal />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('POSTerminal tender options (#268)', () => {
  it('exposes one shared tender constant using the backend-canonical naming', () => {
    // The drift bug was the two pickers disagreeing on the transfer tender's
    // value. The shared constant pins the canonical `transfer` type and drops
    // the `bank_transfer` alias so single- and split-payment can never diverge.
    const values = POS_TENDER_OPTIONS.map((o) => o.v);
    expect(values).toContain('transfer');
    expect(values).not.toContain('bank_transfer');
    // Every entry is well-formed (a tender value + an i18n label key).
    for (const opt of POS_TENDER_OPTIONS) {
      expect(typeof opt.v).toBe('string');
      expect(typeof opt.labelKey).toBe('string');
    }
    // No value repeats — a single source of truth, not a merged list.
    expect(new Set(values).size).toBe(values.length);
  });

  it('drives the single-payment picker from the shared constant', async () => {
    server.use(...mountSideHandlers());
    renderPage();

    // The picker renders a selectable button per shared option, including the
    // reconciled transfer tender (still labelled "Bank Transfer" for cashiers).
    expect(await screen.findByRole('button', { name: /bank transfer/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^cash$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /mada/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /gift card/i })).toBeInTheDocument();
  });
});
