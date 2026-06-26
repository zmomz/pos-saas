import { describe, it, expect, beforeAll, afterAll, afterEach, vi } from 'vitest';
import { render, screen, waitFor, cleanup as cleanupRender } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server, http, HttpResponse } from '../test/msw';
import { LanguageProvider } from '@/lib/i18n';
import POSTerminal from './POSTerminal';

// FE-07 — the live camera barcode scanner (POS-06) starts a requestAnimationFrame
// loop, a 20s auto-stop timeout and a getUserMedia MediaStream from a click
// handler. None of those were tracked or torn down, so unmounting the page (or
// navigating away) left the device camera running, the RAF loop spinning and a
// pending setState that fires on an unmounted component. These tests pin the
// cleanup: unmount must stop the stream, cancel the RAF, and clear the timeout.

const BASE = 'http://127.0.0.1:8000/api/v1';

function mountSideHandlers() {
  return [
    http.get(`${BASE}/auth/me/permissions`, () =>
      HttpResponse.json({ is_master: false, denied: [], granted: [] })
    ),
    http.get(`${BASE}/entities/products`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/customers`, () => HttpResponse.json([])),
    http.get(`${BASE}/entities/branches`, () => HttpResponse.json([])),
    http.get(`${BASE}/payments/terminals`, () => HttpResponse.json([])),
    http.get(`${BASE}/tenant/client/branding`, () =>
      HttpResponse.json({ company_name: 'Test Shop', primary_color: '#000', secondary_color: '#fff', font_family: 'sans', button_radius: '0.5rem' })
    ),
    http.get(`${BASE}/pos/held`, () => HttpResponse.json({ items: [], total: 0 })),
  ];
}

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <POSTerminal />
      </LanguageProvider>
    </MemoryRouter>
  );
}

// Install fakes for the camera + BarcodeDetector + animation-frame APIs that the
// scanner uses. Returns the spies the tests assert on. RAF is made controllable
// (callbacks are captured, never auto-fired) so the loop stays paused at exactly
// one scheduled frame — deterministic, no runaway recursion in the test.
function installCameraFakes() {
  const track = { stop: vi.fn(), kind: 'video' };
  const stream = { getTracks: () => [track] };
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia },
    configurable: true,
  });

  class FakeBarcodeDetector {
    async detect() {
      return [] as { rawValue: string }[]; // never resolves a code -> keeps looping
    }
  }
  (window as unknown as { BarcodeDetector: unknown }).BarcodeDetector = FakeBarcodeDetector;

  const playSpy = vi
    .spyOn(window.HTMLMediaElement.prototype, 'play')
    .mockResolvedValue(undefined);

  let nextRafId = 0;
  const rafSpy = vi
    .spyOn(window, 'requestAnimationFrame')
    .mockImplementation(() => ++nextRafId);
  const cafSpy = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});

  const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout');
  const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout');

  return { track, getUserMedia, rafSpy, cafSpy, setTimeoutSpy, clearTimeoutSpy, playSpy };
}

async function startScanning(fakes: ReturnType<typeof installCameraFakes>) {
  renderPage();
  const camBtn = await screen.findByRole('button', { name: /scan with camera/i });
  await userEvent.click(camBtn);
  // Wait until the async toggle has acquired the camera and scheduled the loop.
  await waitFor(() => expect(fakes.getUserMedia).toHaveBeenCalled());
  await waitFor(() => expect(fakes.rafSpy).toHaveBeenCalled());
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
  delete (window as unknown as { BarcodeDetector?: unknown }).BarcodeDetector;
});
afterAll(() => server.close());

describe('POSTerminal camera-scan cleanup (FE-07)', () => {
  it('stops the MediaStream when the page unmounts mid-scan', async () => {
    const fakes = installCameraFakes();
    await startScanning(fakes);

    expect(fakes.track.stop).not.toHaveBeenCalled();

    cleanupRender();

    expect(fakes.track.stop).toHaveBeenCalled();
  });

  it('cancels the animation-frame loop on unmount', async () => {
    const fakes = installCameraFakes();
    await startScanning(fakes);

    cleanupRender();

    expect(fakes.cafSpy).toHaveBeenCalled();
  });

  it('clears the 20s auto-stop timeout on unmount', async () => {
    const fakes = installCameraFakes();
    await startScanning(fakes);

    const idx = fakes.setTimeoutSpy.mock.calls.findIndex((c) => c[1] === 20000);
    expect(idx).toBeGreaterThanOrEqual(0);
    const timeoutId = fakes.setTimeoutSpy.mock.results[idx].value;

    cleanupRender();

    expect(fakes.clearTimeoutSpy).toHaveBeenCalledWith(timeoutId);
  });
});
