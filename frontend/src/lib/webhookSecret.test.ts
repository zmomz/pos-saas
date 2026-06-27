import { describe, it, expect, vi, afterEach } from 'vitest';
import { generateWebhookSecret } from './webhookSecret';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('generateWebhookSecret', () => {
  it('produces a whsec_-prefixed secret with 32 chars of entropy', () => {
    const secret = generateWebhookSecret();
    expect(secret).toMatch(/^whsec_[A-Za-z0-9]{32}$/);
  });

  it('draws entropy from the Web Crypto CSPRNG, not Math.random', () => {
    const cryptoSpy = vi.spyOn(crypto, 'getRandomValues');
    const mathSpy = vi.spyOn(Math, 'random');

    generateWebhookSecret();

    expect(cryptoSpy).toHaveBeenCalled();
    expect(mathSpy).not.toHaveBeenCalled();
  });

  it('returns a fresh secret on each call', () => {
    const a = generateWebhookSecret();
    const b = generateWebhookSecret();
    expect(a).not.toEqual(b);
  });
});
