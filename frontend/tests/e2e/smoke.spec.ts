import { test, expect } from '@playwright/test';

/**
 * Golden smoke flow (Phase 0): the app boots, the login screen renders its form,
 * and a mocked login lands the user on the role dashboard. Backend endpoints are
 * mocked with page.route so the spec needs no live API.
 */

test('login screen renders the auth form', async ({ page }) => {
  await page.goto('/login');
  await expect(page.locator('input[type="email"]')).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
  await expect(page.locator('button[type="submit"]')).toBeVisible();
});

test('mocked login lands on the client dashboard', async ({ page }) => {
  const token = 'test.jwt.token';

  // Mock the auth + tenancy endpoints the app calls after submitting login.
  await page.route('**/api/v1/auth/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        token,
        refresh_token: 'refresh.token',
        user: { id: 'u1', email: 'merchant@example.com', name: 'Merchant', must_change_password: false },
      }),
    })
  );
  await page.route('**/api/v1/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'u1', email: 'merchant@example.com', name: 'Merchant' }),
    })
  );
  await page.route('**/tenant/role', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ role: 'client', entity_id: 1, agent_id: 1 }),
    })
  );
  // Any other API call → empty success so the dashboard can render.
  await page.route('**/api/v1/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0 }) })
  );

  await page.goto('/login');
  await page.locator('input[type="email"]').fill('merchant@example.com');
  await page.locator('input[type="password"]').fill('Password123');
  await page.locator('button[type="submit"]').click();

  // The app should navigate away from /login after a successful login.
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 15_000 });
});
