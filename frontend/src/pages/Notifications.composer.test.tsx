import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import Notifications from './Notifications';

// ISSUE-214 (M10 / parity #8): operators can compose and send a notification
// from the notifications page. This pins the composer wiring — channel choice
// flows through to POST /production/notifications/send and the dialog closes on
// success.

const LIST_URL = 'http://127.0.0.1:8000/api/v1/notifications/list';
const SEND_URL = 'http://127.0.0.1:8000/api/v1/production/notifications/send';

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <Notifications />
      </LanguageProvider>
    </MemoryRouter>
  );
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Notifications composer (ISSUE-214)', () => {
  it('composes a WhatsApp notification and posts it to the send endpoint', async () => {
    let sentBody: any = null;
    server.use(
      http.get(LIST_URL, () => HttpResponse.json({ items: [], unread_count: 0 })),
      http.post(SEND_URL, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json({ channel: sentBody.channel, to: sentBody.to, subject: 'Notification', status: 'logged', delivered: false });
      })
    );

    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /compose/i }));

    // Pick the WhatsApp channel, then fill recipient + message.
    await user.click(await screen.findByRole('button', { name: /whatsapp/i }));
    await user.type(screen.getByPlaceholderText('Phone number'), '+966500000000');
    await user.type(screen.getByPlaceholderText('Write your message…'), 'Your order is ready');

    await user.click(screen.getByRole('button', { name: /^send$/i }));

    await waitFor(() => expect(sentBody).not.toBeNull());
    expect(sentBody).toMatchObject({
      channel: 'whatsapp',
      to: '+966500000000',
      body: 'Your order is ready',
    });

    // Dialog closes on success.
    await waitFor(() =>
      expect(screen.queryByText('Compose notification')).not.toBeInTheDocument()
    );
  });

  it('sends a scheduled notification with scheduled_at set', async () => {
    let sentBody: any = null;
    server.use(
      http.get(LIST_URL, () => HttpResponse.json({ items: [], unread_count: 0 })),
      http.post(SEND_URL, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json({ channel: 'email', to: sentBody.to, subject: 'Reminder', status: 'scheduled', scheduled_at: sentBody.scheduled_at });
      })
    );

    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /compose/i }));
    await user.type(screen.getByPlaceholderText('Email address'), 'buyer@example.com');
    await user.type(screen.getByPlaceholderText('Write your message…'), 'Reservation tomorrow');

    // Turn on scheduling and set a future time.
    await user.click(screen.getByLabelText('Schedule for later'));
    const when = screen.getByLabelText('Send at') as HTMLInputElement;
    await user.type(when, '2099-01-01T09:00');

    await user.click(screen.getByRole('button', { name: /schedule/i }));

    await waitFor(() => expect(sentBody).not.toBeNull());
    expect(sentBody.channel).toBe('email');
    expect(sentBody.scheduled_at).toBeTruthy();
  });
});
