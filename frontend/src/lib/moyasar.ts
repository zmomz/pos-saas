// moyasar.js card tokenization helper.
//
// The card PAN is entered in Moyasar's hosted fields and never touches our server
// (PAY-09); tokenization returns a reusable token we store (encrypted, server-side)
// for recurring billing. When no publishable key is configured (dev / un-onboarded
// installs) a deterministic sandbox token is produced so the card-on-file flow is
// demonstrable without credentials — mirroring the backend SandboxGateway (OPS-08).
//
// The real moyasar.js integration mounts a hosted form; this helper exposes the
// minimal contract the dashboards need (tokenize a card, with a sandbox fallback).
// Wiring the live hosted form is gated on a real MOYASAR_PUBLISHABLE_KEY.

export interface CardToken {
  token: string;
  last4?: string;
  brand?: string;
  sandbox: boolean;
}

export interface CardInput {
  number: string;
  name: string;
  month: string;
  year: string;
  cvc: string;
}

function detectBrand(pan: string): string {
  const n = pan.replace(/\s+/g, '');
  if (/^4/.test(n)) return 'VISA';
  if (/^(5[1-5]|2[2-7])/.test(n)) return 'MASTERCARD';
  if (/^(34|37)/.test(n)) return 'AMEX';
  if (/^9/.test(n)) return 'MADA';
  return 'CARD';
}

/** True once a real Moyasar publishable key is configured for live tokenization. */
export function moyasarConfigured(publishableKey?: string | null): boolean {
  return !!(publishableKey && publishableKey.trim());
}

/**
 * Tokenize a card. With a publishable key, defers to live moyasar.js tokenization;
 * otherwise returns a clearly-marked sandbox token (no PAN is sent anywhere).
 */
export async function tokenizeCard(
  card: CardInput,
  publishableKey?: string | null,
): Promise<CardToken> {
  const last4 = card.number.replace(/\s+/g, '').slice(-4);
  const brand = detectBrand(card.number);

  if (!moyasarConfigured(publishableKey)) {
    // Sandbox: synthesize a non-PAN token (the last4/brand are display-only).
    const rand = Math.abs(
      Array.from(`${card.number}${card.month}${card.year}`).reduce(
        (h, c) => (h * 31 + c.charCodeAt(0)) | 0,
        7,
      ),
    ).toString(16);
    return { token: `tok_sbx_${rand}`, last4, brand, sandbox: true };
  }

  // Live tokenization against Moyasar's tokens API with the publishable key.
  const resp = await fetch('https://api.moyasar.com/v1/tokens', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      publishable_api_key: publishableKey,
      name: card.name,
      number: card.number.replace(/\s+/g, ''),
      month: card.month,
      year: card.year,
      cvc: card.cvc,
      save_only: true, // create a reusable token, do not charge here
    }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body?.message || `Moyasar tokenization failed (${resp.status})`);
  }
  const body = await resp.json();
  return {
    token: body.id,
    last4: (body.last_four || last4) as string,
    brand: (body.brand || brand) as string,
    sandbox: false,
  };
}
