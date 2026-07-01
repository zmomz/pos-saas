import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import SupplierManagement from './SupplierManagement';

// M11 · FE-Platform a11y (#226) — adopt SegButton on the remaining `.dxr-seg`
// segmented controls. The Suppliers/Purchase-Orders tabs signalled their selected
// segment with `data-active` (styling) ALONE — no `aria-pressed`, so a
// screen-reader user got no cue which tab was active (WCAG 1.4.1 / 4.1.2).

const BASE = 'http://127.0.0.1:8000';
const EMPTY = { items: [], total: 0 };

function happyHandlers() {
  return [
    http.get(`${BASE}/api/v1/entities/suppliers`, () => HttpResponse.json(EMPTY)),
    http.get(`${BASE}/api/v1/entities/purchase_orders`, () => HttpResponse.json(EMPTY)),
    http.get(`${BASE}/api/v1/entities/products`, () => HttpResponse.json(EMPTY)),
    http.get(`${BASE}/api/v1/entities/branches`, () => HttpResponse.json(EMPTY)),
  ];
}

function renderPage() {
  return render(
    <LanguageProvider>
      <SupplierManagement />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('SupplierManagement segmented-tab a11y (#226)', () => {
  it('announces the active Suppliers/Purchase-Orders tab via aria-pressed', async () => {
    server.use(...happyHandlers());
    renderPage();

    expect(
      await screen.findByRole('button', { name: 'Suppliers', pressed: true })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Purchase Orders', pressed: false })
    ).toBeInTheDocument();
  });
});
