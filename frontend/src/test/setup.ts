import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

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
// @ts-expect-error - assign stub onto window
window.ResizeObserver = window.ResizeObserver || ResizeObserverStub;

// jsdom doesn't implement scrollIntoView (Radix select/command).
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}
