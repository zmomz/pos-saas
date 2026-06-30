import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// getAPIBaseURL is the runtime fallback when VITE_API_BASE_URL is unset.
vi.mock('../lib/config', () => ({
  getAPIBaseURL: vi.fn(() => ''),
}));

import { isCustomHost, applyBranding } from './BrandingContext';
import { getAPIBaseURL } from '../lib/config';

describe('isCustomHost', () => {
  beforeEach(() => {
    // platformHost() prefers the build-time VITE_API_BASE_URL (the platform's
    // canonical origin), which is baked at build time in prod.
    vi.stubEnv('VITE_API_BASE_URL', 'https://posai.tech');
    vi.mocked(getAPIBaseURL).mockReturnValue('');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('treats the platform domain as NOT custom (no by-domain lookup)', () => {
    expect(isCustomHost('posai.tech')).toBe(false);
    // www variant of the platform host is also the platform.
    expect(isCustomHost('www.posai.tech')).toBe(false);
  });

  it('treats a real agent custom domain as custom', () => {
    expect(isCustomHost('pos.myrestaurant.com')).toBe(true);
    expect(isCustomHost('shop.example.io')).toBe(true);
  });

  it('rejects localhost, .local, IPs and empty', () => {
    expect(isCustomHost('localhost')).toBe(false);
    expect(isCustomHost('dev.local')).toBe(false);
    expect(isCustomHost('31.97.154.251')).toBe(false);
    expect(isCustomHost('')).toBe(false);
  });

  it('falls back gracefully when the platform host is unparseable', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'not a url');
    // platformHost() returns '' → platform exclusion is skipped, normal rules apply.
    expect(isCustomHost('pos.myrestaurant.com')).toBe(true);
  });
});

// ISSUE-233 (B5) — secondary_color must be applied at runtime (not merely stored)
// so the BrandingEditor's secondary swatch/button reflects the live theme. It
// drives the `--accent` token consumed by `hsl(var(--accent))` chrome.
describe('applyBranding — secondary_color is applied to --accent', () => {
  afterEach(() => {
    document.documentElement.style.removeProperty('--accent');
    document.documentElement.style.removeProperty('--primary');
  });

  it('sets the --accent CSS variable from secondary_color', () => {
    applyBranding({
      primary_color: '#1488a6',
      secondary_color: '#00ff00',
      font_family: 'Inter',
      button_radius: '8px',
    });
    // #00ff00 → HSL "120 100% 50%".
    expect(document.documentElement.style.getPropertyValue('--accent')).toBe('120 100% 50%');
  });
});
