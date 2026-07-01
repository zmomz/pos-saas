import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { server, http, HttpResponse } from '../test/msw';
import { askAssistant } from './api';

// #228 (M9·AI: in-app assistant) — thin client binding over the rule-based
// assistant endpoint (/assistant/query). The SPA asks a plain question and gets
// a grounded, self-describing answer (method + intent + data) back.

const BASE = 'http://127.0.0.1:8000/api/v1';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('assistant API binding (#228)', () => {
  it('askAssistant URL-encodes the question and returns the grounded answer', async () => {
    let seenUrl = '';
    server.use(
      http.get(`${BASE}/assistant/query`, ({ request }) => {
        seenUrl = request.url;
        return HttpResponse.json({
          method: 'rule_based',
          query: 'best seller?',
          intent: 'top_product',
          answer: 'Your best seller is Muffin — 12 units sold in the last 30 days.',
          data: { product_id: 3, name: 'Muffin', units_sold: 12 },
          suggestions: ['What is my best selling product?'],
        });
      })
    );

    const res = await askAssistant('best seller?');
    // The raw question is passed through as a ?q= query param, encoded.
    expect(seenUrl).toContain('q=best+seller%3F');
    expect(res.intent).toBe('top_product');
    expect(res.method).toBe('rule_based');
    expect(res.answer).toContain('Muffin');
    expect(res.data.units_sold).toBe(12);
  });
});
