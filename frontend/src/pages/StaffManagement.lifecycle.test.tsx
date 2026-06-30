import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import StaffManagement from './StaffManagement';

// Issue #216 — the staff workforce dialog: lifecycle (suspend/terminate/
// reactivate), attendance clock in/out, shift assignment and PIN, all owner
// scoped behind the per-row "Workforce" action.

const BASE = 'http://127.0.0.1:8000';
const STAFF_URL = `${BASE}/api/v1/entities/staff_members`;

const STAFF = {
  items: [
    {
      id: 7,
      user_id: 'owner1',
      name: 'Sara Cashier',
      email: 'sara@shop.test',
      role: 'cashier',
      is_active: true,
      status: 'active',
    },
  ],
  total: 1,
  skip: 0,
  limit: 200,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <StaffManagement />
      </LanguageProvider>
    </MemoryRouter>,
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function openWorkforce() {
  const row = (await screen.findByText('Sara Cashier')).closest('tr')!;
  await userEvent.click(within(row).getByRole('button', { name: /workforce/i }));
}

describe('StaffManagement workforce dialog (#216)', () => {
  it('suspends a staff member through the lifecycle endpoint', async () => {
    let suspended = false;
    server.use(
      http.get(STAFF_URL, () => HttpResponse.json(STAFF)),
      http.get(`${STAFF_URL}/7/attendance`, () => HttpResponse.json([])),
      http.get(`${STAFF_URL}/7/shifts`, () => HttpResponse.json([])),
      http.post(`${STAFF_URL}/7/suspend`, () => {
        suspended = true;
        return HttpResponse.json({ ...STAFF.items[0], status: 'suspended', is_active: false });
      }),
    );

    renderPage();
    await openWorkforce();

    await userEvent.click(await screen.findByRole('button', { name: /^suspend$/i }));
    await waitFor(() => expect(suspended).toBe(true));
  });

  it('sets a PIN through the PIN tab', async () => {
    let postedPin: string | null = null;
    server.use(
      http.get(STAFF_URL, () => HttpResponse.json(STAFF)),
      http.get(`${STAFF_URL}/7/attendance`, () => HttpResponse.json([])),
      http.get(`${STAFF_URL}/7/shifts`, () => HttpResponse.json([])),
      http.put(`${STAFF_URL}/7/pin`, async ({ request }) => {
        postedPin = ((await request.json()) as { pin?: string }).pin ?? null;
        return HttpResponse.json({ ...STAFF.items[0] });
      }),
    );

    renderPage();
    await openWorkforce();

    // Switch to the PIN tab and enter a 4-digit PIN.
    await userEvent.click(await screen.findByRole('tab', { name: /pin/i }));
    const pinField = await screen.findByPlaceholderText('••••');
    await userEvent.type(pinField, '4821');
    await userEvent.click(screen.getByRole('button', { name: /^set pin$/i }));

    await waitFor(() => expect(postedPin).toBe('4821'));
  });

  it('clocks a staff member in from the attendance tab', async () => {
    let clockedIn = false;
    server.use(
      http.get(STAFF_URL, () => HttpResponse.json(STAFF)),
      http.get(`${STAFF_URL}/7/attendance`, () => HttpResponse.json([])),
      http.get(`${STAFF_URL}/7/shifts`, () => HttpResponse.json([])),
      http.post(`${STAFF_URL}/7/attendance/clock-in`, () => {
        clockedIn = true;
        return HttpResponse.json({ id: 1, staff_id: 7, clock_in: '2026-06-30T09:00:00Z', clock_out: null });
      }),
    );

    renderPage();
    await openWorkforce();

    await userEvent.click(await screen.findByRole('tab', { name: /attendance/i }));
    await userEvent.click(await screen.findByRole('button', { name: /clock in/i }));
    await waitFor(() => expect(clockedIn).toBe(true));
  });
});
