// Webhook signing secrets must be unpredictable: the backend HMAC-signs payloads
// with this value, so anyone who can guess it can forge webhook deliveries.
// Math.random() is a non-cryptographic PRNG and must never seed a secret —
// draw from the Web Crypto CSPRNG (crypto.getRandomValues) instead. (FE-08)

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
const SECRET_LENGTH = 32;

// Largest multiple of the alphabet size that fits in a byte; bytes at or above
// it are rejected so every character is uniformly distributed (no modulo bias).
const REJECTION_THRESHOLD = 256 - (256 % ALPHABET.length);

export function generateWebhookSecret(): string {
  let result = 'whsec_';
  while (result.length < 'whsec_'.length + SECRET_LENGTH) {
    const bytes = new Uint8Array(SECRET_LENGTH);
    crypto.getRandomValues(bytes);
    for (const byte of bytes) {
      if (byte >= REJECTION_THRESHOLD) continue;
      result += ALPHABET.charAt(byte % ALPHABET.length);
      if (result.length === 'whsec_'.length + SECRET_LENGTH) break;
    }
  }
  return result;
}
