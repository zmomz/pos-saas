import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import ZatcaOnboarding from './ZatcaOnboarding';

// ISSUE-018: in-app ZATCA onboarding wizard. A merchant must be able to walk
// CSR generation -> OTP (compliance CSID) -> production CSID entirely in-app,
// with every step's failure surfaced (no swallowed errors).

const STATUS = 'http://127.0.0.1:8000/api/v1/zatca/status';
const CSR = 'http://127.0.0.1:8000/api/v1/zatca/onboard/csr';
const COMPLIANCE = 'http://127.0.0.1:8000/api/v1/zatca/onboard/compliance-csid';
const PRODUCTION = 'http://127.0.0.1:8000/api/v1/zatca/onboard/production-csid';

function statusBody(over: Record<string, unknown> = {}) {
  return {
    environment: 'sandbox',
    has_csr: false,
    onboarded: false,
    gateway_configured: true,
    pih: null,
    documents: 0,
    ...over,
  };
}

function renderWizard(onComplete = vi.fn()) {
  render(
    <MemoryRouter>
      <LanguageProvider>
        <ZatcaOnboarding onComplete={onComplete} />
      </LanguageProvider>
    </MemoryRouter>
  );
  return onComplete;
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('ZatcaOnboarding (ISSUE-018)', () => {
  it('opens on the CSR step with a generate action when no CSR exists yet', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json(statusBody())));

    renderWizard();

    expect(await screen.findByRole('button', { name: 'Generate CSR' })).toBeInTheDocument();
  });

  it('walks CSR -> OTP -> production CSID and signals completion', async () => {
    server.use(
      http.get(STATUS, () => HttpResponse.json(statusBody())),
      http.post(CSR, () =>
        HttpResponse.json({ csr_pem: 'PEM', csr_base64: 'B64', public_key_pem: 'PUB' })
      ),
      http.post(COMPLIANCE, () =>
        HttpResponse.json({ onboarded: false, message: 'Compliance CSID stored.' })
      ),
      http.post(PRODUCTION, () =>
        HttpResponse.json({ onboarded: true, message: 'Production CSID stored.' })
      )
    );
    const user = userEvent.setup();
    const onComplete = renderWizard();

    await user.click(await screen.findByRole('button', { name: 'Generate CSR' }));

    const otpInput = await screen.findByLabelText('OTP from the Fatoora portal');
    await user.type(otpInput, '123456');
    await user.click(screen.getByRole('button', { name: 'Submit OTP' }));

    await user.click(await screen.findByRole('button', { name: 'Finish onboarding' }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText('Onboarding complete. Your invoices will be signed and reported.')
    ).toBeInTheDocument();
  });

  it('surfaces the server error detail when a step fails (no swallowed failure)', async () => {
    server.use(
      http.get(STATUS, () => HttpResponse.json(statusBody({ has_csr: true }))),
      http.post(COMPLIANCE, () =>
        HttpResponse.json({ detail: 'ZATCA gateway rejected the OTP.' }, { status: 400 })
      )
    );
    const user = userEvent.setup();
    renderWizard();

    const otpInput = await screen.findByLabelText('OTP from the Fatoora portal');
    await user.type(otpInput, '000000');
    await user.click(screen.getByRole('button', { name: 'Submit OTP' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('ZATCA gateway rejected the OTP.');
    // The step must not advance on failure.
    expect(screen.queryByRole('button', { name: 'Finish onboarding' })).not.toBeInTheDocument();
  });

  it('resumes at the OTP step when a CSR already exists', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json(statusBody({ has_csr: true }))));

    renderWizard();

    expect(await screen.findByRole('button', { name: 'Submit OTP' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Generate CSR' })).not.toBeInTheDocument();
  });

  it('warns when no ZATCA gateway is configured', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json(statusBody({ gateway_configured: false }))));

    renderWizard();

    expect(await screen.findByText('Connect a ZATCA gateway before onboarding.')).toBeInTheDocument();
  });
});
