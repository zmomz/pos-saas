import '@testing-library/jest-dom/vitest';
import axios from 'axios';
import { afterEach, expect, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
// ISSUE-274 (M11 · FE-Platform · a11y) — register the vitest-axe
// `toHaveNoViolations` matcher globally so the automated WCAG gate
// (`*.axe.a11y.test.tsx`) can assert axe-core scans across core flows.
// `extend-expect` supplies the TS types; `matchers` supplies the runtime impl.
import 'vitest-axe/extend-expect';
import * as axeMatchers from 'vitest-axe/matchers';
expect.extend(axeMatchers);

// REV-05: jsdom's XHR adapter hangs forever when the request body is a
// `FormData` (multipart upload) — MSW's XHR interceptor never resolves it, so
// any test exercising `uploadMultipart` would time out. Route ONLY FormData
// requests through the node-`http` adapter, which MSW's node interceptor
// handles cleanly; keep XHR for everything else so credentialed flows (e.g.
// the cookie refresh, which relies on `withCredentials` surfacing as
// `credentials: 'include'`) behave exactly as in the browser. The app's axios
// instance leaves `adapter` unset, so it resolves this global default at
// request time. Real browsers are unaffected (they keep the XHR adapter).
const nodeHttpAdapter = axios.getAdapter('http');
const xhrAdapter = axios.getAdapter('xhr');
axios.defaults.adapter = (config) => {
  const isFormData = typeof FormData !== 'undefined' && config.data instanceof FormData;
  return (isFormData ? nodeHttpAdapter : xhrAdapter)(config);
};

// Unmount React trees and clear storage between tests for isolation.
afterEach(() => {
  cleanup();
  localStorage.clear();
});

// jsdom doesn't implement matchMedia (used by some UI components / theme).
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

// jsdom lacks ResizeObserver (used by Radix UI primitives).
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = window.ResizeObserver || (ResizeObserverStub as unknown as typeof ResizeObserver);

// jsdom lacks IntersectionObserver (used by embla-carousel's slides-in-view).
class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}
window.IntersectionObserver =
  window.IntersectionObserver ||
  (IntersectionObserverStub as unknown as typeof IntersectionObserver);

// jsdom doesn't implement scrollIntoView (Radix select/command).
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

// jsdom lacks the Pointer Capture API that Radix Select uses to open its
// listbox; stub it so component tests can drive the select with userEvent.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
}

// jsdom doesn't implement elementFromPoint; input-otp's password-manager badge
// probe (#202 MFA code entry) calls it from a timer and would otherwise raise an
// unhandled error after the test completes.
if (!document.elementFromPoint) {
  document.elementFromPoint = () => null;
}
