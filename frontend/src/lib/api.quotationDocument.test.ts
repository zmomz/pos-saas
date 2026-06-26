import { describe, it, expect, beforeAll, afterAll, afterEach, beforeEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { getQuotationDocument } from './api';

// FE-11: openDocument used a bare fetch() that bypassed the shared axios client
// (and so the auth-refresh interceptor) and never checked resp.ok — it wrote
// error HTML into a new tab. The document is now fetched through the shared
// client (getBlob), which attaches the bearer token and rejects on a non-2xx
// status so the caller can surface the error.
const BASE = 'http://127.0.0.1:8000';
const DOC_URL = `${BASE}/api/v1/entities/quotations/:id/document`;

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  localStorage.setItem('pos_auth_token', 'tok-123');
});

describe('getQuotationDocument', () => {
  it('fetches the quotation document through the shared client (auth attached)', async () => {
    let auth: string | null = null;
    server.use(
      http.get(DOC_URL, ({ request, params }) => {
        auth = request.headers.get('authorization');
        return new HttpResponse(`<html data-id="${params.id}">عرض سعر</html>`, {
          headers: { 'Content-Type': 'text/html' },
        });
      })
    );

    const html = await getQuotationDocument(42);

    // Shared client => the request interceptor attached the bearer token (the
    // bare fetch only attached it when a token happened to be present, and never
    // went through the refresh interceptor).
    expect(auth).toBe('Bearer tok-123');
    expect(html).toContain('عرض سعر');
    expect(html).toContain('data-id="42"');
  });

  it('rejects on a non-2xx response so the caller can surface the error', async () => {
    server.use(
      http.get(DOC_URL, () => new HttpResponse('boom', { status: 500 }))
    );

    await expect(getQuotationDocument(7)).rejects.toBeTruthy();
  });
});
