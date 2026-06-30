/**
 * White-label contrast guard (M2 Fix).
 *
 * A tenant chooses an arbitrary brand colour; chrome that paints solid-brand
 * surfaces (CTAs, the POS pay button, the agent storefront) must not hard-code
 * `text-white`, or a pale brand ships unreadable white-on-pale. These helpers
 * pick a legible text colour for a given solid background.
 *
 * The 0.6 luminance threshold mirrors `readableForeground` in BrandingContext
 * (which drives `--primary-foreground` for token-based chrome); this module is
 * the hex-returning counterpart for the inline-styled public/landing surfaces
 * and the BrandingEditor preview.
 */

/** Relative luminance of a hex colour in [0,1], or null when it can't be parsed. */
export function luminance(hex: string): number | null {
  let h = hex.trim().replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length !== 6 || /[^0-9a-fA-F]/.test(h)) return null;
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * Validate and normalize a hex color: trims whitespace, repairs a missing `#`,
 * expands a 3-digit shorthand, and lowercases. Returns `#rrggbb` for any valid
 * input or `null` when it can't be parsed — the BrandingEditor uses the null to
 * reject an invalid color before it can be saved.
 */
export function normalizeHex(hex: string): string | null {
  let h = (hex ?? '').trim().replace(/^#/, '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (h.length !== 6 || /[^0-9a-fA-F]/.test(h)) return null;
  return `#${h.toLowerCase()}`;
}

/** Near-black ink used when a pale background can't carry white text. */
export const DARK_INK = '#0a0a0a';

/**
 * Pick a readable text colour (`#ffffff` or near-black ink) for a solid hex
 * background. Unparseable input falls back to white — the historical default for
 * brand surfaces — so a malformed colour never crashes the render.
 */
export function readableTextColor(hex: string, fallback = '#ffffff'): string {
  const lum = luminance(hex);
  if (lum == null) return fallback;
  return lum > 0.6 ? DARK_INK : '#ffffff';
}
