import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AuditLog from './AuditLog';
import ExpenseTracking from './ExpenseTracking';

// ISSUE-244 — long ar/ur strings in fixed-width truncated cells were clipped with
// no way to read the full value. The clipped cells must expose the full text via
// a native `title` tooltip so nothing is silently lost.

const BASE = 'http://127.0.0.1:8000';
const TODAY = new Date().toISOString().split('T')[0];

const LONG = 'تم تحديث صلاحيات المستخدم بالكامل مع تفاصيل إضافية طويلة جداً للاختبار';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AuditLog details truncation has a tooltip (ISSUE-244)', () => {
  it('exposes the full details text via title on the clipped cell', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/audit_logs`, () =>
        HttpResponse.json({ items: [{ id: '1', user_email: 'a@b.test', action: 'update', details: LONG }], total: 1, skip: 0, limit: 200 })
      )
    );
    render(
      <MemoryRouter>
        <LanguageProvider>
          <AuditLog />
        </LanguageProvider>
      </MemoryRouter>
    );
    const cell = await screen.findByText(LONG);
    expect(cell).toHaveAttribute('title', LONG);
  });
});

describe('ExpenseTracking description truncation has a tooltip (ISSUE-244)', () => {
  it('exposes the full description via title on the clipped cell', async () => {
    server.use(
      http.get(`${BASE}/api/v1/entities/expenses`, () =>
        HttpResponse.json({ items: [{ id: 'e1', category: 'Supplies', amount: 40, expense_date: TODAY, description: LONG }], total: 1 })
      ),
      http.get(`${BASE}/api/v1/pos/transactions`, () => HttpResponse.json({ items: [], total: 0 }))
    );
    render(
      <MemoryRouter>
        <LanguageProvider>
          <ExpenseTracking />
        </LanguageProvider>
      </MemoryRouter>
    );
    const cell = await screen.findByText(LONG);
    expect(cell).toHaveAttribute('title', LONG);
  });
});
