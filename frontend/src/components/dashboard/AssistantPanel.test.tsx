import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { server, http, HttpResponse } from '../../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import AssistantPanel from './AssistantPanel';

// #228 (M9·AI): the in-app assistant surface. The rule-based /assistant/query
// endpoint already answers plain-language business questions from the tenant's
// own data; this panel is the operator-facing surface that lets a merchant type
// a question, submit it, and read the grounded answer — plus one-tap suggestion
// chips seeded by the backend. This test drives that behaviour through the
// rendered component.

const BASE = 'http://127.0.0.1:8000';

const SUGGESTIONS = [
  'What is my best selling product?',
  'How much did I sell today?',
  'Which products are low on stock?',
];

function answerFor(q: string) {
  return {
    method: 'rule_based',
    query: q,
    intent: 'top_product',
    answer: 'Your best seller is Widget — 42 units sold in the last 30 days.',
    data: { name: 'Widget', units_sold: 42 },
    suggestions: SUGGESTIONS,
  };
}

// Capture the query string the panel sends so we can assert it round-trips the
// operator's question rather than a hard-coded one.
let lastQuery: string | null = null;

function stubAssistant(responder?: (q: string) => unknown) {
  server.use(
    http.get(`${BASE}/api/v1/assistant/query`, ({ request }) => {
      const q = new URL(request.url).searchParams.get('q') ?? '';
      lastQuery = q;
      const body = responder ? responder(q) : answerFor(q);
      return body === 'error'
        ? new HttpResponse(null, { status: 500 })
        : HttpResponse.json(body);
    })
  );
}

function renderPanel() {
  return render(
    <LanguageProvider>
      <AssistantPanel />
    </LanguageProvider>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  lastQuery = null;
});
afterAll(() => server.close());

describe('AssistantPanel (#228 in-app assistant surface)', () => {
  it('sends the typed question and renders the grounded answer', async () => {
    stubAssistant();
    const user = userEvent.setup();
    renderPanel();

    await user.type(
      screen.getByRole('textbox', { name: /assistant/i }),
      'What is my best selling product?'
    );
    await user.click(screen.getByRole('button', { name: /ask/i }));

    expect(await screen.findByText(/Your best seller is Widget/)).toBeInTheDocument();
    expect(lastQuery).toBe('What is my best selling product?');
  });

  it('asks a suggestion chip when clicked without typing', async () => {
    stubAssistant();
    const user = userEvent.setup();
    renderPanel();

    // Suggestion chips are available up front so a merchant can ask in one tap.
    await user.click(screen.getByRole('button', { name: 'How much did I sell today?' }));

    await waitFor(() => expect(lastQuery).toBe('How much did I sell today?'));
    expect(await screen.findByText(/Your best seller is Widget/)).toBeInTheDocument();
  });

  it('does not query when the question is blank', async () => {
    stubAssistant();
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole('button', { name: /ask/i }));

    // A blank submit must not hit the endpoint (the backend requires min_length=1).
    expect(lastQuery).toBeNull();
  });

  it('surfaces an error when the assistant request fails', async () => {
    stubAssistant(() => 'error');
    const user = userEvent.setup();
    renderPanel();

    await user.type(screen.getByRole('textbox', { name: /assistant/i }), 'anything');
    await user.click(screen.getByRole('button', { name: /ask/i }));

    expect(await screen.findByText(/could not/i)).toBeInTheDocument();
  });
});
