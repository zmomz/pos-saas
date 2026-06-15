import { describe, it, expect, vi, beforeEach } from 'vitest';

// getAPIBaseURL drives platformHost(); control it per-test.
vi.mock('../lib/config', () => ({
  getAPIBaseURL: vi.fn(() => 'https://posai.tech'),
}));

import { isCustomHost } from './BrandingContext';
import { getAPIBaseURL } from '../lib/config';

describe('isCustomHost', () => {
  beforeEach(() => {
    vi.mocked(getAPIBaseURL).mockReturnValue('https://posai.tech');
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

  it('falls back gracefully when the API base URL is unparseable', () => {
    vi.mocked(getAPIBaseURL).mockReturnValue('not a url');
    // platformHost() returns '' → platform exclusion is skipped, normal rules apply.
    expect(isCustomHost('pos.myrestaurant.com')).toBe(true);
  });
});
