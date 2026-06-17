import { test, expect, type Page } from '@playwright/test';

/**
 * Western-numerals visual pass (2026-06-18 decision). Boots the real production
 * bundle, logs in (mocked backend), renders a data-rich client dashboard in both
 * Arabic (RTL) and English, screenshots each, and asserts that NO Eastern
 * Arabic-Indic digits (٠-٩) appear anywhere in the rendered app while Arabic is
 * active — i.e. amounts, dates, counts and stats all use Western numerals.
 */

const EASTERN_DIGITS = /[٠-٩]/; // ٠١٢٣٤٥٦٧٨٩

const DASH = {
  total_sales: 54231.75,
  today_sales: 1234.5,
  total_transactions: 312,
  today_transactions: 8,
  products_count: 47,
  company_name: 'متجر التجربة',
};

const TXNS = {
  items: [
    { id: 1, invoice_number: 'INV-1001', total_amount: 1234.5, created_at: '2026-06-15T13:45:00Z', payment_method: 'cash', customer_name: 'عميل' },
    { id: 2, invoice_number: 'INV-1002', total_amount: 89, created_at: '2026-06-16T09:05:00Z', payment_method: 'card', customer_name: 'عميل' },
  ],
  total: 2,
};

async function mockBackend(page: Page) {
  // Catch-all FIRST so the specific routes registered below take precedence
  // (Playwright matches the most-recently-added route first).
  await page.route('**/api/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) })
  );
  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        token: 'test.jwt.token',
        refresh_token: 'refresh.token',
        user: { id: 'u1', email: 'merchant@example.com', name: 'Merchant', must_change_password: false },
      }),
    })
  );
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'u1', email: 'merchant@example.com', name: 'Merchant' }) })
  );
  await page.route('**/tenant/role', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ role: 'client', entity_id: 1, agent_id: 1 }) })
  );
  await page.route('**/tenant/client/dashboard', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DASH) })
  );
  // A real subscription object (numeric fee + billing date) so the subscription
  // card renders — and its numerals get checked too.
  await page.route('**/tenant/client/subscription', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ subscription_status: 'active', subscription_fee: 299, next_billing_date: '2026-07-01T00:00:00Z', payments: [] }),
    })
  );
  await page.route('**/pos/transactions**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(TXNS) })
  );
}

async function login(page: Page) {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill('merchant@example.com');
  await page.locator('input[type="password"]').fill('Password123');
  await page.locator('button[type="submit"]').click();
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
}

test('client dashboard renders Western numerals in Arabic (RTL)', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('pos-language', 'ar');
    localStorage.setItem('onboarding_completed_client', 'true'); // suppress the first-run tour overlay
  });
  await mockBackend(page);
  await login(page);

  // The RTL direction is actually applied.
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');

  // Wait for the CountUp stat animation to settle on its final Western value
  // (the assertion retries, so it isn't racing the count-up).
  await expect(page.locator('body')).toContainText('312'); // total transactions
  await page.screenshot({ path: 'test-results/dashboard-ar.png', fullPage: true });

  // Core assertion: nothing on screen uses Eastern Arabic-Indic digits.
  const text = await page.locator('body').innerText();
  const offending = text.split('\n').filter((l) => EASTERN_DIGITS.test(l));
  expect(offending, `Lines with Eastern digits: ${JSON.stringify(offending)}`).toEqual([]);
  expect(text).toMatch(/2026/); // a Western Gregorian year from a transaction date
});

test('client dashboard renders in English (LTR) for comparison', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('pos-language', 'en');
    localStorage.setItem('onboarding_completed_client', 'true'); // suppress the first-run tour overlay
  });
  await mockBackend(page);
  await login(page);

  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  // Guard against a silent crash, and wait for CountUp to settle.
  await expect(page.locator('body')).toContainText('312');
  await page.screenshot({ path: 'test-results/dashboard-en.png', fullPage: true });

  const text = await page.locator('body').innerText();
  expect(text).not.toMatch(EASTERN_DIGITS);
});

test('login screen mirrors correctly in Arabic (RTL)', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('pos-language', 'ar'));
  await mockBackend(page);
  await page.goto('/login');
  await expect(page.locator('input[type="email"]')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await page.screenshot({ path: 'test-results/login-ar.png', fullPage: true });
});
